"""Tests for attachment cutters."""

import pytest
from unittest.mock import MagicMock

from vkflow import (
    Photo,
    AudioMessage,
    Document,
    Video,
)
from vkflow.commands.parsing.cutters import (
    PhotoCutter,
    PhotoListCutter,
    AudioMessageCutter,
    AudioMessageListCutter,
    DocumentCutter,
    VideoCutter,
    ATTACHMENT_CUTTERS,
    ATTACHMENT_LIST_CUTTERS,
)
from vkflow.commands.parsing.adapters import _resolve_cutter
from vkflow.commands.parsing.cutter import Argument
from vkflow.exceptions import BadArgumentError


def create_mock_ctx(
    attachments=None,
    reply_attachments=None,
    fwd_attachments=None,
):
    """Create a mock context with attachments."""
    ctx = MagicMock()
    from vkflow.app.storages import ArgumentPayload

    ctx.argument_processing_payload = ArgumentPayload()
    ctx.api = MagicMock()

    # Main message
    msg = MagicMock()
    msg.is_cropped = False
    msg.attachments = attachments or []

    # Reply message
    if reply_attachments is not None:
        reply_msg = MagicMock()
        reply_msg.is_cropped = False
        reply_msg.attachments = reply_attachments
        msg.reply_message = reply_msg
    else:
        msg.reply_message = None

    # Forwarded messages
    if fwd_attachments is not None:
        fwd_msgs = []
        for fwd_att in fwd_attachments:
            fwd_msg = MagicMock()
            fwd_msg.is_cropped = False
            fwd_msg.attachments = fwd_att
            fwd_msgs.append(fwd_msg)
        msg.fwd_messages = fwd_msgs
    else:
        msg.fwd_messages = []

    ctx.msg = msg
    return ctx


class TestAttachmentCuttersRegistry:
    def test_all_attachment_types_registered(self):
        expected_types = [
            "photo",
            "doc",
            "video",
            "audio",
            "audio_message",
            "sticker",
            "wall",
            "gift",
            "graffiti",
            "link",
            "poll",
            "market",
            "story",
        ]

        for att_type in expected_types:
            assert att_type in ATTACHMENT_CUTTERS, f"{att_type} not in ATTACHMENT_CUTTERS"
            assert att_type in ATTACHMENT_LIST_CUTTERS, f"{att_type} not in ATTACHMENT_LIST_CUTTERS"


class TestPhotoCutter:
    @pytest.mark.asyncio
    async def test_extract_photo_from_message(self):
        ctx = create_mock_ctx(attachments=[{"type": "photo", "photo": {"id": 123, "owner_id": 456}}])

        cutter = PhotoCutter()
        result = await cutter.cut_part(ctx, "some text")

        assert isinstance(result.parsed_part, Photo)
        assert result.parsed_part.fields["id"] == 123
        assert result.new_arguments_string == "some text"

    @pytest.mark.asyncio
    async def test_extract_photo_from_reply(self):
        ctx = create_mock_ctx(
            attachments=[], reply_attachments=[{"type": "photo", "photo": {"id": 789, "owner_id": 101}}]
        )

        cutter = PhotoCutter()
        result = await cutter.cut_part(ctx, "text")

        assert isinstance(result.parsed_part, Photo)
        assert result.parsed_part.fields["id"] == 789

    @pytest.mark.asyncio
    async def test_extract_photo_from_forwarded(self):
        ctx = create_mock_ctx(
            attachments=[],
            reply_attachments=None,
            fwd_attachments=[[{"type": "photo", "photo": {"id": 111, "owner_id": 222}}]],
        )

        cutter = PhotoCutter()
        result = await cutter.cut_part(ctx, "text")

        assert isinstance(result.parsed_part, Photo)
        assert result.parsed_part.fields["id"] == 111

    @pytest.mark.asyncio
    async def test_priority_current_over_reply(self):
        ctx = create_mock_ctx(
            attachments=[{"type": "photo", "photo": {"id": 1, "owner_id": 1}}],
            reply_attachments=[{"type": "photo", "photo": {"id": 2, "owner_id": 2}}],
        )

        cutter = PhotoCutter()
        result = await cutter.cut_part(ctx, "text")

        assert result.parsed_part.fields["id"] == 1

    @pytest.mark.asyncio
    async def test_no_photo_raises_error(self):
        ctx = create_mock_ctx(attachments=[])

        cutter = PhotoCutter()

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(ctx, "text")

    @pytest.mark.asyncio
    async def test_multiple_photos_uses_counter(self):
        ctx = create_mock_ctx(
            attachments=[
                {"type": "photo", "photo": {"id": 1, "owner_id": 1}},
                {"type": "photo", "photo": {"id": 2, "owner_id": 2}},
            ]
        )

        cutter1 = PhotoCutter()
        cutter2 = PhotoCutter()

        result1 = await cutter1.cut_part(ctx, "text")
        result2 = await cutter2.cut_part(ctx, "text")

        assert result1.parsed_part.fields["id"] == 1
        assert result2.parsed_part.fields["id"] == 2


class TestPhotoListCutter:
    @pytest.mark.asyncio
    async def test_extract_all_photos(self):
        ctx = create_mock_ctx(
            attachments=[
                {"type": "photo", "photo": {"id": 1, "owner_id": 1}},
                {"type": "photo", "photo": {"id": 2, "owner_id": 2}},
                {"type": "photo", "photo": {"id": 3, "owner_id": 3}},
            ]
        )

        cutter = PhotoListCutter()
        result = await cutter.cut_part(ctx, "text")

        assert len(result.parsed_part) == 3
        assert all(isinstance(p, Photo) for p in result.parsed_part)
        assert [p.fields["id"] for p in result.parsed_part] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_extract_photos_from_all_sources(self):
        ctx = create_mock_ctx(
            attachments=[
                {"type": "photo", "photo": {"id": 1, "owner_id": 1}},
            ],
            reply_attachments=[
                {"type": "photo", "photo": {"id": 2, "owner_id": 2}},
            ],
            fwd_attachments=[
                [{"type": "photo", "photo": {"id": 3, "owner_id": 3}}],
            ],
        )

        cutter = PhotoListCutter()
        result = await cutter.cut_part(ctx, "text")

        assert len(result.parsed_part) == 3
        assert [p.fields["id"] for p in result.parsed_part] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_empty_list_when_no_photos(self):
        ctx = create_mock_ctx(attachments=[])

        cutter = PhotoListCutter()
        result = await cutter.cut_part(ctx, "text")

        assert result.parsed_part == []


class TestAudioMessageCutter:
    @pytest.mark.asyncio
    async def test_extract_voice_message(self):
        ctx = create_mock_ctx(
            attachments=[
                {
                    "type": "audio_message",
                    "audio_message": {
                        "id": 123,
                        "owner_id": 456,
                        "duration": 10,
                        "link_ogg": "https://example.com/audio.ogg",
                        "link_mp3": "https://example.com/audio.mp3",
                    },
                }
            ]
        )

        cutter = AudioMessageCutter()
        result = await cutter.cut_part(ctx, "text")

        assert isinstance(result.parsed_part, AudioMessage)
        assert result.parsed_part.duration == 10

    @pytest.mark.asyncio
    async def test_no_voice_message_raises_error(self):
        ctx = create_mock_ctx(attachments=[])

        cutter = AudioMessageCutter()

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(ctx, "text")


class TestResolveAttachmentCutter:
    def test_resolve_photo_type(self):
        cutter = _resolve_cutter(
            arg_name="photo",
            arg_annotation=Photo,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, PhotoCutter)

    def test_resolve_audio_message_type(self):
        cutter = _resolve_cutter(
            arg_name="voice",
            arg_annotation=AudioMessage,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, AudioMessageCutter)

    def test_resolve_document_type(self):
        cutter = _resolve_cutter(
            arg_name="doc",
            arg_annotation=Document,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, DocumentCutter)

    def test_resolve_video_type(self):
        cutter = _resolve_cutter(
            arg_name="video",
            arg_annotation=Video,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, VideoCutter)

    def test_resolve_list_photo_type(self):

        cutter = _resolve_cutter(
            arg_name="photos",
            arg_annotation=list[Photo],
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, PhotoListCutter)

    def test_resolve_list_audio_message_type(self):
        cutter = _resolve_cutter(
            arg_name="voices",
            arg_annotation=list[AudioMessage],
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, AudioMessageListCutter)


class TestOptionalAttachment:
    def test_resolve_optional_photo(self):
        from vkflow.commands.parsing.cutters import OptionalCutter

        cutter = _resolve_cutter(
            arg_name="photo",
            arg_annotation=Photo | None,
            arg_settings=Argument(default=None),
            arg_kind=None,
        )

        assert isinstance(cutter, OptionalCutter)

    @pytest.mark.asyncio
    async def test_optional_photo_returns_none(self):

        cutter = _resolve_cutter(
            arg_name="photo",
            arg_annotation=Photo | None,
            arg_settings=Argument(default=None),
            arg_kind=None,
        )

        ctx = create_mock_ctx(attachments=[])

        result = await cutter.cut_part(ctx, "text")

        assert result.parsed_part is None
        assert result.new_arguments_string == "text"

    @pytest.mark.asyncio
    async def test_optional_photo_returns_photo_when_present(self):
        cutter = _resolve_cutter(
            arg_name="photo",
            arg_annotation=Photo | None,
            arg_settings=Argument(default=None),
            arg_kind=None,
        )

        ctx = create_mock_ctx(attachments=[{"type": "photo", "photo": {"id": 123, "owner_id": 456}}])

        result = await cutter.cut_part(ctx, "text")

        assert isinstance(result.parsed_part, Photo)
        assert result.parsed_part.fields["id"] == 123
