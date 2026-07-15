"""
Scenario export / import service.

Export serialises a scenario and all of its agents + internal links to a
self-contained JSON document.  Import reconstructs that document under the
current user, creating fresh database records while preserving the agent
graph structure.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.agents.registry import agent_registry
from app.extensions import db
from app.models import AgentLink, Job, Scenario

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB

# Matches {{credential:some_name}}
_CREDENTIAL_RE = re.compile(r'\{\{credential:([a-zA-Z0-9_-]+)\}\}')


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_scenario(scenario: Scenario) -> Dict[str, Any]:
    """
    Build a JSON-serialisable dict representing *scenario* and all of its
    agents and internal links.

    Only AgentLinks where both endpoints belong to this scenario are included;
    cross-scenario links are silently omitted.  Credential references inside
    agent configs are preserved verbatim as ``{{credential:name}}`` strings —
    they are never resolved or decrypted.

    Returns the export document as a plain dict (caller serialises to JSON).
    """
    agents: List[Job] = (
        db.session.query(Job)
        .filter_by(scenario_id=scenario.id)
        .order_by(Job.id)
        .all()
    )

    agent_ids = {a.id for a in agents}
    # Build export_id (0-based index within this export) for each real DB id
    id_to_export = {a.id: idx for idx, a in enumerate(agents)}

    # Only links where both ends are inside this scenario
    links: List[AgentLink] = (
        db.session.query(AgentLink)
        .filter(
            AgentLink.source_agent_id.in_(agent_ids),
            AgentLink.target_agent_id.in_(agent_ids),
        )
        .all()
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": scenario.user.username if scenario.user else "unknown",
        "scenario": {
            "name": scenario.name,
            "description": scenario.description,
            "color": scenario.color,
            "is_active": scenario.is_active,
        },
        "agents": [
            {
                "export_id": id_to_export[a.id],
                "name": a.name,
                "job_type": a.job_type,
                "description": a.description,
                "config": a.config or {},
                "schedule_cron": a.schedule_cron,
                "schedule_enabled": a.schedule_enabled,
                "is_active": a.is_active,
                "priority": a.priority,
                "tags": a.tags,
            }
            for a in agents
        ],
        "links": [
            {
                "source": id_to_export[lnk.source_agent_id],
                "target": id_to_export[lnk.target_agent_id],
            }
            for lnk in links
        ],
    }


# ---------------------------------------------------------------------------
# Import validation
# ---------------------------------------------------------------------------

class ImportValidationError(ValueError):
    """Raised when the import document fails hard validation."""


def validate_import_document(raw_bytes: bytes) -> Dict[str, Any]:
    """
    Parse and structurally validate an upload.

    Returns the parsed document dict on success.
    Raises :class:`ImportValidationError` with a human-readable message on
    any hard failure (bad JSON, wrong schema_version, unknown agent types,
    etc.).
    """
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ImportValidationError(
            f"File exceeds the 1 MB size limit "
            f"({len(raw_bytes) // 1024} KB uploaded)."
        )

    try:
        doc = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(f"Invalid JSON: {exc}") from exc

    if not isinstance(doc, dict):
        raise ImportValidationError("Import file must be a JSON object.")

    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ImportValidationError(
            f"Unsupported schema_version {version!r}. "
            f"Expected {SCHEMA_VERSION}."
        )

    if "scenario" not in doc or not isinstance(doc["scenario"], dict):
        raise ImportValidationError("Missing or invalid 'scenario' key.")

    if "agents" not in doc or not isinstance(doc["agents"], list):
        raise ImportValidationError("Missing or invalid 'agents' key.")

    if "links" not in doc or not isinstance(doc["links"], list):
        raise ImportValidationError("Missing or invalid 'links' key.")

    # Validate agent types are all registered
    unknown = [
        a["job_type"]
        for a in doc["agents"]
        if not agent_registry.is_registered(a.get("job_type", ""))
    ]
    if unknown:
        raise ImportValidationError(
            f"Unknown agent type(s): {', '.join(sorted(set(unknown)))}. "
            "Ensure the Muninn instance supports these agent types."
        )

    # Validate link indices are in bounds
    n = len(doc["agents"])
    for lnk in doc["links"]:
        src = lnk.get("source")
        tgt = lnk.get("target")
        if not isinstance(src, int) or not isinstance(tgt, int):
            raise ImportValidationError(
                f"Link has non-integer source/target: {lnk!r}"
            )
        if not (0 <= src < n and 0 <= tgt < n):
            raise ImportValidationError(
                f"Link references out-of-range export_id: {lnk!r} "
                f"(document has {n} agent(s))."
            )

    return doc


def _find_credential_refs(config: Any) -> List[str]:
    """Recursively collect all credential names referenced in a config."""
    found = []
    if isinstance(config, dict):
        for v in config.values():
            found.extend(_find_credential_refs(v))
    elif isinstance(config, list):
        for item in config:
            found.extend(_find_credential_refs(item))
    elif isinstance(config, str):
        found.extend(_CREDENTIAL_RE.findall(config))
    return found


def check_missing_credentials(doc: Dict[str, Any], user_id: int) -> List[str]:
    """
    Return a sorted list of credential names referenced in the document that
    do not yet exist for *user_id*.  Empty list means nothing is missing.
    """
    from app.models import Credential  # local to avoid circular import

    referenced: set = set()
    for agent_def in doc.get("agents", []):
        referenced.update(_find_credential_refs(agent_def.get("config", {})))

    if not referenced:
        return []

    existing_names = {
        row[0]
        for row in db.session.query(Credential.name)
        .filter(
            Credential.user_id == user_id,
            Credential.name.in_(referenced),
        )
        .all()
    }

    return sorted(referenced - existing_names)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _unique_scenario_name(base_name: str, user_id: int) -> str:
    """
    Return *base_name* if no scenario with that name exists for the user,
    otherwise append ' (2)', ' (3)', … until a free name is found.
    """
    existing = {
        row[0]
        for row in db.session.query(Scenario.name)
        .filter_by(user_id=user_id)
        .all()
    }
    if base_name not in existing:
        return base_name
    counter = 2
    while f"{base_name} ({counter})" in existing:
        counter += 1
    return f"{base_name} ({counter})"


def import_scenario(
    doc: Dict[str, Any], user_id: int
) -> Tuple[Scenario, List[str]]:
    """
    Persist the export document *doc* for *user_id* inside a single
    transaction.

    Returns ``(new_scenario, warnings)`` where *warnings* is a list of
    human-readable messages about non-fatal issues (e.g. missing credentials).

    Raises :class:`ImportValidationError` (or any SQLAlchemy exception) on
    failure; the caller is responsible for rolling back if needed.
    """
    warnings: List[str] = []

    # --- Soft check: missing credentials ---
    missing_creds = check_missing_credentials(doc, user_id)
    if missing_creds:
        warnings.append(
            "The following credentials are referenced in the imported agents "
            "but do not exist on this instance. Create them before running "
            f"the agents: {', '.join(missing_creds)}"
        )

    scenario_def = doc["scenario"]
    agent_defs = doc["agents"]
    link_defs = doc["links"]

    # --- Create Scenario ---
    chosen_name = _unique_scenario_name(scenario_def["name"], user_id)
    scenario = Scenario(
        user_id=user_id,
        name=chosen_name,
        description=scenario_def.get("description"),
        color=scenario_def.get("color") or "#3B82F6",
        is_active=scenario_def.get("is_active", True),
    )
    db.session.add(scenario)
    db.session.flush()  # get scenario.id without committing

    # --- Create Jobs (agents), maintaining export_id → new DB id mapping ---
    export_id_to_db_id: Dict[int, int] = {}

    for agent_def in sorted(agent_defs, key=lambda a: a["export_id"]):
        job = Job(
            name=agent_def["name"],
            job_type=agent_def["job_type"],
            config=agent_def.get("config") or {},
            user_id=user_id,
            scenario_id=scenario.id,
            description=agent_def.get("description"),
            tags=agent_def.get("tags"),
            priority=agent_def.get("priority", 0),
            is_active=agent_def.get("is_active", True),
            schedule_cron=agent_def.get("schedule_cron"),
            schedule_enabled=agent_def.get("schedule_enabled", False),
            # Deliberately omit last_scheduled_run / next_scheduled_run
        )
        db.session.add(job)
        db.session.flush()  # get job.id
        export_id_to_db_id[agent_def["export_id"]] = job.id

    # --- Create AgentLinks ---
    for link_def in link_defs:
        link = AgentLink(
            source_agent_id=export_id_to_db_id[link_def["source"]],
            target_agent_id=export_id_to_db_id[link_def["target"]],
        )
        db.session.add(link)

    db.session.commit()

    return scenario, warnings
