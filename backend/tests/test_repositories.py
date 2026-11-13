import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from app.models.enums import EventCategory, EventStatus, SourceType
from app.models.event import Event
from app.schemas.event import EventSearchFilterDTO
from app.repositories.event_repo import EventRepository
from app.repositories.dictionary_repo import DictionaryRepository
from app.repositories.subscription_repo import SubscriptionRepository


@pytest.mark.asyncio
async def test_event_repo_build_base_filters():
    mock_session = AsyncMock()
    repo = EventRepository(mock_session)

    filters = EventSearchFilterDTO(
        city="Уфа",
        category=EventCategory.CONCERT,
        price_max=1000,
        is_free=False,
        age_limit_max=12,
    )
    clauses = repo._build_base_filters(filters)
    # Check that clauses contain status, city, category, price_min, age_limit
    assert len(clauses) >= 4


@pytest.mark.asyncio
async def test_event_repo_create_or_update_event_dedup():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = EventRepository(mock_session)

    # 1. Existing event found by dedup_key -> should merge
    existing_event = Event(
        id=uuid4(),
        title="Спектакль",
        normalized_title="спектакль",
        category=EventCategory.THEATER,
        date_start=datetime.now(timezone.utc),
        city="Уфа",
        venue="Башдрам",
        address="ул. Заки Валиди",
        description="Краткое описание",
        tags=["театр"],
        price_min=300,
        price_max=800,
        source_url="https://source1.com",
        source_type=SourceType.IMPORT,
        source_hash="hash1",
        verified_at=datetime.now(timezone.utc),
        confidence=Decimal("1.0"),
        status=EventStatus.PUBLISHED,
        dedup_key="dedup_123",
    )
    repo.get_by_dedup_key = AsyncMock(return_value=existing_event)

    incoming_data = {
        "title": "Спектакль в театре",
        "description": "Очень подробное длинное описание спектакля",
        "tags": ["драма", "театр"],
        "source_url": "https://source2.com",
        "source_type": SourceType.API,
        "source_hash": "hash2",
        "dedup_key": "dedup_123",
    }
    event, action = await repo.create_or_update_event(incoming_data)
    assert action == "merged"
    assert "Очень подробное длинное описание спектакля" in event.description
    assert "драма" in event.tags
