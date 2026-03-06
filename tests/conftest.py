import os

import pytest
import pytest_asyncio

import vkflow


@pytest_asyncio.fixture
async def group_api():
    if "GROUP_TOKEN" not in os.environ:
        pytest.skip("GROUP_TOKEN env var not set")
    api = vkflow.API("$GROUP_TOKEN", token_owner=vkflow.TokenOwner.GROUP)
    async with api:
        yield api


@pytest_asyncio.fixture
async def user_api():
    if "USER_TOKEN" not in os.environ:
        pytest.skip("USER_TOKEN env var not set")
    api = vkflow.API("$USER_TOKEN", token_owner=vkflow.TokenOwner.USER)
    async with api:
        yield api
