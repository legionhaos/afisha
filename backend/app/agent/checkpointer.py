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

    # Preserve complete human/tool turns, even when they exceed the soft limit.
    human_indices = [i for i, msg in enumerate(other_msgs) if getattr(msg, "type", None) == "human"]
    if not human_indices:
        return system_msgs + other_msgs
    required_start = human_indices[max(0, len(human_indices) - max(min_turns, 1))]
    target = max(0, len(other_msgs) - max_messages)
    starts = [i for i in human_indices if i <= min(target, required_start)]
    start = starts[-1] if starts else human_indices[0]
    return system_msgs + other_msgs[start:]


class CheckpointerManager:
    """Управление чекпоинтером состояний диалогов LangGraph на базе AsyncPostgresSaver."""

    @staticmethod
    def get_checkpointer(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
        """Создает экземпляр AsyncPostgresSaver на основе пула соединений psycopg_pool."""
        return AsyncPostgresSaver(pool)
