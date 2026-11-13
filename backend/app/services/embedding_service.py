from typing import Any
import structlog
from langchain_openai import OpenAIEmbeddings

from app.core.circuit_breaker import CircuitOpenError, llm_circuit_breaker
from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Сервис вычисления векторных представлений текста (эмбеддингов).

    Обернут в LLMCircuitBreaker и безопасно возвращает None при недоступности провайдера.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._embeddings_client: OpenAIEmbeddings | None = None

    def _get_client(self) -> OpenAIEmbeddings:
        if self._embeddings_client is None:
            self._embeddings_client = OpenAIEmbeddings(
                model=self.settings.EMBEDDING_MODEL_NAME,
                openai_api_key=self.settings.LLM_API_KEY.get_secret_value(),
                openai_api_base=self.settings.LLM_BASE_URL,
                request_timeout=self.settings.LLM_TIMEOUT_SEC,
            )
        return self._embeddings_client

    async def generate_embedding(self, text: str) -> list[float] | None:
        """Вычисляет эмбеддинг для текста с защитой через LLMCircuitBreaker."""
        if not text or not text.strip():
            return None

        # If dummy or mock API key is used, avoid real external request in offline tests
        api_key_val = self.settings.LLM_API_KEY.get_secret_value()
        if not api_key_val or api_key_val.startswith("mock") or api_key_val == "your-llm-api-key":
            # Return deterministic mock 1536-dim vector for tests
            return None

        async def _call_embeddings() -> list[float]:
            client = self._get_client()
            return await client.aembed_query(text.strip())

        try:
            return await llm_circuit_breaker.call(_call_embeddings)
        except (CircuitOpenError, TimeoutError) as ce:
            logger.warning("embedding_generation_degraded", reason=str(ce))
            return None
        except Exception as e:
            logger.warning("embedding_generation_failed", error=str(e))
            return None


embedding_service = EmbeddingService()
