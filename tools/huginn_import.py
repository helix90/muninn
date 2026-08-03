#!/usr/bin/env python3
"""
huginn_import.py — Convert a Huginn scenario export to Muninn and import via REST API.

Usage:
    python tools/huginn_import.py HUGINN_EXPORT.json \\
        --api-url http://localhost:5000 \\
        --api-token YOUR_API_TOKEN \\
        [--dry-run] [--verbose] [--output OUTPUT.json]

The script reads a Huginn JSON export, translates agents to their nearest Muninn
equivalents, and POSTs the result to POST /api/v1/scenarios/import.

Agent mapping summary:
    Full fidelity : rss_agent, webhook_agent, http_post_agent, deduplication_agent,
                    delay_agent, slack_agent, telegram_agent
    Approximated  : filter_agent (TriggerAgent), template_agent (EventFormattingAgent),
                    email_agent, web_fetch_agent+html_parser_agent (WebsiteAgent)
    Not imported  : SchedulerAgent (schedule applied to its controlled agents instead)
    Skipped       : Twitter, JavaScript, DataOutput, EventDiff, and other site-specific agents
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required.  pip install requests", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# ANSI colours (gracefully degraded when not a tty)
# ---------------------------------------------------------------------------

def _colour(code: str) -> str:
    return code if sys.stdout.isatty() else ""


GREEN  = _colour("\033[32m")
YELLOW = _colour("\033[33m")
RED    = _colour("\033[31m")
BOLD   = _colour("\033[1m")
RESET  = _colour("\033[0m")


# ---------------------------------------------------------------------------
# Schedule translation
# ---------------------------------------------------------------------------

_SCHEDULE_MAP: Dict[str, Tuple[Optional[str], bool]] = {
    "never":      (None, False),
    "every_1m":   ("* * * * *",    True),
    "every_2m":   ("*/2 * * * *",  True),
    "every_5m":   ("*/5 * * * *",  True),
    "every_10m":  ("*/10 * * * *", True),
    "every_30m":  ("*/30 * * * *", True),
    "every_1h":   ("0 * * * *",    True),
    "every_2h":   ("0 */2 * * *",  True),
    "every_3h":   ("0 */3 * * *",  True),
    "every_4h":   ("0 */4 * * *",  True),
    "every_5h":   ("0 */5 * * *",  True),
    "every_6h":   ("0 */6 * * *",  True),
    "every_7h":   ("0 */7 * * *",  True),
    "every_12h":  ("0 */12 * * *", True),
    "every_1d":   ("0 0 * * *",    True),
    "every_2d":   ("0 0 */2 * *",  True),
    "every_7d":   ("0 0 * * 0",    True),
    "midnight":   ("0 0 * * *",    True),
    "1am":        ("0 1 * * *",    True),
    "2am":        ("0 2 * * *",    True),
    "3am":        ("0 3 * * *",    True),
    "4am":        ("0 4 * * *",    True),
    "5am":        ("0 5 * * *",    True),
    "6am":        ("0 6 * * *",    True),
    "7am":        ("0 7 * * *",    True),
    "8am":        ("0 8 * * *",    True),
    "9am":        ("0 9 * * *",    True),
    "10am":       ("0 10 * * *",   True),
    "11am":       ("0 11 * * *",   True),
    "noon":       ("0 12 * * *",   True),
    "1pm":        ("0 13 * * *",   True),
    "2pm":        ("0 14 * * *",   True),
    "3pm":        ("0 15 * * *",   True),
    "4pm":        ("0 16 * * *",   True),
    "5pm":        ("0 17 * * *",   True),
    "6pm":        ("0 18 * * *",   True),
    "7pm":        ("0 19 * * *",   True),
    "8pm":        ("0 20 * * *",   True),
    "9pm":        ("0 21 * * *",   True),
    "10pm":       ("0 22 * * *",   True),
    "11pm":       ("0 23 * * *",   True),
}


def translate_schedule(huginn_schedule: str) -> Tuple[Optional[str], bool]:
    """Convert a Huginn schedule string to (cron_expr_or_None, enabled)."""
    s = (huginn_schedule or "never").lower().strip()
    result = _SCHEDULE_MAP.get(s)
    if result is None:
        return (None, False)
    return result


# ---------------------------------------------------------------------------
# Liquid → Jinja2 template translation
# ---------------------------------------------------------------------------

_LIQUID_FILTER_SUBS = [
    (r"\|\s*downcase",             "| lower"),
    (r"\|\s*upcase",               "| upper"),
    (r"\|\s*capitalize",           "| capitalize"),
    (r"\|\s*strip\b",              "| strip"),
    (r"\|\s*lstrip",               "| lstrip"),
    (r"\|\s*rstrip",               "| rstrip"),
    (r"\|\s*escape",               "| e"),
    (r"\|\s*url_encode",           "| urlencode"),
    (r"\|\s*size\b",               "| length"),
    (r"\|\s*first\b",              "| first"),
    (r"\|\s*last\b",               "| last"),
    (r"\|\s*strip_newlines",       "| replace('\\n', '')"),
    (r"\|\s*strip_html",           ""),   # no Jinja2 equivalent — drop
    (r"\|\s*truncate:\s*(\d+)",    r"| truncate(\1, '')"),
    (r"\|\s*join:\s*[\"']([^\"']*)[\"']", r"| join('\1')"),
    (r"\|\s*split:\s*[\"']([^\"']*)[\"']", r"| split('\1')"),
    (
        r"\|\s*replace:\s*[\"']([^\"']*)[\"'],\s*[\"']([^\"']*)[\"']",
        r"| replace('\1', '\2')",
    ),
    (r"\|\s*date:\s*[\"'][^\"']*[\"']", ""),  # date format: drop (leave raw value)
]


def translate_liquid(template: str) -> str:
    """Best-effort Liquid → Jinja2 translation for the patterns Huginn uses most."""
    if not isinstance(template, str):
        return template

    # Huginn credential references: {% credential name %} → {{credential:name}}
    result = re.sub(r"\{%-?\s*credential\s+(\w+)\s*-?%\}", r"{{credential:\1}}", template)

    # Normalise Liquid tag whitespace ({{ foo }} and {% if x %})
    result = re.sub(r"\{\{\s*", "{{ ", result)
    result = re.sub(r"\s*\}\}", " }}", result)
    result = re.sub(r"\{%\s*", "{% ", result)
    result = re.sub(r"\s*%\}", " %}", result)

    for pattern, replacement in _LIQUID_FILTER_SUBS:
        result = re.sub(pattern, replacement, result)

    return result


def _apply_liquid_recursively(value: Any) -> Any:
    """Walk a config dict/list/str and translate all string values."""
    if isinstance(value, str):
        return translate_liquid(value)
    if isinstance(value, dict):
        return {k: _apply_liquid_recursively(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_apply_liquid_recursively(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# TriggerAgent rule translation
# ---------------------------------------------------------------------------

_TRIGGER_TYPE_MAP: Dict[str, str] = {
    "regex":        "regex",
    "!regex":       "not_contains",   # approximate: Muninn has no "not_regex"
    "field>value":  "greater_than",
    "field>=value": "greater_than",   # approximate
    "field<value":  "less_than",
    "field<=value": "less_than",      # approximate
    "field==value": "equals",
    "field!=value": "not_equals",
    "present":      "exists",
    "not present":  "not_exists",
    "contains":     "contains",
    "!contains":    "not_contains",
}


def translate_trigger_rules(huginn_rules: List[dict]) -> List[dict]:
    muninn_rules = []
    for rule in huginn_rules:
        h_type = rule.get("type", "").lower().strip()
        muninn_type = _TRIGGER_TYPE_MAP.get(h_type, "contains")
        path = rule.get("path", rule.get("field", ""))
        value = str(rule.get("value", ""))
        muninn_rule: dict = {"type": muninn_type, "field": path}
        if muninn_type not in ("exists", "not_exists"):
            muninn_rule["value"] = value
        muninn_rules.append(muninn_rule)
    return muninn_rules


# ---------------------------------------------------------------------------
# Per-type agent translators
# Each returns (job_type: str, config: dict)
# ---------------------------------------------------------------------------

def _translate_rss(opts: dict) -> Tuple[str, dict]:
    config: dict = {"feed_url": opts.get("url", "")}
    try:
        config["max_entries"] = int(opts["max_events_per_run"])
    except (KeyError, TypeError, ValueError):
        pass
    return "rss_agent", config


def _translate_website(opts: dict) -> Tuple[str, dict, str, dict]:
    """Returns (fetch_type, fetch_cfg, parser_type, parser_cfg)."""
    fetch_config = {"url": opts.get("url", "")}

    selectors: dict = {}
    for fname, extraction in opts.get("extract", {}).items():
        if isinstance(extraction, dict):
            css = extraction.get("css", extraction.get("xpath", ""))
            selectors[fname] = css
        elif isinstance(extraction, str):
            selectors[fname] = extraction

    parser_config = {
        "content_field": "body",
        "selectors": selectors if selectors else {"content": "body"},
        "extract_mode": "first",
    }
    return "web_fetch_agent", fetch_config, "html_parser_agent", parser_config


def _translate_trigger(opts: dict) -> Tuple[str, dict]:
    rules = translate_trigger_rules(opts.get("rules", []))
    match_type = opts.get("match", "any").lower()
    return "filter_agent", {
        "rules": rules,
        "match_all": match_type == "all",
    }


def _translate_event_formatting(opts: dict) -> Tuple[str, dict]:
    instructions = opts.get("instructions", {})
    mode = opts.get("mode", "clean")
    preserve = mode != "clean"

    if len(instructions) == 1:
        fname, tmpl = next(iter(instructions.items()))
        return "template_agent", {
            "template": translate_liquid(tmpl),
            "output_field": fname,
            "preserve_original": preserve,
        }

    templates = {k: translate_liquid(v) for k, v in instructions.items()}
    return "template_agent", {"templates": templates, "preserve_original": preserve}


def _translate_email(opts: dict) -> Tuple[str, dict]:
    recipients = opts.get("recipients", opts.get("to", ""))
    if isinstance(recipients, list):
        to_email: Any = recipients[0] if len(recipients) == 1 else recipients
    else:
        to_email = recipients or ""
    return "email_agent", {
        "to_email": to_email,
        "subject": translate_liquid(opts.get("subject", "{{ title }}")),
        "body": translate_liquid(opts.get("body", "{{ message }}")),
    }


def _translate_webhook(opts: dict) -> Tuple[str, dict]:
    config: dict = {"path": opts.get("path", "/webhook")}
    secret = opts.get("secret", "")
    if secret:
        config["secret"] = secret
    return "webhook_agent", config


def _translate_post(opts: dict) -> Tuple[str, dict]:
    method = opts.get("method", "post").upper()
    headers = dict(opts.get("headers") or {})
    if opts.get("content_type") == "json":
        headers.setdefault("Content-Type", "application/json")
    config: dict = {
        "url": opts.get("post_url", ""),
        "method": method,
    }
    if headers:
        config["headers"] = headers
    if "payload" in opts:
        config["payload"] = _apply_liquid_recursively(opts["payload"])
    return "http_post_agent", config


def _translate_slack(opts: dict) -> Tuple[str, dict]:
    config: dict = {
        "webhook_url": opts.get("webhook_url", ""),
        "message_template": translate_liquid(opts.get("message", "{{ message }}")),
    }
    for opt_key, cfg_key in [("username", "username"), ("icon", "icon_emoji"), ("channel", "channel")]:
        if opts.get(opt_key):
            config[cfg_key] = opts[opt_key]
    return "slack_agent", config


def _translate_telegram(opts: dict) -> Tuple[str, dict]:
    return "telegram_agent", {
        "bot_token": opts.get("token", opts.get("bot_token", "")),
        "chat_id": str(opts.get("chat_id", "")),
        "message_template": translate_liquid(opts.get("text", opts.get("message", "{{ message }}"))),
    }


def _translate_deduplication(opts: dict) -> Tuple[str, dict]:
    fields = opts.get("unique_fields", opts.get("uniqueness_fields", []))
    if isinstance(fields, str):
        fields = [fields]
    if not fields:
        prop = opts.get("property", "")
        fields = [prop] if prop else ["title"]
    config: dict = {"uniqueness_fields": fields}
    if "lookback_days" in opts:
        try:
            config["lookback_days"] = float(opts["lookback_days"])
        except (TypeError, ValueError):
            pass
    return "deduplication_agent", config


def _translate_delay(opts: dict) -> Tuple[str, dict]:
    try:
        minutes = max(1, int(opts.get("delay_minutes", opts.get("max_events", 60))))
    except (TypeError, ValueError):
        minutes = 60
    return "delay_agent", {"delay_minutes": minutes}


def _translate_http_status(opts: dict) -> Tuple[str, dict]:
    return "web_fetch_agent", {"url": opts.get("url", "")}


def _translate_json_parse(opts: dict) -> Tuple[str, dict]:
    path = opts.get("data", "$")
    if path and not path.startswith("$"):
        path = "$" + path
    return "jsonpath_agent", {"path": path}


def _translate_manual(opts: dict) -> Tuple[str, dict]:
    return "webhook_agent", {"path": "/webhook"}


def _translate_imap(opts: dict) -> Tuple[str, dict]:
    folders = opts.get("folders", ["INBOX"])
    folder = folders[0] if isinstance(folders, list) and folders else str(folders or "INBOX")
    return "imap_agent", {
        "host": opts.get("host", ""),
        "port": int(opts.get("port", 993)),
        "username": opts.get("username", ""),
        "password": opts.get("password", ""),
        "folder": folder,
        "use_ssl": True,
    }


# ---------------------------------------------------------------------------
# Type dispatch tables
# ---------------------------------------------------------------------------

# Maps the normalised type key (see _type_key()) to a translator function.
_TRANSLATORS: Dict[str, Any] = {
    "rss":             _translate_rss,
    "trigger":         _translate_trigger,
    "eventformatting": _translate_event_formatting,
    "email":           _translate_email,
    "emaildigest":     _translate_email,       # loses digest grouping
    "webhook":         _translate_webhook,
    "post":            _translate_post,
    "slack":           _translate_slack,
    "telegram":        _translate_telegram,
    "deduplication":   _translate_deduplication,
    "delay":           _translate_delay,
    "httpstatus":      _translate_http_status,
    "jsonparse":       _translate_json_parse,
    "manualevent":     _translate_manual,
    "imap":            _translate_imap,
    "imapfolder":      _translate_imap,
}

# Huginn agents that are absorbed (schedule propagated to targets, no Muninn agent created)
_ABSORBED = {"scheduler"}

# Huginn agents with no reasonable equivalent
_SKIPPED = {
    "twitter", "twitterx", "twitterxagent",
    "javascript",
    "dataoutput",
    "eventdiff",
    "github",
    "hipchat",
    "pushover",
    "googlecalendarpublish",
    "basecamp",
    "dropbox",
    "evernote",
    "sendgrid",
    "twilio",
}


def _type_key(huginn_type: str) -> str:
    """'Agents::EventFormattingAgent' → 'eventformatting'."""
    name = huginn_type.split("::")[-1]          # EventFormattingAgent
    name = re.sub(r"Agent$", "", name, flags=re.IGNORECASE)   # EventFormatting
    return name.lower().replace("_", "").replace(" ", "")     # eventformatting


# ---------------------------------------------------------------------------
# Pre-processing: flatten SchedulerAgents
# ---------------------------------------------------------------------------

def preprocess(data: dict) -> Tuple[List[dict], List[dict], Dict[int, Tuple], List[str]]:
    """
    Remove SchedulerAgents from the agent list and propagate their schedule to
    the agents they control (via control_links).

    Returns:
        agents           — Huginn agents list with schedulers removed
        links            — link list with indices remapped to match new agent list
        schedule_overrides — {new_agent_idx: (cron, enabled)}
        absorbed_names   — names of SchedulerAgents that were absorbed
    """
    agents = list(data.get("agents", []))
    links  = list(data.get("links", []))
    control_links = data.get("control_links", [])

    # Find SchedulerAgent indices (old indices)
    scheduler_old_idxs: set = set()
    absorbed_names: List[str] = []
    for i, agent in enumerate(agents):
        if _type_key(agent.get("type", "")) in _ABSORBED:
            scheduler_old_idxs.add(i)
            absorbed_names.append(agent.get("name", f"Scheduler {i}"))

    # Collect schedule overrides: old_target_idx → (cron, enabled)
    raw_overrides: Dict[int, Tuple] = {}
    for cl in control_links:
        ctrl = cl.get("controller")
        targets = cl.get("control_targets", [])
        if ctrl in scheduler_old_idxs:
            sched_str = agents[ctrl].get("options", {}).get("schedule", "never")
            cron, enabled = translate_schedule(sched_str)
            for tgt in targets:
                raw_overrides[tgt] = (cron, enabled)

    # Build remapping: old_idx → new_idx (None for removed schedulers)
    old_to_new: Dict[int, Optional[int]] = {}
    new_agents: List[dict] = []
    new_idx = 0
    for i, agent in enumerate(agents):
        if i in scheduler_old_idxs:
            old_to_new[i] = None
        else:
            old_to_new[i] = new_idx
            new_agents.append(agent)
            new_idx += 1

    # Remap schedule_overrides to new indices
    schedule_overrides: Dict[int, Tuple] = {}
    for old_idx, sched in raw_overrides.items():
        mapped = old_to_new.get(old_idx)
        if mapped is not None:
            schedule_overrides[mapped] = sched

    # Remap links, dropping those that touch removed schedulers
    new_links: List[dict] = []
    for link in links:
        src = link.get("source")
        rcv = link.get("receiver")
        new_src = old_to_new.get(src)
        new_rcv = old_to_new.get(rcv)
        if new_src is not None and new_rcv is not None:
            new_links.append({"source": new_src, "receiver": new_rcv})

    return new_agents, new_links, schedule_overrides, absorbed_names


# ---------------------------------------------------------------------------
# Reporting dataclass
# ---------------------------------------------------------------------------

@dataclass
class Report:
    imported:     List[tuple] = field(default_factory=list)   # (name, muninn_type)
    approximated: List[tuple] = field(default_factory=list)   # (name, muninn_type, note)
    skipped:      List[tuple] = field(default_factory=list)   # (name, huginn_type, reason)
    absorbed:     List[str]   = field(default_factory=list)   # scheduler names absorbed
    extra_agents: List[str]   = field(default_factory=list)   # synthetic agents added (splits)


# ---------------------------------------------------------------------------
# Main translation pass
# ---------------------------------------------------------------------------

def translate_all(
    huginn_agents: List[dict],
    huginn_links: List[dict],
    schedule_overrides: Dict[int, Tuple],
    absorbed_names: Optional[List[str]] = None,
) -> Tuple[List[dict], List[dict], Report]:
    """
    Translate preprocessed Huginn agents + links into Muninn format.
    Returns (muninn_agents, muninn_links, report).
    """
    report = Report()
    if absorbed_names:
        report.absorbed = list(absorbed_names)

    # huginn_idx → list of Muninn export_ids assigned ([] = skipped)
    h_to_m: Dict[int, List[int]] = {}
    muninn_agents: List[dict] = []
    extra_links: List[dict] = []   # internal links (e.g. web_fetch → html_parser)

    for h_idx, h_agent in enumerate(huginn_agents):
        h_type  = h_agent.get("type", "Unknown")
        h_name  = h_agent.get("name", f"Agent {h_idx}")
        opts    = h_agent.get("options", {})
        tkey    = _type_key(h_type)

        # Determine schedule
        h_schedule = h_agent.get("schedule", "never")
        if h_idx in schedule_overrides:
            sched_cron, sched_enabled = schedule_overrides[h_idx]
        else:
            sched_cron, sched_enabled = translate_schedule(h_schedule)

        is_active = not h_agent.get("disabled", False)

        # --- SchedulerAgent: already filtered by preprocess(); shouldn't reach here ---
        if tkey in _ABSORBED:
            report.absorbed.append(h_name)
            h_to_m[h_idx] = []
            continue

        # --- Skip list ---
        if tkey in _SKIPPED:
            report.skipped.append((h_name, h_type, "no Muninn equivalent"))
            h_to_m[h_idx] = []
            continue

        # --- WebsiteAgent: split into two agents ---
        # _type_key strips the "Agent" suffix, so "WebsiteAgent" → "website"
        if tkey == "website":
            fetch_id   = len(muninn_agents)
            parser_id  = fetch_id + 1

            _, fetch_cfg, _, parser_cfg = _translate_website(opts)

            muninn_agents.append({
                "export_id":       fetch_id,
                "name":            h_name,
                "job_type":        "web_fetch_agent",
                "config":          fetch_cfg,
                "schedule_cron":   sched_cron,
                "schedule_enabled": sched_enabled,
                "is_active":       is_active,
                "priority":        0,
            })
            muninn_agents.append({
                "export_id":       parser_id,
                "name":            f"{h_name} (parser)",
                "job_type":        "html_parser_agent",
                "config":          parser_cfg,
                "schedule_cron":   None,
                "schedule_enabled": False,
                "is_active":       is_active,
                "priority":        0,
            })
            h_to_m[h_idx] = [fetch_id, parser_id]
            extra_links.append({"source": fetch_id, "target": parser_id})
            report.approximated.append((
                h_name, "web_fetch_agent",
                "split: html_parser_agent added as downstream stage",
            ))
            report.extra_agents.append(f"{h_name} (parser)")
            continue

        # --- General dispatch ---
        translator = _TRANSLATORS.get(tkey)
        if translator is None:
            report.skipped.append((h_name, h_type, "no mapping for this type"))
            h_to_m[h_idx] = []
            continue

        try:
            job_type, config = translator(opts)
        except Exception as exc:
            report.skipped.append((h_name, h_type, f"translation error: {exc}"))
            h_to_m[h_idx] = []
            continue

        export_id = len(muninn_agents)
        muninn_agents.append({
            "export_id":       export_id,
            "name":            h_name,
            "job_type":        job_type,
            "config":          config,
            "schedule_cron":   sched_cron,
            "schedule_enabled": sched_enabled,
            "is_active":       is_active,
            "priority":        0,
        })
        h_to_m[h_idx] = [export_id]

        _APPROX_TYPES = {"filter_agent", "template_agent", "email_agent", "web_fetch_agent"}
        if job_type in _APPROX_TYPES:
            report.approximated.append((h_name, job_type, "config approximated"))
        else:
            report.imported.append((h_name, job_type))

    # --- Translate links ---
    muninn_links: List[dict] = list(extra_links)
    for link in huginn_links:
        src_ids = h_to_m.get(link.get("source"), [])
        rcv_ids = h_to_m.get(link.get("receiver"), [])
        if not src_ids or not rcv_ids:
            continue   # one or both ends were skipped
        # chain end of source → head of receiver
        muninn_links.append({"source": src_ids[-1], "target": rcv_ids[0]})

    return muninn_agents, muninn_links, report


# ---------------------------------------------------------------------------
# Build Muninn import document
# ---------------------------------------------------------------------------

def build_muninn_doc(
    name: str,
    description: str,
    agents: List[dict],
    links: List[dict],
) -> dict:
    return {
        "schema_version": 1,
        "scenario": {
            "name": name,
            "description": description or "",
            "color": "#3B82F6",
            "is_active": True,
        },
        "agents": agents,
        "links": links,
    }


# ---------------------------------------------------------------------------
# API import
# ---------------------------------------------------------------------------

def import_via_api(doc: dict, api_url: str, api_token: str) -> dict:
    url = api_url.rstrip("/") + "/api/v1/scenarios/import"
    resp = requests.post(
        url,
        json=doc,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"API returned {resp.status_code}: {resp.text[:500]}")
    return resp.json()


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

def print_report(
    huginn_name: str,
    n_huginn: int,
    muninn_agents: List[dict],
    muninn_links: List[dict],
    report: Report,
    verbose: bool,
) -> None:
    print(f"\n{BOLD}Huginn Scenario:{RESET} \"{huginn_name}\" ({n_huginn} agents)")
    print()
    print("Translating agents:")

    name_w = 38

    for name, job_type in report.imported:
        print(f"  {GREEN}✓{RESET}  {name:<{name_w}} → {job_type:<32}  full fidelity")

    for name, job_type, note in report.approximated:
        print(f"  {YELLOW}~{RESET}  {name:<{name_w}} → {job_type:<32}  {note}")

    for name, huginn_type, reason in report.skipped:
        short_type = huginn_type.split("::")[-1]
        print(f"  {RED}✗{RESET}  {name:<{name_w}}   {YELLOW}SKIPPED{RESET}  {reason}  ({short_type})")

    if verbose and report.absorbed:
        for name in report.absorbed:
            print(f"  {YELLOW}⊕{RESET}  {name:<{name_w}}   schedule absorbed into targets")

    print()

    n_in  = len(report.imported) + len(report.approximated)
    n_skip = len(report.skipped)
    n_extra = len(report.extra_agents)
    n_absorbed = len(report.absorbed)

    parts = [f"{n_huginn} input"]
    if n_absorbed:
        parts.append(f"– {n_absorbed} scheduler{'s' if n_absorbed > 1 else ''}")
    if n_skip:
        parts.append(f"– {n_skip} skipped")
    if n_extra:
        parts.append(f"+ {n_extra} split")
    parts.append(f"= {len(muninn_agents)}")

    print(f"Muninn agents: {len(muninn_agents)}  ({', '.join(parts)})")
    print(f"Links:         {len(muninn_links)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Import a Huginn scenario export into Muninn via the REST API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n", 1)[1],
    )
    p.add_argument("huginn_file", help="Path to the Huginn JSON export file")
    p.add_argument(
        "--api-url",
        default="http://localhost:5000",
        help="Base URL of the Muninn instance (default: %(default)s)",
    )
    p.add_argument(
        "--api-token",
        required=True,
        help="Muninn REST API token (Bearer auth)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Translate but do not import; combine with --output to inspect the result",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Show absorbed schedulers and extra detail",
    )
    p.add_argument(
        "--output",
        metavar="FILE",
        help="Save the translated Muninn import document to this JSON file",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --- Load Huginn export ---
    try:
        with open(args.huginn_file) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: Could not read {args.huginn_file}: {exc}", file=sys.stderr)
        sys.exit(1)

    if "agents" not in data:
        print(
            "ERROR: File does not look like a Huginn export (missing 'agents' key).",
            file=sys.stderr,
        )
        sys.exit(1)

    huginn_name = data.get("name", "Imported Huginn Scenario")
    huginn_desc = data.get("description", "")
    n_huginn    = len(data.get("agents", []))

    # --- Pre-process: absorb schedulers, remap indices ---
    agents, links, schedule_overrides, absorbed_names = preprocess(data)

    # --- Translate ---
    muninn_agents, muninn_links, report = translate_all(
        agents, links, schedule_overrides, absorbed_names
    )

    # --- Console report ---
    print_report(huginn_name, n_huginn, muninn_agents, muninn_links, report, args.verbose)

    # --- Build document ---
    doc = build_muninn_doc(huginn_name, huginn_desc, muninn_agents, muninn_links)

    # --- Optionally save translated document ---
    if args.output:
        try:
            with open(args.output, "w") as fh:
                json.dump(doc, fh, indent=2)
            print(f"\nTranslated document saved to: {args.output}")
        except OSError as exc:
            print(f"WARNING: Could not save output: {exc}", file=sys.stderr)

    if args.dry_run:
        print("\nDry run — not importing.  Pass --output to inspect the translated document.")
        return

    # --- Import via REST API ---
    print(f"\nImporting to Muninn at {args.api_url} …")
    try:
        result = import_via_api(doc, args.api_url, args.api_token)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    sid  = result.get("scenario_id")
    name = result.get("name", huginn_name)
    print(f"{GREEN}✓ Scenario created:{RESET} \"{name}\" (id={sid})")

    for w in result.get("warnings", []):
        print(f"  {YELLOW}Warning:{RESET} {w}")

    base = args.api_url.rstrip("/")
    print(f"\nOpen scenario at {base}/scenarios/{sid}")


if __name__ == "__main__":
    main()
