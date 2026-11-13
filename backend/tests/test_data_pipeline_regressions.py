from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.models.enums import EventStatus, SourceType
from app.repositories.event_repo import EventRepository
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


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["до 1200", "от 300", "неизвестно", "-500", "500.50", "900-300", "бесплатно 500"])
async def test_incomplete_prices_are_not_published(price):
    svc = service()
    report = await svc.import_file(__import__("json").dumps([payload(price=price)], ensure_ascii=False).encode(), "events.json", "test", "request")
    assert report.rejected_count == 1
    svc.event_repo.create_or_update_event.assert_not_awaited()


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


def test_age_is_not_inferred_from_arbitrary_description_numbers():
    norm = NormalizationService()
    assert norm.normalize_age_limit(None, "Концерт начинается в 19:00, билеты от 500 рублей") == 0
    assert norm.normalize_age_limit("для детей 8 лет") == 12
    with pytest.raises(ValueError):
        norm.normalize_age_limit("неизвестно")
    with pytest.raises(ValueError):
        norm.normalize_age_limit(-1)


def test_hard_duration_filter_excludes_unknown_duration():
    repo = EventRepository(AsyncMock())
    clauses = repo._build_base_filters(EventSearchFilterDTO(max_duration_min=90))
    compiled = " ".join(str(x.compile(dialect=postgresql.dialect())) for x in clauses)
    assert "duration_min <=" in compiled
    assert "duration_min IS NULL" not in compiled
