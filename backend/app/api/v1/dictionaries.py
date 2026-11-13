from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_dict_repo
from app.repositories.dictionary_repo import DictionaryRepository
from app.schemas.dictionary import (
    CategoryStatsDTO,
    CityDTO,
    DictionariesResponseDTO,
    VenueDTO,
)

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])


@router.get(
    "",
    response_model=DictionariesResponseDTO,
    summary="Сводные справочники городов, площадок и категорий",
)
async def get_all_dictionaries(
    response: Response,
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
    city: str | None = Query(default=None, description="Фильтр площадок по городу"),
) -> DictionariesResponseDTO:
    cities = await dict_repo.get_all_cities()
    venues = await dict_repo.get_venues_by_city(city)
    cat_stats = await dict_repo.get_categories_stats(city)

    response.headers["Cache-Control"] = "public, max-age=3600"

    return DictionariesResponseDTO(
        cities=[CityDTO.model_validate(c) for c in cities],
        venues=[VenueDTO.model_validate(v) for v in venues],
        categories=[CategoryStatsDTO.model_validate(cs) for cs in cat_stats],
    )


@router.get(
    "/cities",
    response_model=list[CityDTO],
    summary="Справочник городов Республики Башкортостан",
)
async def get_cities(
    response: Response,
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
) -> list[CityDTO]:
    cities = await dict_repo.get_all_cities()
    response.headers["Cache-Control"] = "public, max-age=3600"
    return [CityDTO.model_validate(c) for c in cities]


@router.get(
    "/venues",
    response_model=list[VenueDTO],
    summary="Справочник площадок",
)
async def get_venues(
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
    city: str | None = Query(default=None),
) -> list[VenueDTO]:
    venues = await dict_repo.get_venues_by_city(city)
    return [VenueDTO.model_validate(v) for v in venues]


@router.get(
    "/categories",
    response_model=list[CategoryStatsDTO],
    summary="Справочник категорий с подсчетом активных мероприятий",
)
async def get_categories(
    dict_repo: Annotated[DictionaryRepository, Depends(get_dict_repo)],
    city: str | None = Query(default=None),
) -> list[CategoryStatsDTO]:
    stats = await dict_repo.get_categories_stats(city)
    return [CategoryStatsDTO.model_validate(cs) for cs in stats]
