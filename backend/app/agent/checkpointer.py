import os
from typing import Any
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

# Ensure LANGGRAPH_STRICT_MSGPACK is enabled for security
os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"


def trim_conversation_history(
    messages: list[BaseMessage],
    min_turns: int = 5,
    max_messages: int = 14,
) -> list[BaseMessage]:
    """Обрезает историю сообщений, сохраняя системный промпт и не менее 5 реплик (10-14 сообщений)."""
    if not messages:
        return []

    system_msgs: list[BaseMessage] = []
    other_msgs: list[BaseMessage] = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_msgs.append(msg)
        else:
            other_msgs.append(msg)

    # Оставляем последние max_messages сообщений
    if len(other_msgs) > max_messages:
        trimmed = other_msgs[-max_messages:]
    else:
        trimmed = other_msgs

    return system_msgs + trimmed


class CheckpointerManager:
    """Управление чекпоинтером состояний диалогов LangGraph на базе AsyncPostgresSaver."""

    @staticmethod
    def get_checkpointer(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
        """Создает экземпляр AsyncPostgresSaver на основе пула соединений psycopg_pool."""
        return AsyncPostgresSaver(pool)
