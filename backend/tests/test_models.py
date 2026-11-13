import pytest
from app.models import (
    Base,
    City,
    Venue,
    RawEventRecord,
    Event,
    EventSource,
    Subscription,
    FeedbackRequest,
    AuditLog,
    AgentTrace,
)


def test_base_metadata_contains_all_tables():
    expected_tables = {
        "cities",
        "venues",
        "raw_event_records",
        "events",
        "event_sources",
        "subscriptions",
        "feedback_requests",
        "audit_logs",
        "agent_traces",
    }
    assert expected_tables == set(Base.metadata.tables.keys())


def test_event_model_specific_columns():
    events_table = Base.metadata.tables["events"]
    # Check generated TSVECTOR column
    assert "tsv" in events_table.columns
    # Check Vector column
    assert "embedding" in events_table.columns
    # Check unique dedup_key
    assert "dedup_key" in events_table.columns
    assert events_table.columns["dedup_key"].unique is True


def test_subscriptions_table_bigint_telegram_chat_id():
    sub_table = Base.metadata.tables["subscriptions"]
    # telegram_chat_id must be BigInteger for 64-bit Telegram user IDs
    assert str(sub_table.columns["telegram_chat_id"].type).upper() == "BIGINT"
