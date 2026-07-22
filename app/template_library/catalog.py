"""Reads and indexes bundled scenario template JSON files."""

import json
import os
from typing import Any, Dict, List, Optional

_SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), 'scenarios')

_DIFFICULTY_ORDER = {'beginner': 0, 'intermediate': 1, 'advanced': 2}


def _load_all() -> List[Dict[str, Any]]:
    templates = []
    try:
        filenames = sorted(os.listdir(_SCENARIOS_DIR))
    except OSError:
        return templates

    for filename in filenames:
        if not filename.endswith('.json'):
            continue
        slug = filename[:-5]
        filepath = os.path.join(_SCENARIOS_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        meta = doc.get('_template_meta', {})
        templates.append({
            'slug': slug,
            'display_name': meta.get('display_name', slug),
            'description': meta.get('description', ''),
            'tags': meta.get('tags', []),
            'difficulty': meta.get('difficulty', 'intermediate'),
            'required_credentials': meta.get('required_credentials', []),
            'agent_count': len(doc.get('agents', [])),
            'doc': doc,
        })

    templates.sort(key=lambda t: (
        _DIFFICULTY_ORDER.get(t['difficulty'], 99),
        t['display_name'],
    ))
    return templates


def get_all() -> List[Dict[str, Any]]:
    return _load_all()


def get_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    for t in _load_all():
        if t['slug'] == slug:
            return t
    return None
