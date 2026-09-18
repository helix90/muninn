"""Default sample payloads for each agent type, used to pre-populate the test panel."""

_RSS_ITEM = {
    "title": "Example Article Title",
    "link": "https://example.com/article-1",
    "summary": "A brief summary of the article content.",
    "published": "2026-07-30T09:00:00",
    "author": "Jane Smith",
}

_EMAIL_ITEM = {
    "subject": "Example Email Subject",
    "from": "sender@example.com",
    "body": "This is the body of the example email.",
    "date": "2026-07-30T09:00:00",
}

_GENERIC = {
    "title": "Example Event",
    "data": "example value",
    "timestamp": "2026-07-30T09:00:00",
}

SAMPLE_PAYLOADS = {
    # Source agents — no input payload needed; shown for reference only
    "rss_agent":                _RSS_ITEM,
    "web_fetch_agent":          {"url": "https://example.com", "title": "Page Title", "text": "Page body text."},
    "api_call_agent":           {"status": "ok", "data": {"key": "value"}, "count": 1},
    "imap_agent":               _EMAIL_ITEM,
    "webhook_agent":            _GENERIC,
    "mqtt_subscriber_agent":    {"topic": "sensors/temp", "value": 23.5, "unit": "C"},
    "jabber_listener_agent":    {"from": "user@example.com", "body": "Hello!"},
    "s3_bucket_monitor_agent":  {"bucket": "my-bucket", "key": "uploads/file.csv", "size": 1024},
    "dropbox_read_agent":       {"name": "report.csv", "path": "/reports/report.csv", "size": 2048, "server_modified": "2026-09-18T09:00:00Z", "rev": "abc123", "id": "id:abc123"},

    # Transform agents
    "filter_agent":             _RSS_ITEM,
    "deduplication_agent":      _RSS_ITEM,
    "template_agent":           _RSS_ITEM,
    "html_parser_agent":        {"url": "https://example.com", "html": "<h1>Title</h1><p>Body text.</p>"},
    "csv_parser_agent":         {"csv": "name,age\nAlice,30\nBob,25", "filename": "data.csv"},
    "jsonpath_agent":           {"user": {"name": "Alice", "email": "alice@example.com"}, "status": "active"},
    "aggregation_agent":        _RSS_ITEM,
    "router_agent":             {"priority": "normal", "title": "Example Event", "link": "https://example.com"},
    "delay_agent":              _RSS_ITEM,
    "datastore_read_agent":     {"namespace": "my_data", "key": "last_seen"},
    "scheduler_agent":          _GENERIC,

    # Action agents
    "email_agent":              _RSS_ITEM,
    "slack_agent":              {"title": "Alert: Something happened", "link": "https://example.com", "summary": "Details here."},
    "telegram_agent":           {"title": "Alert: Something happened", "message": "Details here."},
    "discord_webhook_agent":    {"title": "Alert", "description": "Something happened.", "url": "https://example.com"},
    "http_post_agent":          {"event": "user.signup", "user_id": 42, "email": "alice@example.com"},
    "jabber_agent":             {"subject": "Alert", "body": "Something needs your attention."},
    "mqtt_publisher_agent":     {"topic": "alerts/high", "value": 99.5},
    "datastore_write_agent":    {"key": "last_processed", "value": "article-1", "namespace": "rss_tracker"},
    "dropbox_write_agent":      {"name": "report", "date": "2026-09-18", "content": "Line 1\nLine 2\n"},
}

DEFAULT_PAYLOAD = _GENERIC


def get_sample_payload(agent_type: str) -> dict:
    return dict(SAMPLE_PAYLOADS.get(agent_type, DEFAULT_PAYLOAD))
