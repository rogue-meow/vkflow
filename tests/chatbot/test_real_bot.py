import asyncio
import dataclasses
import typing

import pytest

import vkflow as vf


@dataclasses.dataclass
class AppMetadata:
    group_ponged: bool = dataclasses.field(default=False)
    user_ponged: bool = dataclasses.field(default=False)


app: vf.App[AppMetadata] = vf.App(payload_factory=AppMetadata)


@app.command("ping")
async def ping(ctx: vf.NewMessage[AppMetadata, typing.Any, typing.Any]):
    bot_type, _ = await ctx.api.define_token_owner()
    if bot_type == vf.TokenOwner.USER:
        ctx.app.payload.user_ponged = True
    else:
        ctx.app.payload.group_ponged = True
    ctx.bot.events_factory.stop()
    return "pong"


@pytest.mark.asyncio
async def test_ping_bot(group_api, user_api):
    group = await group_api.define_token_owner()
    group_schema = group[1]

    group_bot_task = asyncio.create_task(app.start(group_api, build_autodoc=False))
    user_bot_task = asyncio.create_task(app.start(user_api, build_autodoc=False))
    # Setup the bot
    await asyncio.sleep(1)

    await user_api.method(
        "messages.send",
        random_id=vf.random_id(),
        message="ping",
        peer_id=-group_schema.id,
    )

    await group_bot_task
    # Wait the answer
    await asyncio.gather(group_bot_task, user_bot_task, asyncio.sleep(1))
    last_message = await user_api.method(
        "messages.get_history",
        count=2,
        peer_id=-group_schema.id,
    )
    assert last_message["items"][0]["text"] == last_message["items"][1]["text"] == "pong"
    assert app.payload.user_ponged and app.payload.group_ponged
