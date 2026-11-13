"""Regression cases for deterministic parsing without an external model."""
from unittest.mock import AsyncMock

import pytest

from app.services.fallback_search_service import FallbackSearchService


@pytest.fixture
def service():
    dictionary = AsyncMock()
    dictionary.resolve_city_name.return_value = None
    return FallbackSearchService(AsyncMock(), dictionary, AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [
    ("Концерт до 20:00", None),
    ("Концерт до 1000 рублей на двоих", 500),
    ("Концерт до 1 200 ₽", 1200),
    ("Концерт до 500 р", 500),
])
async def test_price_does_not_confuse_time(service, text, expected):
    result = await service.parse_free_text_deterministically(text)
    assert result.price_max == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [
    ("Фестиваль проводится 10 лет", None),
    ("С ребёнком 8 лет", 8),
    ("С ребенком", None),
])
async def test_age_requires_child_context(service, text, expected):
    result = await service.parse_free_text_deterministically(text)
    assert result.age_limit_max == expected


@pytest.mark.asyncio
async def test_this_week_ends_on_sunday(service):
    result = await service.parse_free_text_deterministically("на этой неделе")
    assert result.date_to.weekday() == 6
    assert 0 <= (result.date_to.date() - result.date_from.date()).days <= 6


@pytest.mark.asyncio
async def test_negated_free_is_not_set(service):
    result = await service.parse_free_text_deterministically("Не бесплатные концерты")
    assert result.is_free is None
