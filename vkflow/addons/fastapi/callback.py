from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request  # noqa: TC002 -FastAPI inspects annotations at runtime
from fastapi.responses import PlainTextResponse

from vkflow.app.storages import NewEvent
from vkflow.event import GroupEvent

_background_tasks: set = set()

if TYPE_CHECKING:
    from vkflow.addons.fastapi.addon import FastAPIAddon
    from vkflow.app.bot import Bot


def setup_callback_routes(
    fastapi_app: FastAPI,
    addon: FastAPIAddon,
    bots: list[Bot],
) -> None:
    """Register VK Callback API endpoints on the FastAPI app."""
    callback_path = addon._callback_path

    if addon._callback_per_bot:
        for bot in bots:
            if bot.api._owner_schema is not None:
                group_id = bot.api._owner_schema.id
                _register_bot_endpoint(fastapi_app, addon, bot, f"{callback_path}/{group_id}")

    @fastapi_app.post(callback_path)
    async def callback_handler(request: Request):
        body = await request.json()
        group_id = body.get("group_id")
        bot = _find_bot_by_group_id(group_id, bots) if group_id else bots[0]
        return await handle_callback(body, bot, addon)


def _register_bot_endpoint(
    fastapi_app: FastAPI,
    addon: FastAPIAddon,
    bot: Bot,
    path: str,
) -> None:
    """Register a per-bot callback endpoint."""

    @fastapi_app.post(path)
    async def bot_callback_handler(request: Request):
        body = await request.json()
        return await handle_callback(body, bot, addon)


async def handle_callback(
    body: dict[str, Any],
    bot: Bot,
    addon: FastAPIAddon,
) -> PlainTextResponse:
    """Process a VK Callback API request."""
    event_type = body.get("type")
    group_id = body.get("group_id")

    if event_type == "confirmation":
        key = _get_confirmation_key(group_id, addon)
        return PlainTextResponse(key or "")

    if not _validate_secret(body, group_id, addon):
        return PlainTextResponse("secret check failed", status_code=403)

    event = GroupEvent(body)
    new_event = await NewEvent.from_event(event=event, bot=bot)
    task = asyncio.create_task(bot.handle_event(new_event))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return PlainTextResponse("ok")


def _get_confirmation_key(group_id: int | None, addon: FastAPIAddon) -> str | None:
    if addon._confirmations and group_id in addon._confirmations:
        return addon._confirmations[group_id]
    return addon._confirmation_key


def _validate_secret(body: dict, group_id: int | None, addon: FastAPIAddon) -> bool:
    expected = None
    if addon._secrets and group_id in addon._secrets:
        expected = addon._secrets[group_id]
    elif addon._secret_key:
        expected = addon._secret_key

    if expected is None:
        return True

    return body.get("secret") == expected


def _find_bot_by_group_id(group_id: int, bots: list[Bot]) -> Bot:
    for bot in bots:
        if bot.api._owner_schema and bot.api._owner_schema.id == group_id:
            return bot
    return bots[0]
