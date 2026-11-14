from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.models.enums import EventCategory, EventStatus
from app.repositories.event_repo import EventRepository
from app.repositories.raw_record_repo import RawRecordRepository
from app.schemas.event import EventSearchFilterDTO
from app.schemas.import_mod import ImportReportDTO
from app.services.deduplication_service import DeduplicationService
from app.services.import_service import ImportService
from app.services.normalization_service import NormalizationService


def payload(**overrides):
    data = {
        "title": "Тестовый концерт", "date_start": "2027-01-01T19:00:00+05:00",
        "city": "Уфа", "venue": "Зал", "address": "Тестовая улица 1",
        "description": "Тестовое описание концертного мероприятия",
        "source_url": "https://example.org/test", "price": "500",
    }
    return data | overrides


def service():
    event_repo, raw_repo, dictionary, audit, embedding = (AsyncMock() for _ in range(5))
    dictionary.resolve_city_name.return_value = "Уфа"
    raw_repo.get_by_hash.return_value = None
    raw_repo.save_raw_record.return_value = SimpleNamespace(id=uuid4())
    embedding.generate_embedding.return_value = None
    svc = ImportService(event_repo, raw_repo, dictionary, audit, NormalizationService(), DeduplicationService(), embedding)
    return svc


@pytest.mark.parametrize("filename,content", [
    ("events.json", b'{"events": "not a list"}'),
    ("events.json", b'[1, 2]'),
    ("events.csv", b'title,title\nfirst,second\n'),
    ("events.csv", b'title\na,b\n'),
    ("events.txt", b'title\nevent\n'),
])
def test_invalid_import_file_is_rejected(filename, content):
    with pytest.raises(ValueError):
        service()._parse_file_to_rows(content, filename)


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["до 1200", "от 300", "неизвестно", "-500", "500.50", "900-300", "бесплатно 500"])
async def test_incomplete_prices_are_not_published(price):
    svc = service()
    report = await svc.import_file(__import__("json").dumps([payload(price=price)], ensure_ascii=False).encode(), "events.json", "test", "request")
    assert report.rejected_count == 1
    svc.event_repo.create_or_update_event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"status": "draft"}, {"url_verified": False}])
async def test_crawler_unverified_records_remain_drafts(extra):
    svc = service()
    svc.event_repo.create_or_update_event.return_value = (SimpleNamespace(id=uuid4()), "added")
    report = ImportReportDTO()
    await svc._process_single_row(payload(**extra), 1, "test", "request", report)
    data = svc.event_repo.create_or_update_event.await_args.kwargs["event_data"]
    assert data["status"] == EventStatus.DRAFT
    assert data["is_disputed"] is True
    assert report.flagged_for_moderation_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [
    {"lat": "91"}, {"lon": "181"}, {"lat": "NaN"},
    {"duration_min": -10}, {"duration_min": 0}, {"duration_min": "1.5"},
])
async def test_invalid_coordinates_and_duration_are_rejected(extra):
    svc = service()
    report = await svc.import_file(__import__("json").dumps([payload(**extra)], ensure_ascii=False).encode(), "events.json", "test", "request")
    assert report.rejected_count == 1
    svc.event_repo.create_or_update_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_zero_coordinates_are_preserved():
    svc = service()
    svc.event_repo.create_or_update_event.return_value = (SimpleNamespace(id=uuid4()), "added")
    report = ImportReportDTO()
    await svc._process_single_row(payload(lat=0, lon=0), 1, "test", "request", report)
    data = svc.event_repo.create_or_update_event.await_args.kwargs["event_data"]
    assert data["lat"] == 0 and data["lon"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("price", [0, "0", "0 рублей"])
async def test_zero_price_remains_free(price):
    svc = service()
    svc.event_repo.create_or_update_event.return_value = (SimpleNamespace(id=uuid4()), "added")
    report = ImportReportDTO()
    await svc._process_single_row(payload(price=price), 1, "test", "request", report)
    assert report.added_count == 1
    data = svc.event_repo.create_or_update_event.await_args.kwargs["event_data"]
    assert (data["price_min"], data["price_max"], data["is_free"]) == (0, 0, True)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_date", ["неизвестно", "2027-02-30", "2027-13-01"])
async def test_invalid_dates_are_not_replaced_with_now(bad_date):
    svc = service()
    report = await svc.import_file(__import__("json").dumps([payload(date_start=bad_date)], ensure_ascii=False).encode(), "events.json", "test", "request")
    assert report.rejected_count == 1
    svc.event_repo.create_or_update_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_before_start_is_rejected():
    svc = service()
    event = payload(date_end="2026-12-31T19:00:00+05:00")
    report = await svc.import_file(__import__("json").dumps([event], ensure_ascii=False).encode(), "events.json", "test", "request")
    assert report.rejected_count == 1
    assert "Дата окончания" in report.errors[0].reason
    svc.event_repo.create_or_update_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_reuses_source_and_preserves_cancellation():
    svc = service()
    raw = SimpleNamespace(id=uuid4(), source_hash="a" * 64, processed_event_id=uuid4(), raw_payload=payload())
    dedup_key = svc.dedup_service.build_dedup_key("Уфа", "Зал", svc.norm_service.parse_date_to_yekaterinburg(raw.raw_payload["date_start"]), svc.norm_service.normalize_title(raw.raw_payload["title"]).lower())
    event = SimpleNamespace(id=raw.processed_event_id, dedup_key=dedup_key, description="old", tags=[], org_link=None, lat=None, lon=None, date_end=None, duration_min=None, status=EventStatus.CANCELLED, is_disputed=False, dispute_reason=None)
    svc.event_repo.get_by_id.return_value = event
    report = ImportReportDTO()
    await svc._process_single_row(raw.raw_payload, 1, "test", "request", report, replay_record=raw)
    assert report.updated_count == 1
    assert event.status == EventStatus.CANCELLED
    assert event.description == raw.raw_payload["description"]
    svc.raw_repo.save_raw_record.assert_not_awaited()
    svc.event_repo.create_or_update_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_propagates_database_failures():
    svc = service()
    raw = SimpleNamespace(id=uuid4(), source_hash="a" * 64, processed_event_id=uuid4(), raw_payload=payload())

    async def batches(batch_size):
        yield [raw]

    svc.raw_repo.list_all_for_replay = batches
    svc.event_repo.get_by_id.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await svc.replay_all_normalizations("test", "request")


def test_deduplication_preserves_existing_organizer_link():
    event = SimpleNamespace(description="Описание", tags=[], org_link="https://example.org/original", lat=None, lon=None, date_end=None, duration_min=None)
    merged = DeduplicationService().merge_event_fields(event, {"org_link": "https://example.org/other"})
    assert merged["org_link"] == "https://example.org/original"


@pytest.mark.parametrize("raw,title,description,expected", [
    ("theater", "Музыкальная комедия", "Музыка и песни", EventCategory.THEATER),
    ("concert", "Концерт", "В театре", EventCategory.CONCERT),
    ("выставка", "Концерт в музее", "Музыка", EventCategory.EXHIBITION),
    ("festival", "Фестиваль", "Концерты", EventCategory.FESTIVAL),
])
def test_explicit_category_takes_precedence(raw, title, description, expected):
    category, _ = NormalizationService().normalize_category(raw, title, description)
    assert category == expected


def test_age_is_not_inferred_from_arbitrary_description_numbers():
    norm = NormalizationService()
    assert norm.normalize_age_limit(None, "Концерт начинается в 19:00, билеты от 500 рублей") == 0
    assert norm.normalize_age_limit("для детей 8 лет") == 12
    with pytest.raises(ValueError):
        norm.normalize_age_limit("неизвестно")
    with pytest.raises(ValueError):
        norm.normalize_age_limit(-1)


@pytest.mark.asyncio
async def test_text_search_candidate_gate_includes_trigram_matching():
    session = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = []
    session.execute.side_effect = [count_result, rows_result]
    await EventRepository(session).hybrid_search(EventSearchFilterDTO(query_text="концерт"))
    sql = str(session.execute.await_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    assert "events.normalized_title %%" in sql


@pytest.mark.asyncio
async def test_diagnostics_uses_same_topic_gate_as_search():
    session = AsyncMock()
    row = MagicMock()
    row._mapping = {"price": 0}
    result = MagicMock()
    result.one.return_value = row
    session.execute.return_value = result
    await EventRepository(session).diagnose_blocking_constraints(
        EventSearchFilterDTO(query_text="хоккей", price_max=100)
    )
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "plainto_tsquery" in sql and "websearch_to_tsquery" in sql
    assert "events.normalized_title %%" in sql


@pytest.mark.asyncio
async def test_similar_events_require_category_or_close_vector():
    repo = EventRepository(AsyncMock())
    repo.session.execute.return_value = MagicMock()
    repo.session.execute.return_value.scalars.return_value.all.return_value = []
    base = SimpleNamespace(id=uuid4(), city="Уфа", category=EventCategory.CONCERT, embedding=[1.0] + [0.0] * 1535)
    await repo.find_similar_events(base)
    statement = repo.session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "events.category =" in sql and "<=>" in sql and " <= " in sql
    assert "NULLS LAST" in sql


@pytest.mark.asyncio
async def test_replay_pagination_uses_stable_timestamp_and_id_cursor():
    session = AsyncMock()
    timestamp = datetime(2027, 1, 1, tzinfo=timezone.utc)
    records = [SimpleNamespace(created_at=timestamp, id=uuid4()) for _ in range(3)]
    responses = []
    for batch in (records[:2], records[2:], []):
        result = MagicMock()
        result.scalars.return_value.all.return_value = batch
        responses.append(result)
    session.execute.side_effect = responses
    batches = [batch async for batch in RawRecordRepository(session).list_all_for_replay(batch_size=2)]
    assert batches == [records[:2], records[2:]]
    sql = str(session.execute.await_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "raw_event_records.created_at, raw_event_records.id" in sql
    assert " OFFSET " not in sql


def test_hard_duration_filter_excludes_unknown_duration():
    repo = EventRepository(AsyncMock())
    clauses = repo._build_base_filters(EventSearchFilterDTO(max_duration_min=90))
    compiled = " ".join(str(x.compile(dialect=postgresql.dialect())) for x in clauses)
    assert "duration_min <=" in compiled
    assert "duration_min IS NULL" not in compiled
