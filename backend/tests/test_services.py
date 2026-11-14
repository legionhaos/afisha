from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import pytest
from unittest.mock import AsyncMock

from app.models.enums import EventCategory, EventStatus, SourceType
from app.models.event import Event
from app.services.normalization_service import NormalizationService, YEKT_TZ
from app.services.deduplication_service import DeduplicationService
from app.services.fallback_search_service import FallbackSearchService


def test_normalization_service_title_clean():
    norm = NormalizationService()
    raw = '«Концерт: Волшебная флейта» в ДК'
    cleaned = norm.normalize_title(raw)
    assert cleaned == "Волшебная флейта в ДК"

    # Replace ё -> е
    raw_yo = "«Спектакль - Зелёная карета»"
    cleaned_yo = norm.normalize_title(raw_yo)
    assert cleaned_yo == "Зеленая карета"

    # Status/duplicate markings removal
    assert norm.normalize_title("Балет «Лебединое озеро» (Дубликат из другого источника)") == "Балет Лебединое озеро"
    assert norm.normalize_title("Спектакль «Женитьба Фигаро» (ОТМЕНЕНО)") == "Спектакль Женитьба Фигаро"
    assert norm.normalize_title("Концерт классики [ОТМЕНЕН]") == "Концерт классики"


def test_normalization_service_price_parsing():
    norm = NormalizationService()
    # Free
    assert norm.parse_price_text("Вход свободный") == (0, 0, True)
    assert norm.parse_price_text("Бесплатно") == (0, 0, True)
    assert norm.parse_price_text(0) == (0, 0, True)

    # Range
    assert norm.parse_price_text("от 300 до 800 ₽") == (300, 800, False)
    assert norm.parse_price_text("300-800 руб") == (300, 800, False)

    # Single
    assert norm.parse_price_text("500 руб.") == (500, 500, False)
    assert norm.parse_price_text("до 1000 ₽") == (0, 1000, False)


def test_normalization_service_age_scale():
    norm = NormalizationService()
    # Acceptable scale: 0, 6, 12, 16, 18
    assert norm.normalize_age_limit(0) == 0
    assert norm.normalize_age_limit("6+") == 6
    assert norm.normalize_age_limit("для детей 8 лет") == 12
    assert norm.normalize_age_limit("12+") == 12
    assert norm.normalize_age_limit("15 лет") == 16
    assert norm.normalize_age_limit("18+") == 18


def test_normalization_service_category_and_tags():
    norm = NormalizationService()
    cat, tags = norm.normalize_category(
        raw_category="Симфоническая музыка",
        title="Большой симфонический концерт для детей",
        description="Концерт классической музыки с Пушкинской картой",
    )
    assert cat == EventCategory.CONCERT
    assert "дети" in tags
    assert "классика" in tags
    assert "пушкинская_карта" in tags


def test_deduplication_service_build_dedup_key():
    dedup = DeduplicationService()
    dt = datetime(2026, 11, 14, 19, 0, tzinfo=YEKT_TZ)
    key1 = dedup.build_dedup_key("Уфа", "ГКЗ Башкортостан", dt, "симфонический концерт")
    key2 = dedup.build_dedup_key("уфа  ", " гкз башкортостан", dt, "симфонический концерт")
    assert key1 == key2
    assert len(key1) == 64


def test_deduplication_service_merge_fields():
    dedup = DeduplicationService()
    existing = Event(
        id=uuid4(),
        title="Концерт",
        normalized_title="концерт",
        category=EventCategory.CONCERT,
        date_start=datetime.now(timezone.utc),
        city="Уфа",
        venue="ГКЗ",
        address="Ленина",
        description="Краткое описание",
        tags=["концерт"],
        price_min=500,
        price_max=1000,
        source_url="https://source1.com",
        source_type=SourceType.IMPORT,
        source_hash="hash1",
        verified_at=datetime.now(timezone.utc),
        confidence=Decimal("1.0"),
        status=EventStatus.PUBLISHED,
        dedup_key="key1",
        org_link=None,
    )
    incoming = {
        "description": "Очень подробное длинное описание концерта музыкантов",
        "tags": ["музыка", "классика"],
        "org_link": "https://tickets.org/1",
    }
    merged = dedup.merge_event_fields(existing, incoming)
    assert "Очень подробное" in merged["description"]
    assert "классика" in merged["tags"]
    assert merged["org_link"] == "https://tickets.org/1"


@pytest.mark.asyncio
async def test_fallback_search_service_parsing():
    mock_catalog = AsyncMock()
    mock_dict = AsyncMock()
    mock_dict.get_all_cities.return_value = [SimpleNamespace(name="Стерлитамак")]
    mock_audit = AsyncMock()

    service = FallbackSearchService(mock_catalog, mock_dict, mock_audit)

    query = "Куда пойти в субботу с ребенком 8 лет в стерлитамаке до 1000 рублей?"
    filters = await service.parse_free_text_deterministically(query)

    assert filters.city == "Стерлитамак"
    assert filters.price_max == 1000
    assert filters.age_limit_max == 8
    assert filters.date_from is not None
    assert filters.date_to is not None
