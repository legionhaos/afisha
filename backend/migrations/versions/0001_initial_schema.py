"""Create the initial application schema.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE TYPE eventcategory AS ENUM ('CONCERT', 'THEATER', 'EXHIBITION', 'FESTIVAL', 'CINEMA', 'EXCURSION', 'OTHER')")
    op.execute("CREATE TYPE sourcetype AS ENUM ('MANUAL', 'IMPORT', 'RSS', 'API', 'PAGE')")
    op.execute("CREATE TYPE eventstatus AS ENUM ('PUBLISHED', 'DRAFT', 'CANCELLED')")
    op.execute("CREATE TYPE subscriptionchannel AS ENUM ('TELEGRAM', 'WEB')")
    op.execute('CREATE TABLE audit_logs (\n\tid UUID NOT NULL, \n\tactor VARCHAR(120) NOT NULL, \n\taction VARCHAR(64) NOT NULL, \n\tentity_type VARCHAR(64) NOT NULL, \n\tentity_id VARCHAR(64) NOT NULL, \n\tdiff_json JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)')
    op.execute('CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at)')
    op.execute('CREATE INDEX ix_audit_logs_entity_id ON audit_logs (entity_id)')
    op.execute('CREATE TABLE agent_traces (\n\tid UUID NOT NULL, \n\tthread_id VARCHAR(128) NOT NULL, \n\tuser_identifier_hash VARCHAR(64) NOT NULL, \n\tuser_query TEXT NOT NULL, \n\textracted_plan JSONB NOT NULL, \n\ttool_calls_log JSONB NOT NULL, \n\tevidence_event_ids UUID[] NOT NULL, \n\tfinal_response TEXT NOT NULL, \n\tlatency_ms INTEGER NOT NULL, \n\tprompt_tokens INTEGER NOT NULL, \n\tcompletion_tokens INTEGER NOT NULL, \n\tcost_rub NUMERIC(10, 4) NOT NULL, \n\tfallback_used BOOLEAN NOT NULL, \n\tinjection_blocked BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)')
    op.execute('CREATE INDEX ix_agent_traces_user_identifier_hash ON agent_traces (user_identifier_hash)')
    op.execute('CREATE INDEX ix_agent_traces_thread_id ON agent_traces (thread_id)')
    op.execute('CREATE INDEX ix_agent_traces_created_at ON agent_traces (created_at)')
    op.execute('CREATE TABLE cities (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(120) NOT NULL, \n\tnormalized_name VARCHAR(120) NOT NULL, \n\tcenter_lat NUMERIC(9, 6) NOT NULL, \n\tcenter_lon NUMERIC(9, 6) NOT NULL, \n\tPRIMARY KEY (id)\n)')
    op.execute('CREATE INDEX ix_cities_normalized_name ON cities (normalized_name)')
    op.execute('CREATE INDEX ix_cities_normalized_name_trgm ON cities USING gin (normalized_name gin_trgm_ops)')
    op.execute('CREATE UNIQUE INDEX ix_cities_name ON cities (name)')
    op.execute("CREATE TABLE events (\n\tid UUID NOT NULL, \n\ttitle TEXT NOT NULL, \n\tnormalized_title TEXT NOT NULL, \n\tcategory eventcategory NOT NULL, \n\ttags TEXT[] NOT NULL, \n\tdate_start TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdate_end TIMESTAMP WITH TIME ZONE, \n\tduration_min INTEGER, \n\tcity VARCHAR(120) NOT NULL, \n\tvenue VARCHAR(255) NOT NULL, \n\taddress TEXT NOT NULL, \n\tlat NUMERIC(9, 6), \n\tlon NUMERIC(9, 6), \n\tdescription TEXT NOT NULL, \n\tprice_min INTEGER NOT NULL, \n\tprice_max INTEGER NOT NULL, \n\tis_free BOOLEAN NOT NULL, \n\tage_limit INTEGER NOT NULL, \n\tlanguage VARCHAR(64), \n\torg_link TEXT, \n\tsource_url TEXT NOT NULL, \n\tsource_type sourcetype NOT NULL, \n\tsource_hash VARCHAR(64) NOT NULL, \n\tverified_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconfidence NUMERIC(3, 2) NOT NULL, \n\tstatus eventstatus NOT NULL, \n\tdedup_key VARCHAR(128) NOT NULL, \n\tis_disputed BOOLEAN NOT NULL, \n\tdispute_reason TEXT, \n\ttsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('russian'::regconfig, coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(venue, ''))) STORED NOT NULL, \n\tembedding VECTOR(1536), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_events_age_limit CHECK (age_limit IN (0, 6, 12, 16, 18)), \n\tUNIQUE (source_hash)\n)")
    op.execute('CREATE INDEX ix_events_is_disputed ON events (is_disputed)')
    op.execute('CREATE INDEX ix_events_normalized_title ON events (normalized_title)')
    op.execute('CREATE INDEX ix_events_city ON events (city)')
    op.execute('CREATE INDEX ix_events_category ON events (category)')
    op.execute('CREATE INDEX ix_events_status ON events (status)')
    op.execute('CREATE UNIQUE INDEX ix_events_dedup_key ON events (dedup_key)')
    op.execute('CREATE INDEX ix_events_normalized_title_trgm ON events USING gin (normalized_title gin_trgm_ops)')
    op.execute('CREATE INDEX ix_events_embedding_hnsw ON events USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)')
    op.execute('CREATE INDEX ix_events_age_limit ON events (age_limit)')
    op.execute('CREATE INDEX ix_events_language ON events (language)')
    op.execute('CREATE INDEX ix_events_tags_gin ON events USING gin (tags)')
    op.execute('CREATE INDEX ix_events_tsv_gin ON events USING gin (tsv)')
    op.execute('CREATE INDEX ix_events_date_start ON events (date_start)')
    op.execute('CREATE INDEX ix_events_venue ON events (venue)')
    op.execute('CREATE INDEX ix_events_is_free ON events (is_free)')
    op.execute('CREATE TABLE subscriptions (\n\tid UUID NOT NULL, \n\tchannel subscriptionchannel NOT NULL, \n\tuser_identifier VARCHAR(128) NOT NULL, \n\tcity VARCHAR(120) NOT NULL, \n\tcategory eventcategory, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_subscriptions_identity UNIQUE NULLS NOT DISTINCT (channel, user_identifier, city, category)\n)')
    op.execute('CREATE INDEX ix_subscriptions_user_identifier ON subscriptions (user_identifier)')
    op.execute('CREATE TABLE venues (\n\tid SERIAL NOT NULL, \n\tcity_id INTEGER NOT NULL, \n\tname VARCHAR(255) NOT NULL, \n\tnormalized_name VARCHAR(255) NOT NULL, \n\taddress TEXT NOT NULL, \n\tlat NUMERIC(9, 6), \n\tlon NUMERIC(9, 6), \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(city_id) REFERENCES cities (id)\n)')
    op.execute('CREATE INDEX ix_venues_normalized_name ON venues (normalized_name)')
    op.execute('CREATE INDEX ix_venues_normalized_name_trgm ON venues USING gin (normalized_name gin_trgm_ops)')
    op.execute('CREATE INDEX ix_venues_city_id ON venues (city_id)')
    op.execute('CREATE TABLE raw_event_records (\n\tid UUID NOT NULL, \n\tevent_id UUID, \n\tsource_type sourcetype NOT NULL, \n\tsource_url TEXT NOT NULL, \n\tsource_hash VARCHAR(64) NOT NULL, \n\traw_payload JSONB NOT NULL, \n\tingested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(event_id) REFERENCES events (id) ON DELETE SET NULL\n)')
    op.execute('CREATE INDEX ix_raw_event_records_event_id ON raw_event_records (event_id)')
    op.execute('CREATE UNIQUE INDEX ix_raw_event_records_source_hash ON raw_event_records (source_hash)')
    op.execute('CREATE TABLE feedback_tickets (\n\tid UUID NOT NULL, \n\tevent_id UUID, \n\torganizer_contact VARCHAR(255) NOT NULL, \n\tmessage TEXT NOT NULL, \n\tis_processed BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(event_id) REFERENCES events (id) ON DELETE SET NULL\n)')


def downgrade() -> None:
    op.execute("DROP TABLE venues")
    op.execute("DROP TABLE raw_event_records")
    op.execute("DROP TABLE feedback_tickets")
    op.execute("DROP TABLE subscriptions")
    op.execute("DROP TABLE events")
    op.execute("DROP TABLE cities")
    op.execute("DROP TABLE audit_logs")
    op.execute("DROP TABLE agent_traces")
    op.execute("DROP TYPE subscriptionchannel")
    op.execute("DROP TYPE sourcetype")
    op.execute("DROP TYPE eventstatus")
    op.execute("DROP TYPE eventcategory")
