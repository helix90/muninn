"""
Test the client-side field-rendering JS in app/templates/agents/edit.html.

The rest of the test suite is pure Python/pytest -- there's no JS test
runner in this project -- but the "Deduplicate Across Feeds" save bug
lived entirely in generateFieldHTML()'s HTML-attribute construction, which
a Flask test client can never exercise (it doesn't run JS). To actually
catch a regression here, this test extracts the real escapeHtml()/
generateFieldHTML() function source verbatim from the template file and
executes it under Node, then parses the resulting HTML the way a browser
would (entity-decoding included) to check what value would actually reach
the <input>. It skips (rather than fails) if Node isn't installed.
"""

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

_TEMPLATE_PATH = Path(__file__).parent.parent / 'app' / 'templates' / 'agents' / 'edit.html'

pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='Node.js not installed')


def _extract_function(source: str, name: str) -> str:
    """Pull a top-level `function NAME(...) { ... }` out of `source` verbatim, by brace-matching."""
    marker = f'function {name}('
    start = source.index(marker)
    brace_start = source.index('{', start)
    depth = 0
    for i in range(brace_start, len(source)):
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f'unbalanced braces while extracting function {name}() from {_TEMPLATE_PATH}')


class _InputAttrs(HTMLParser):
    """Collects attributes of every <input> tag; HTMLParser decodes entities for us."""

    def __init__(self):
        super().__init__()
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            self.inputs.append(dict(attrs))


def _run_generate_field_html(field: dict) -> str:
    """Execute the real escapeHtml()/generateFieldHTML() from edit.html under Node."""
    template_source = _TEMPLATE_PATH.read_text(encoding='utf-8')
    escape_html_js = _extract_function(template_source, 'escapeHtml')
    generate_field_html_js = _extract_function(template_source, 'generateFieldHTML')

    import json
    driver = f"""
{escape_html_js}
{generate_field_html_js}
const field = {json.dumps(field)};
process.stdout.write(generateFieldHTML(field));
"""
    result = subprocess.run(
        ['node', '-e', driver],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f'node execution failed: {result.stderr}'
    return result.stdout


class TestGenerateFieldHTMLListValues:
    """
    Regression coverage for: editing 'Deduplicate Across Feeds' (imported
    with config {"uniqueness_fields": ["link"], ...}) failed to save.

    Root cause: generateFieldHTML() JSON.stringify's list/object field
    values before embedding them in an HTML value="..." attribute, but
    didn't HTML-escape the result. For uniqueness_fields=["link"], that
    produced literal `value="["link"]"` -- the embedded double quotes
    closed the attribute early, so the browser exposed only `[` as the
    field's value. Saving then failed json.loads() server-side, stored the
    raw string '[', and DeduplicationAgent.validate_config() rejected it
    ("must be a list"), blocking the save. Fixed via an escapeHtml() pass.
    """

    def test_list_value_round_trips_through_rendered_attribute(self):
        field = {
            'name': 'uniqueness_fields',
            'label': 'Uniqueness Fields',
            'type': 'text',
            'required': True,
            'placeholder': 'Enter uniqueness fields',
            'value': ['link'],
        }
        html = _run_generate_field_html(field)

        parser = _InputAttrs()
        parser.feed(html)
        assert len(parser.inputs) == 1, f'expected exactly one <input>, got: {html!r}'

        # This is the literal string a submitting browser would send as
        # config_uniqueness_fields -- it must be valid JSON for a list,
        # not the truncated '[' the unescaped bug produced.
        submitted_value = parser.inputs[0]['value']
        assert submitted_value == '["link"]'

        import json
        assert json.loads(submitted_value) == ['link']

    def test_multi_field_list_value_round_trips(self):
        field = {
            'name': 'uniqueness_fields',
            'label': 'Uniqueness Fields',
            'type': 'text',
            'required': True,
            'placeholder': '',
            'value': ['link', 'title'],
        }
        html = _run_generate_field_html(field)

        parser = _InputAttrs()
        parser.feed(html)
        submitted_value = parser.inputs[0]['value']

        import json
        assert json.loads(submitted_value) == ['link', 'title']

    def test_plain_string_value_is_unaffected(self):
        """Sanity check: the fix shouldn't change behavior for ordinary scalar values."""
        field = {
            'name': 'feed_url',
            'label': 'Feed Url',
            'type': 'url',
            'required': True,
            'placeholder': '',
            'value': 'https://example.com/feed.xml',
        }
        html = _run_generate_field_html(field)

        parser = _InputAttrs()
        parser.feed(html)
        assert parser.inputs[0]['value'] == 'https://example.com/feed.xml'

    def test_value_containing_quotes_and_angle_brackets_is_escaped(self):
        """A value with HTML-special characters must not break out of the attribute
        or inject markup -- guards the fix generally, not just the JSON-array case."""
        field = {
            'name': 'note',
            'label': 'Note',
            'type': 'text',
            'required': False,
            'placeholder': '',
            'value': '"><script>alert(1)</script>',
        }
        html = _run_generate_field_html(field)

        parser = _InputAttrs()
        parser.feed(html)
        assert len(parser.inputs) == 1
        assert parser.inputs[0]['value'] == '"><script>alert(1)</script>'
        assert '<script>alert' not in html
