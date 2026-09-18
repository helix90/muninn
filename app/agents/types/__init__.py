"""
Agent type implementations

Source Agents:
- RSSAgent: Fetch RSS/Atom feeds
- WebFetchAgent: HTTP GET requests
- SchedulerAgent: Time-based triggers
- JabberListenerAgent: Receive XMPP/Jabber messages (direct + group chat)
- S3BucketMonitorAgent: Monitor AWS S3 buckets for file changes
- IMAPAgent: Monitor email inbox via IMAP
- MqttSubscriberAgent: Subscribe to MQTT topics (Mosquitto-compatible)
- DataStoreReadAgent: Emit events from the shared DataStore
- DropboxReadAgent: Monitor a Dropbox folder for new or modified files

Transform Agents:
- FilterAgent: Rule-based filtering
- DeduplicationAgent: Remove duplicates
- HTMLParserAgent: Parse HTML via CSS selectors
- TemplateAgent: Transform via Jinja2
- JSONPathAgent: Extract fields using JSONPath expressions
- AggregationAgent: Aggregate events into time/count-based windows
- CSVParserAgent: Parse CSV content from event payloads
- RouterAgent: Tag events with a route label for conditional branching
- DelayAgent: Buffer events and release them after a configurable delay
- TopicExtractAgent: Naive keyword/phrase extraction from event text
- FrequencyTrackerAgent: Track topic mention frequency/persistence over time
- HypeTermAgent: Build a trending-term snapshot from a noise-reference feed
- SignalScoreAgent: Score candidate topics as quiet-signal vs. hype/one-off

Action Agents:
- EmailAgent: Send via SMTP
- HTTPPostAgent: POST/PUT/PATCH/DELETE to URL
- JabberAgent: XMPP messaging
- APICallAgent: Comprehensive RESTful API calls (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)
- DiscordWebhookAgent: Send messages to Discord channels via webhooks
- MqttPublisherAgent: Publish events to MQTT topics (Mosquitto-compatible)
- SlackAgent: Send messages to Slack channels via Incoming Webhooks
- TelegramAgent: Send messages via the Telegram Bot API
- DataStoreWriteAgent: Write key-value data to the shared DataStore
- DropboxWriteAgent: Upload event content as a file to Dropbox
"""

# Import source agents
from app.agents.types.rss_agent import RSSAgent
from app.agents.types.web_fetch_agent import WebFetchAgent
from app.agents.types.scheduler_agent import SchedulerAgent
from app.agents.types.jabber_listener_agent import JabberListenerAgent
from app.agents.types.s3_bucket_monitor_agent import S3BucketMonitorAgent
from app.agents.types.imap_agent import IMAPAgent
from app.agents.types.webhook_agent import WebhookAgent
from app.agents.types.mqtt_subscriber_agent import MqttSubscriberAgent
from app.agents.types.datastore_read_agent import DataStoreReadAgent
from app.agents.types.dropbox_read_agent import DropboxReadAgent

# Import transform agents
from app.agents.types.filter_agent import FilterAgent
from app.agents.types.deduplication_agent import DeduplicationAgent
from app.agents.types.html_parser_agent import HTMLParserAgent
from app.agents.types.template_agent import TemplateAgent
from app.agents.types.jsonpath_agent import JSONPathAgent
from app.agents.types.aggregation_agent import AggregationAgent
from app.agents.types.csv_parser_agent import CSVParserAgent
from app.agents.types.router_agent import RouterAgent
from app.agents.types.delay_agent import DelayAgent
from app.agents.types.topic_extract_agent import TopicExtractAgent
from app.agents.types.frequency_tracker_agent import FrequencyTrackerAgent
from app.agents.types.hype_term_agent import HypeTermAgent
from app.agents.types.signal_score_agent import SignalScoreAgent

# Import action agents
from app.agents.types.email_agent import EmailAgent
from app.agents.types.http_post_agent import HTTPPostAgent
from app.agents.types.jabber_agent import JabberAgent
from app.agents.types.api_call_agent import APICallAgent
from app.agents.types.discord_webhook_agent import DiscordWebhookAgent
from app.agents.types.mqtt_publisher_agent import MqttPublisherAgent
from app.agents.types.slack_agent import SlackAgent
from app.agents.types.telegram_agent import TelegramAgent
from app.agents.types.datastore_write_agent import DataStoreWriteAgent
from app.agents.types.dropbox_write_agent import DropboxWriteAgent

__all__ = [
    # Source agents
    'RSSAgent',
    'WebFetchAgent',
    'SchedulerAgent',
    'JabberListenerAgent',
    'S3BucketMonitorAgent',
    'IMAPAgent',
    'WebhookAgent',
    'MqttSubscriberAgent',
    'DataStoreReadAgent',
    'DropboxReadAgent',
    # Transform agents
    'FilterAgent',
    'DeduplicationAgent',
    'HTMLParserAgent',
    'TemplateAgent',
    'JSONPathAgent',
    'AggregationAgent',
    'CSVParserAgent',
    'RouterAgent',
    'DelayAgent',
    'TopicExtractAgent',
    'FrequencyTrackerAgent',
    'HypeTermAgent',
    'SignalScoreAgent',
    # Action agents
    'EmailAgent',
    'HTTPPostAgent',
    'JabberAgent',
    'APICallAgent',
    'DiscordWebhookAgent',
    'MqttPublisherAgent',
    'SlackAgent',
    'TelegramAgent',
    'DataStoreWriteAgent',
    'DropboxWriteAgent',
]
