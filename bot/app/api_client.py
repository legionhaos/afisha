from typing import Any
from urllib.parse import quote

import httpx


class APIError(Exception):
    def __init__(self, status: int | None = None) -> None:
        self.status = status
        super().__init__(f"API error: {status}")

    @property
    def user_message(self) -> str:
        if self.status == 404:
            return "Данные не найдены или уже недоступны."
        if self.status == 422:
            return "Сервис не принял параметры запроса. Проверьте их и попробуйте ещё раз."
        if self.status == 429:
            return "Слишком много запросов. Попробуйте немного позже."
        return "Сервис временно недоступен. Попробуйте позже."


class APIClient:
    def __init__(self, base_url: str, timeout: float = 20, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(base_url=base_url.rstrip('/') + '/', timeout=timeout, transport=transport)

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self.client.request(method, path.lstrip('/'), **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise APIError(exc.response.status_code) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise APIError() from exc

    async def events(self, filters: dict[str, Any]) -> dict[str, Any]:
        return await self.request('GET', 'events', params=filters)

    async def event(self, event_id: str) -> dict[str, Any]:
        return await self.request('GET', f'events/{quote(event_id, safe="")}')

    async def dictionaries(self, city: str | None = None) -> dict[str, Any]:
        return await self.request('GET', 'dictionaries', params={'city': city} if city else {})

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request('POST', 'chat', json=payload)

    async def subscriptions(self, user: str) -> list[dict[str, Any]]:
        return await self.request('GET', 'subscriptions', params={'user_identifier': user})

    async def subscribe(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request('POST', 'subscriptions', json=payload)

    async def unsubscribe(self, user: str, subscription_id: str | None = None) -> dict[str, Any]:
        params = {'subscription_id': subscription_id} if subscription_id else {}
        return await self.request('DELETE', f'subscriptions/{quote(user, safe="")}', params=params)
