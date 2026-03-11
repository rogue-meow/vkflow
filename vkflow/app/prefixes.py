from __future__ import annotations

import re
import typing
import inspect

from collections.abc import Callable, Awaitable
from loguru import logger

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage


__all__ = (
    "PrefixCallable",
    "PrefixType",
    "resolve_prefixes",
    "when_mentioned",
    "when_mentioned_or",
)


PrefixCallable = (
    Callable[["NewMessage"], str | list[str]] | Callable[["NewMessage"], Awaitable[str | list[str]]]
)

PrefixType = str | list[str] | PrefixCallable


async def resolve_prefixes(
    ctx: NewMessage,
    prefixes: PrefixType | None,
) -> list[str]:
    if prefixes is None:
        return []

    if isinstance(prefixes, str):
        return [prefixes]

    if isinstance(prefixes, list):
        return prefixes

    if callable(prefixes):
        if inspect.iscoroutinefunction(prefixes):
            result = await prefixes(ctx)
        else:
            result = prefixes(ctx)

        return await resolve_prefixes(ctx, result)

    return []


def _get_mention_patterns(ctx: NewMessage) -> list[str]:
    patterns = []
    bot = ctx.bot

    if not bot or not hasattr(bot, "api"):
        return patterns

    try:
        from vkflow.api import TokenOwner

        token_owner = getattr(bot.api, "_token_owner", None)
        owner_schema = getattr(bot.api, "_owner_schema", None)

        bot_id = None

        if owner_schema is not None:
            if hasattr(owner_schema, "_fields") and isinstance(owner_schema._fields, dict):
                bot_id = owner_schema._fields.get("id")

            elif hasattr(owner_schema, "id"):
                bot_id = owner_schema.id

        if bot_id is None and hasattr(bot, "events_factory"):
            from vkflow.longpoll import GroupLongPoll, UserLongPoll

            if isinstance(bot.events_factory, GroupLongPoll) and hasattr(bot.events_factory, "group_id"):
                bot_id = bot.events_factory.group_id
                token_owner = TokenOwner.GROUP

            elif isinstance(bot.events_factory, UserLongPoll) and hasattr(bot.events_factory, "user_id"):
                bot_id = bot.events_factory.user_id
                token_owner = TokenOwner.USER

        if bot_id is not None:
            if token_owner == TokenOwner.GROUP:
                group_id = abs(bot_id)
                patterns.extend(
                    [
                        rf"\[club{group_id}\|[^\]]+\]",
                        rf"\[public{group_id}\|[^\]]+\]",
                    ]
                )

            elif token_owner == TokenOwner.USER:
                user_id = abs(bot_id)
                patterns.extend(
                    [
                        rf"\[id{user_id}\|[^\]]+\]",
                    ]
                )

            else:
                if bot_id < 0:
                    group_id = abs(bot_id)
                    patterns.extend(
                        [
                            rf"\[club{group_id}\|[^\]]+\]",
                            rf"\[public{group_id}\|[^\]]+\]",
                        ]
                    )

                else:
                    patterns.extend(
                        [
                            rf"\[id{bot_id}\|[^\]]+\]",
                        ]
                    )

    except Exception as exc:
        logger.debug("Failed to detect mention patterns: {}", exc)

    return patterns


def when_mentioned() -> PrefixCallable:
    async def _when_mentioned(ctx: NewMessage) -> list[str]:
        patterns = _get_mention_patterns(ctx)

        if not patterns and ctx.msg.text:
            mention_pattern = r"\[(club|public|id)(\d+)\|"
            matches = re.findall(mention_pattern, ctx.msg.text)

            if matches:
                for mention_type, mention_id in matches:
                    patterns.append(f"[{mention_type}{mention_id}|")

        return patterns

    return _when_mentioned


def when_mentioned_or(*prefixes: str | list[str] | PrefixCallable) -> PrefixCallable:
    async def _when_mentioned_or(ctx: NewMessage) -> list[str]:
        mention_prefixes = await when_mentioned()(ctx)
        all_prefixes = list(mention_prefixes)

        for prefix in prefixes:
            resolved = await resolve_prefixes(ctx, prefix)
            all_prefixes.extend(resolved)

        seen = set()
        unique_prefixes = []

        for p in all_prefixes:
            if p not in seen:
                seen.add(p)
                unique_prefixes.append(p)

        return unique_prefixes

    return _when_mentioned_or
