"""0001_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    # 2. ENUM types
    event_category_enum = postgresql.ENUM(
        "concert", "theater", "exhibition", "festival", "cinema", "excursion", "other",
        name="event_category_enum",
        create_type=False,
    )
    event_category_enum.create(op.get_bind(), checkfirst=True)

    source_type_enum = postgresql.ENUM(
        "manual", "import", "rss", "api", "page",
        name="source_type_enum",
        create_type=False,
    )
    source_type_enum.create(op.get_bind(), checkfirst=True)

    event_status_enum = postgresql.ENUM(
        "published", "draft", "cancelled",
        name="event_status_enum",
        create_type=False,
    )
    event_status_enum.create(op.get_bind(), checkfirst=True)

    moderation_reason_enum = postgresql.ENUM(
        "low_confidence", "missing_required_fields", "potential_duplicate", "prompt_injection_suspected", "manual_flag",
        name="moderation_reason_enum",
        create_type=False,
    )
    moderation_reason_enum.create(op.get_bind(), checkfirst=True)

    feedback_status_enum = postgresql.ENUM(
        "new", "processed", "rejected",
        name="feedback_status_enum",
        create_type=False,
    )
    feedback_status_enum.create(op.get_bind(), checkfirst=True)

    # 3. Table: cities
    op.create_table(
        "cities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lon", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.create_index("ix_cities_name", "cities", ["name"])
    op.create_index("ix_cities_normalized_name", "cities", ["normalized_name"])
    op.execute("CREATE INDEX ix_cities_norm_name_trgm ON cities USING gin (normalized_name gin_trgm_ops);")

    # 4. Table: venues
    op.create_table(
        "venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lon", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.UniqueConstraint("city_id", "normalized_name", name="uq_venue_city_norm_name"),
    )
    op.create_index("ix_venues_city_id", "venues", ["city_id"])
    op.create_index("ix_venues_normalized_name", "venues", ["normalized_name"])
    op.execute("CREATE INDEX ix_venues_norm_name_trgm ON venues USING gin (normalized_name gin_trgm_ops);")

    # 5. Table: events
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("category", event_category_enum, nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("date_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("venue", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lon", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("age_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("org_link", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False, server_default="1.00"),
        sa.Column("status", event_status_enum, nullable=False, server_default="published"),
        sa.Column("is_disputed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dispute_reason", moderation_reason_enum, nullable=True),
        sa.Column("dedup_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('russian', coalesce(description, '')), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # B-Tree indexes
    op.create_index("ix_events_status_city_date", "events", ["status", "city", "date_start"])
    op.create_index("ix_events_category", "events", ["category"])
    op.create_index("ix_events_date_start", "events", ["date_start"])
    op.create_index("ix_events_city", "events", ["city"])
    op.create_index("ix_events_venue", "events", ["venue"])
    op.create_index("ix_events_is_free", "events", ["is_free"])
    op.create_index("ix_events_age_limit", "events", ["age_limit"])
    op.create_index("ix_events_language", "events", ["language"])
    op.create_index("ix_events_dedup_key", "events", ["dedup_key"], unique=True)
    op.create_index("ix_events_is_disputed", "events", ["is_disputed"])

    # GIN indexes for TSVECTOR, TAGS, and Trigrams
    op.execute("CREATE INDEX ix_events_tsv ON events USING gin (tsv);")
    op.execute("CREATE INDEX ix_events_tags ON events USING gin (tags);")
    op.execute("CREATE INDEX ix_events_norm_title_trgm ON events USING gin (normalized_title gin_trgm_ops);")

    # HNSW index for embedding (cosine distance)
    op.execute(
        "CREATE INDEX ix_events_embedding_hnsw ON events "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);"
    )

    # 6. Table: raw_event_records
    op.create_table(
        "raw_event_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("imported_by", sa.String(length=100), nullable=True),
        sa.Column("processed_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_raw_event_records_source_hash", "raw_event_records", ["source_hash"], unique=True)
    op.create_index("ix_raw_event_records_processed_event_id", "raw_event_records", ["processed_event_id"])

    # 7. Table: event_sources
    op.create_table(
        "event_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_event_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_event_sources_event_id", "event_sources", ["event_id"])

    # 8. Table: subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_identifier", sa.String(length=128), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("category", event_category_enum, nullable=True),
        sa.Column("period_type", sa.String(length=32), nullable=False, server_default="all"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_identifier", "city", "category", name="uq_subscription_user_city_category"),
    )
    op.create_index("ix_subscriptions_user_identifier", "subscriptions", ["user_identifier"])
    op.create_index("ix_subscriptions_telegram_chat_id", "subscriptions", ["telegram_chat_id"])
    op.create_index("ix_subscriptions_city", "subscriptions", ["city"])
    op.create_index("ix_subscriptions_category", "subscriptions", ["category"])

    # 9. Table: feedback_requests
    op.create_table(
        "feedback_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sender_identifier", sa.String(length=128), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("status", feedback_status_enum, nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_requests_status", "feedback_requests", ["status"])
    op.create_index("ix_feedback_requests_created_at", "feedback_requests", ["created_at"])
    op.create_index("ix_feedback_requests_event_id", "feedback_requests", ["event_id"])

    # 10. Table: audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # 11. Table: agent_traces
    op.create_table(
        "agent_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("plan_steps", postgresql.JSONB(), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=False),
        sa.Column("grounding_event_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_rub", sa.Numeric(precision=8, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_traces_thread_id", "agent_traces", ["thread_id"])
    op.create_index("ix_agent_traces_created_at", "agent_traces", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_traces")
    op.drop_table("audit_logs")
    op.drop_table("feedback_requests")
    op.drop_table("subscriptions")
    op.drop_table("event_sources")
    op.drop_table("raw_event_records")
    op.drop_table("events")
    op.drop_table("venues")
    op.drop_table("cities")

    op.execute("DROP TYPE IF EXISTS feedback_status_enum;")
    op.execute("DROP TYPE IF EXISTS moderation_reason_enum;")
    op.execute("DROP TYPE IF EXISTS event_status_enum;")
    op.execute("DROP TYPE IF EXISTS source_type_enum;")
    op.execute("DROP TYPE IF EXISTS event_category_enum;")
