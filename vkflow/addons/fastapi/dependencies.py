from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from vkflow.addons.fastapi.addon import FastAPIAddon
    from vkflow.api import API
    from vkflow.app.bot import App, Bot


def get_vk_app(request: Request) -> App:
    """Get the VKQuick App instance."""
    return request.app.state.vk_app


def get_bot(
    request: Request,
    bot_index: int = 0,
    group_id: int | None = None,
) -> Bot:
    """Get a Bot instance by index or group_id."""
    bots = request.app.state.vk_bots
    if group_id is not None:
        for bot in bots:
            if bot.api._owner_schema and bot.api._owner_schema.id == group_id:
                return bot
        raise HTTPException(404, f"Bot with group_id={group_id} not found")
    return bots[bot_index]


def get_api(
    request: Request,
    bot_index: int = 0,
    group_id: int | None = None,
) -> API:
    """Get the API instance from a Bot."""
    return get_bot(request, bot_index=bot_index, group_id=group_id).api


def get_addon(request: Request) -> FastAPIAddon:
    """Get the FastAPIAddon instance."""
    return request.app.state.vk_addon
