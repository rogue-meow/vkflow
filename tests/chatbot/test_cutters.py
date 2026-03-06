import asyncio
import typing
import unittest.mock

import pytest

import vkflow as vf

NOT_PARSED = object()


@pytest.mark.parametrize(
    ("cutter", "string", "expected"),
    [
        (vf.IntegerCutter(), "123", 123),
        (vf.IntegerCutter(), "123 456", 123),
        (vf.IntegerCutter(), "007", 7),
        (vf.IntegerCutter(), "1b2", 1),
        (vf.IntegerCutter(), "+12", 12),
        (vf.IntegerCutter(), "-12", -12),
        (vf.IntegerCutter(), "abc2", NOT_PARSED),
        (vf.FloatCutter(), "12.1", 12.1),
        (vf.FloatCutter(), ".1", 0.1),
        (vf.FloatCutter(), "+12.1", 12.1),
        (vf.FloatCutter(), "-.1", -0.1),
        (vf.FloatCutter(), "12e5", 12e5),
        (vf.FloatCutter(), "12E-5", 12e-5),
        (vf.FloatCutter(), "-12E-5", -12e-5),
        (vf.FloatCutter(), "~12E-5", NOT_PARSED),
        (vf.WordCutter(), "foobar", "foobar"),
        (vf.WordCutter(), "foo123", "foo123"),
        (vf.WordCutter(), "!@привет#4123", "!@привет#4123"),
        (vf.WordCutter(), "foo bar", "foo"),
        (vf.WordCutter(), "\nfoo bar", NOT_PARSED),
        (
            vf.StringCutter(),
            "!@привет#4123\n\n !@привет#4123",
            "!@привет#4123\n\n !@привет#4123",
        ),
        (vf.OptionalCutter(vf.IntegerCutter()), "123", 123),
        (vf.OptionalCutter(vf.IntegerCutter()), "abc", None),
        (vf.OptionalCutter(vf.IntegerCutter(), default=123), "abc", 123),
        (
            vf.OptionalCutter(vf.IntegerCutter(), default_factory=int),
            "abc",
            0,
        ),
        (vf.UnionCutter(vf.IntegerCutter(), vf.WordCutter()), "abc", "abc"),
        (vf.UnionCutter(vf.IntegerCutter(), vf.WordCutter()), "123", 123),
        (
            vf.OptionalCutter(vf.UnionCutter(vf.IntegerCutter(), vf.WordCutter())),
            " ",
            None,
        ),
        (
            vf.GroupCutter(vf.IntegerCutter(), vf.WordCutter()),
            "123",
            NOT_PARSED,
        ),
        (
            vf.GroupCutter(vf.IntegerCutter(), vf.WordCutter()),
            "123abc",
            (123, "abc"),
        ),
        (
            vf.GroupCutter(vf.IntegerCutter(), vf.LiteralCutter(r"\s+"), vf.WordCutter()),
            "123   abc",
            (123, "   ", "abc"),
        ),
        (
            vf.GroupCutter(vf.IntegerCutter(), vf.LiteralCutter("!"), vf.WordCutter()),
            "123abc",
            NOT_PARSED,
        ),
        (
            vf.MutableSequenceCutter(vf.IntegerCutter()),
            "123,456 678 , 901",
            [123, 456, 678, 901],
        ),
        (
            vf.MutableSequenceCutter(vf.IntegerCutter()),
            "abc",
            [],
        ),
        (
            vf.ImmutableSequenceCutter(vf.UnionCutter(vf.IntegerCutter(), vf.WordCutter())),
            "123,456 abc , 901",
            (123, 456, "abc", 901),
        ),
        (
            vf.UniqueMutableSequenceCutter(vf.UnionCutter(vf.IntegerCutter(), vf.WordCutter())),
            "",
            set(),
        ),
        (
            vf.UniqueImmutableSequenceCutter(vf.IntegerCutter()),
            "123 abc",
            frozenset([123]),
        ),
    ],
)
@pytest.mark.asyncio
async def test_simple_cutters(cutter, string, expected):
    try:
        parsed_result = await cutter.cut_part(None, string)
    except vf.BadArgumentError:
        assert expected is NOT_PARSED
    else:
        assert parsed_result.parsed_part == expected


@pytest.mark.asyncio
async def test_mention_with_wrapper(group_api):
    mocked_context = unittest.mock.Mock()
    mocked_context.api = group_api

    cutter = vf.MentionCutter(vf.Page)
    call1 = await cutter.cut_part(mocked_context, "[id1|abc]")
    call2 = await cutter.cut_part(mocked_context, "[club1|abc]")
    assert call1.parsed_part.alias == call2.parsed_part.alias == "abc"
    assert call1.parsed_part.entity.id == call2.parsed_part.entity.id == 1
    assert isinstance(call1.parsed_part.entity, vf.User)
    assert isinstance(call2.parsed_part.entity, vf.Group)

    cutter = vf.MentionCutter(vf.Group)
    with pytest.raises(vf.BadArgumentError):
        await cutter.cut_part(mocked_context, "[id1|abc]")
    call = await cutter.cut_part(mocked_context, "[club1|abc]")
    assert call.parsed_part.alias == "abc"
    assert call.parsed_part.entity.id == 1
    assert isinstance(call.parsed_part.entity, vf.Group)

    cutter = vf.MentionCutter(vf.User)
    with pytest.raises(vf.BadArgumentError):
        await cutter.cut_part(mocked_context, "[club1|abc]")
    call = await cutter.cut_part(mocked_context, "[id1|abc]")
    assert call.parsed_part.alias == "abc"
    assert call.parsed_part.entity.id == 1
    assert isinstance(call.parsed_part.entity, vf.User)

    # Несуществующий ID
    with pytest.raises(vf.BadArgumentError):
        await cutter.cut_part(mocked_context, "[id123123123123123123123123|abc]")

    cutter = vf.MentionCutter(vf.User[typing.Literal["bdate"]])
    call = await cutter.cut_part(mocked_context, "[id1|abc]")
    assert "bdate" in call.parsed_part.entity.fields


@pytest.mark.asyncio
async def test_mention_with_id():
    cutter = vf.MentionCutter(vf.PageID)
    call1 = await cutter.cut_part(None, "[id123|abc]")
    call2 = await cutter.cut_part(None, "[club123|abc]")
    assert call1.parsed_part.alias == call2.parsed_part.alias == "abc"
    assert call1.parsed_part.entity == call2.parsed_part.entity == 123
    assert call1.parsed_part.page_type == vf.PageType.USER
    assert call2.parsed_part.page_type == vf.PageType.GROUP

    cutter = vf.MentionCutter(vf.GroupID)
    with pytest.raises(vf.BadArgumentError):
        await cutter.cut_part(None, "[id123|abc]")
    call = await cutter.cut_part(None, "[club123|abc]")
    assert call.parsed_part.alias == "abc"
    assert call.parsed_part.entity == 123
    assert call.parsed_part.page_type == vf.PageType.GROUP

    cutter = vf.MentionCutter(vf.UserID)
    with pytest.raises(vf.BadArgumentError):
        await cutter.cut_part(None, "[club123|abc]")
    call = await cutter.cut_part(None, "[id123|abc]")
    assert call.parsed_part.alias == "abc"
    assert call.parsed_part.entity == 123
    assert call.parsed_part.page_type == vf.PageType.USER


@pytest.mark.parametrize(
    "input_string",
    [
        "[id1|abc]",
        "vk.ru/durov",
        "vk.ru/id1",
        "https://vk.ru/id1",
        "http://vk.ru/id1",
        "id1",
        "durov",
        "1",
    ],
)
@pytest.mark.asyncio
async def test_group_entity_by_string(input_string, group_api):
    mocked_context = unittest.mock.Mock()
    mocked_context.api = group_api
    page_cutter = vf.EntityCutter(vf.Page)
    user_cutter = vf.EntityCutter(vf.User)
    user_id_cutter = vf.EntityCutter(vf.User)
    result_page, result_user, result_user_id = await asyncio.gather(
        page_cutter.cut_part(mocked_context, input_string),
        user_cutter.cut_part(mocked_context, input_string),
        user_id_cutter.cut_part(mocked_context, input_string),
    )
    assert result_page.parsed_part.id == result_user.parsed_part.id == result_user_id.parsed_part.id == 1
