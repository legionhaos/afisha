"""Generate optional search embeddings without making search depend on an LLM."""

import math
from typing import Any

from app.core.circuit_breaker import CircuitOpenError, LLMCircuitBreaker


class EmbeddingService:
    def __init__(self, client: Any, model_name: str, circuit_breaker: LLMCircuitBreaker) -> None:
        self.client = client
        self.model_name = model_name
        self.circuit_breaker = circuit_breaker

    async def generate_embedding(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        try:
            response = await self.circuit_breaker.call(
                self.client.embeddings.create, model=self.model_name, input=text
            )
            vector = response.data[0].embedding
            if len(vector) != 1536 or any(not math.isfinite(float(value)) for value in vector):
                return None
            return [float(value) for value in vector]
        except (CircuitOpenError, AttributeError, IndexError, TypeError, ValueError, OverflowError):
            return None
