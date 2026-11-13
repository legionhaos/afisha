"""PostgreSQL checkpoint setup and bounded conversation history."""

import os
from typing import Any


class CheckpointerManager:
    @staticmethod
    async def get_checkpointer(pool: Any) -> Any:
        os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        return saver


def trim_conversation_history(messages: list[Any], min_turns: int = 5, max_messages: int = 14) -> list[Any]:
    """Keep whole recent human turns, even if tool messages exceed the soft cap."""
    if not messages:
        return []
    system = [message for message in messages if getattr(message, "type", None) == "system"]
    rest = [message for message in messages if getattr(message, "type", None) != "system"]
    human_indices = [i for i, message in enumerate(rest) if getattr(message, "type", None) == "human"]
    if not human_indices:
        return system + rest
    required_start = human_indices[max(0, len(human_indices) - max(min_turns, 1))]
    # Start only at a human message so tool results never become orphaned.
    target = max(0, len(rest) - max_messages)
    starts = [i for i in human_indices if i <= min(target, required_start)]
    start = starts[-1] if starts else human_indices[0]
    return system + rest[start:]
