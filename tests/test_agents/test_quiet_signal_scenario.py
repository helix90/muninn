"""
Scenario-level smoke test for the "Quiet Signal Newsletter" template.

Regression check that the 4 custom agents it depends on
(topic_extract_agent, frequency_tracker_agent, hype_term_agent,
signal_score_agent) are registered end-to-end -- this is exactly what
export_import.validate_import_document rejects with "Unknown agent
type(s)" if registration is ever accidentally broken.
"""

import json
import os

from app.extensions import db
from app.models import AgentLink, Job
from app.scenarios.export_import import import_scenario, validate_import_document

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'app', 'template_library', 'scenarios',
    '09_quiet_signal_newsletter.json',
)


def _load_doc():
    with open(_TEMPLATE_PATH, encoding='utf-8') as f:
        return json.load(f)


class TestQuietSignalScenarioValidation:
    def test_validates_cleanly(self):
        doc = _load_doc()
        validated = validate_import_document(json.dumps(doc).encode('utf-8'))
        assert validated['scenario']['name'] == 'Quiet Signal Newsletter'
        assert len(validated['agents']) == 14
        assert len(validated['links']) == 13

    def test_all_custom_agent_types_present(self):
        doc = _load_doc()
        job_types = {a['job_type'] for a in doc['agents']}
        assert {
            'topic_extract_agent', 'frequency_tracker_agent',
            'hype_term_agent', 'signal_score_agent',
        } <= job_types


class TestQuietSignalScenarioImport:
    def test_import_creates_all_agents_and_links(self, app, test_user):
        with app.app_context():
            doc = _load_doc()
            scenario, warnings = import_scenario(doc, test_user.id)

            jobs = db.session.query(Job).filter_by(scenario_id=scenario.id).all()
            assert len(jobs) == 14

            job_types = {j.job_type for j in jobs}
            assert 'topic_extract_agent' in job_types
            assert 'frequency_tracker_agent' in job_types
            assert 'hype_term_agent' in job_types
            assert 'signal_score_agent' in job_types

            job_ids = {j.id for j in jobs}
            links = db.session.query(AgentLink).filter(
                AgentLink.source_agent_id.in_(job_ids),
                AgentLink.target_agent_id.in_(job_ids),
            ).all()
            assert len(links) == 13
