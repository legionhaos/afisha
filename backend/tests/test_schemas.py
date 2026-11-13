from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from pydantic import ValidationError

from app.models.enums import EventCategory, EventStatus, SourceType
from app.schemas.event import EventCardDTO, EventCreateDTO
from app.schemas.common import ProblemDetails
from app.schemas.import_mod import ImportReportDTO, ImportReportItemErrorDTO
from app.schemas.chat import ChatMessageResponseDTO, AgentRecommendationItemDTO

YEKT_TZ = timezone(timedelta(hours=5))


def test_event_create_validation_age_and_prices():
    valid_dt = datetime.now(YEKT_TZ)

    # Valid event
    evt = EventCreateDTO(
        title="Симфонический концерт",
        category=EventCategory.CONCERT,
        date_start=valid_dt,
        city="Уфа",
        venue="ГКЗ Башкортостан",
        address="ул. Ленина, 50",
        description="Прекрасный вечер классической музыки",
        price_min=500,
        price_max=1500,
        age_limit=6,
        source_url="https://example.com/event/1",
    )
    assert evt.age_limit == 6
    assert evt.price_min == 500
    assert evt.price_max == 1500

    # Invalid age_limit
    with pytest.raises(ValidationError) as exc_info:
        EventCreateDTO(
            title="Концерт",
            category=EventCategory.CONCERT,
            date_start=valid_dt,
            city="Уфа",
            venue="ДК",
            address="ул. Ленина, 1",
            description="Описание концерта",
            age_limit=7,  # invalid: must be 0, 6, 12, 16, 18
            source_url="https://example.com",
        )
    assert "Возрастное ограничение должно быть одним из" in str(exc_info.value)

    # Invalid price_max < price_min
    with pytest.raises(ValidationError) as exc_info2:
        EventCreateDTO(
            title="Концерт",
            category=EventCategory.CONCERT,
            date_start=valid_dt,
            city="Уфа",
            venue="ДК",
            address="ул. Ленина, 1",
            description="Описание концерта",
            price_min=1000,
            price_max=500,
            age_limit=12,
            source_url="https://example.com",
        )
    assert "не может быть меньше price_min" in str(exc_info2.value)


def test_event_card_cancelled_badge():
    valid_dt = datetime.now(YEKT_TZ)
    card = EventCardDTO(
        id=uuid4(),
        title="Отмененный спектакль",
        category=EventCategory.THEATER,
        date_start=valid_dt,
        city="Стерлитамак",
        venue="Русский драматический театр",
        address="ул. Худайбердина, 18",
        description="Спектакль отменен театром по техническим причинам",
        price_min=0,
        price_max=0,
        is_free=True,
        age_limit=12,
        source_url="https://example.com/theatre/1",
        status=EventStatus.CANCELLED,
        cancelled_badge="⚠️ Мероприятие отменено организатором",
        verified_at=valid_dt,
    )
    assert card.status == EventStatus.CANCELLED
    assert card.cancelled_badge is not None


def test_import_report_dto():
    report = ImportReportDTO(
        total_received=10,
        added_count=6,
        updated_count=2,
        deduplicated_merged_count=1,
        flagged_for_moderation_count=0,
        rejected_count=1,
        errors=[
            ImportReportItemErrorDTO(row_index=5, raw_title="Без даты", reason="Отсутствует обязательное поле date_start")
        ],
    )
    assert report.total_received == 10
    assert len(report.errors) == 1
    assert report.errors[0].row_index == 5
