import unittest.mock

import pytest

import vkflow as vf


@pytest.mark.asyncio
async def test_and_filter():
    filter = vf.filters.OnlyMe() & vf.filters.IgnoreBots()
    mock = unittest.mock.Mock()
    mock.msg = unittest.mock.Mock()
    mock.msg.from_id = 100
    mock.msg.out = True

    await filter.make_decision(mock)

    mock.msg.out = False
    with pytest.raises(vf.StopCurrentHandlingError):
        await filter.make_decision(mock)

    mock.msg.out = True
    mock.msg.from_id = -100
    with pytest.raises(vf.StopCurrentHandlingError):
        await filter.make_decision(mock)


@pytest.mark.asyncio
async def test_or_filter_combined():
    filter = vf.filters.OnlyMe() | vf.filters.IgnoreBots()
    mock = unittest.mock.Mock()
    mock.msg = unittest.mock.Mock()
    mock.msg.from_id = 100
    mock.msg.out = True

    await filter.make_decision(mock)

    mock.msg.out = False
    await filter.make_decision(mock)

    mock.msg.out = True
    mock.msg.from_id = -100
    await filter.make_decision(mock)

    mock.msg.out = False
    with pytest.raises(vf.StopCurrentHandlingError):
        await filter.make_decision(mock)


@pytest.mark.parametrize(
    ("filter", "fields", "passed"),
    [
        (vf.filters.OnlyMe(), {"out": True}, True),
        (vf.filters.OnlyMe(), {"out": False}, False),
        (vf.filters.IgnoreBots(), {"from_id": 100}, True),
        (vf.filters.IgnoreBots(), {"from_id": -100}, False),
        (vf.filters.ChatOnly(), {"peer_id": vf.peer(100)}, True),
        (vf.filters.ChatOnly(), {"peer_id": 100}, False),
        (vf.filters.DirectOnly(), {"peer_id": 100}, True),
        (vf.filters.DirectOnly(), {"peer_id": vf.peer(100)}, False),
        (
            vf.filters.Dynamic(lambda ctx: ctx.msg.some_field == "egg"),
            {"some_field": "egg"},
            True,
        ),
        (
            vf.filters.Dynamic(lambda ctx: 5 > 10),
            {"some_field": "egg"},
            False,
        ),
    ],
)
@pytest.mark.asyncio
async def test_or_filter(filter, fields, passed):
    mock = unittest.mock.Mock()
    mock.msg = unittest.mock.Mock()
    mock.msg.__dict__.update(fields)

    if passed:
        await filter.make_decision(mock)
    else:
        with pytest.raises(vf.StopCurrentHandlingError):
            await filter.make_decision(mock)
