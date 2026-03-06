"""
Tests for chat action events system
"""

import pytest
from vkflow.commands.listener import (
    listener,
    normalize_event_name,
    is_chat_action_event,
    get_action_types_for_event,
    CHAT_ACTION_EVENTS,
    CHAT_ACTION_ALIASES,
)
from vkflow.commands.chat_actions import (
    ChatActionEvent,
    MemberJoinEvent,
    MemberRemoveEvent,
    PinMessageEvent,
    UnpinMessageEvent,
    ChatPhotoUpdateEvent,
    ChatPhotoRemoveEvent,
    ChatTitleUpdateEvent,
    ChatCreateEvent,
    ChatPhoto,
    create_chat_action_event,
)


class TestChatActionConstants:
    """Test chat action constants"""

    def test_chat_action_events_set(self):
        """Test CHAT_ACTION_EVENTS contains expected events"""
        assert "chat_invite_user" in CHAT_ACTION_EVENTS
        assert "chat_kick_user" in CHAT_ACTION_EVENTS
        assert "chat_pin_message" in CHAT_ACTION_EVENTS
        assert "chat_unpin_message" in CHAT_ACTION_EVENTS
        assert "member_join" in CHAT_ACTION_EVENTS
        assert "member_remove" in CHAT_ACTION_EVENTS
        assert "pin_message" in CHAT_ACTION_EVENTS
        assert "unpin_message" in CHAT_ACTION_EVENTS
        assert "chat_edit" in CHAT_ACTION_EVENTS

    def test_chat_action_aliases(self):
        """Test CHAT_ACTION_ALIASES mappings"""
        # member_join should map to multiple action types
        assert "chat_invite_user" in CHAT_ACTION_ALIASES["member_join"]
        assert "chat_invite_user_by_link" in CHAT_ACTION_ALIASES["member_join"]

        # member_remove should map to chat_kick_user
        assert "chat_kick_user" in CHAT_ACTION_ALIASES["member_remove"]

        # pin_message should map to chat_pin_message
        assert "chat_pin_message" in CHAT_ACTION_ALIASES["pin_message"]

        # chat_edit should map to photo and title updates
        assert "chat_photo_update" in CHAT_ACTION_ALIASES["chat_edit"]
        assert "chat_photo_remove" in CHAT_ACTION_ALIASES["chat_edit"]
        assert "chat_title_update" in CHAT_ACTION_ALIASES["chat_edit"]


class TestNormalization:
    """Test event name normalization for chat actions"""

    def test_normalize_chat_action_events(self):
        """Test normalizing chat action event names"""
        assert normalize_event_name("on_member_join") == ("member_join", False)
        assert normalize_event_name("on_raw_member_join") == ("member_join", True)
        assert normalize_event_name("member_join") == ("member_join", False)
        assert normalize_event_name("on_chat_invite_user") == ("chat_invite_user", False)
        assert normalize_event_name("on_pin_message") == ("pin_message", False)
        assert normalize_event_name("on_raw_unpin_message") == ("unpin_message", True)

    def test_is_chat_action_event(self):
        """Test is_chat_action_event function"""
        assert is_chat_action_event("member_join") is True
        assert is_chat_action_event("chat_invite_user") is True
        assert is_chat_action_event("pin_message") is True
        assert is_chat_action_event("message_new") is False
        assert is_chat_action_event("message_event") is False

    def test_get_action_types_for_event(self):
        """Test get_action_types_for_event function"""
        types = get_action_types_for_event("member_join")
        assert "chat_invite_user" in types
        assert "chat_invite_user_by_link" in types

        types = get_action_types_for_event("member_remove")
        assert "chat_kick_user" in types

        # Non-existent event should return empty list
        types = get_action_types_for_event("non_existent")
        assert types == []


class TestChatPhoto:
    """Test ChatPhoto dataclass"""

    def test_from_dict(self):
        """Test creating ChatPhoto from dict"""
        data = {
            "photo_50": "https://vk.com/photo_50.jpg",
            "photo_100": "https://vk.com/photo_100.jpg",
            "photo_200": "https://vk.com/photo_200.jpg",
        }
        photo = ChatPhoto.from_dict(data)
        assert photo.photo_50 == "https://vk.com/photo_50.jpg"
        assert photo.photo_100 == "https://vk.com/photo_100.jpg"
        assert photo.photo_200 == "https://vk.com/photo_200.jpg"

    def test_from_dict_none(self):
        """Test creating ChatPhoto from None"""
        assert ChatPhoto.from_dict(None) is None

    def test_from_dict_partial(self):
        """Test creating ChatPhoto with partial data"""
        data = {"photo_50": "https://vk.com/photo_50.jpg"}
        photo = ChatPhoto.from_dict(data)
        assert photo.photo_50 == "https://vk.com/photo_50.jpg"
        assert photo.photo_100 is None
        assert photo.photo_200 is None


class TestCreateChatActionEvent:
    """Test create_chat_action_event factory function"""

    class FakeMessage:
        def __init__(self, action, from_id=123, peer_id=2000000001):
            self.action = action
            self.from_id = from_id
            self.peer_id = peer_id

    class FakeNewMessage:
        def __init__(self, msg):
            self.msg = msg
            self.bot = None
            self.api = None

    def test_create_member_join_event(self):
        """Test creating MemberJoinEvent"""
        action = {
            "type": "chat_invite_user",
            "member_id": 456,
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, MemberJoinEvent)
        assert event.action_type == "chat_invite_user"
        assert event.member_id == 456
        assert event.from_id == 123
        assert event.peer_id == 2000000001
        assert event.inviter_id == 123  # from_id is inviter
        assert event.is_direct_invite is True

    def test_create_member_join_by_link(self):
        """Test creating MemberJoinEvent for link invite"""
        action = {"type": "chat_invite_user_by_link"}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, MemberJoinEvent)
        assert event.is_by_link is True
        assert event.inviter_id is None

    def test_create_member_self_return(self):
        """Test creating MemberJoinEvent for self return"""
        action = {
            "type": "chat_invite_user",
            "member_id": 123,  # Same as from_id
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, MemberJoinEvent)
        assert event.is_self_return is True
        assert event.is_direct_invite is False
        assert event.inviter_id is None

    def test_create_member_remove_event(self):
        """Test creating MemberRemoveEvent"""
        action = {
            "type": "chat_kick_user",
            "member_id": 456,
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, MemberRemoveEvent)
        assert event.member_id == 456
        assert event.is_kicked is True
        assert event.is_self_leave is False
        assert event.kicker_id == 123

    def test_create_member_self_leave(self):
        """Test creating MemberRemoveEvent for self leave"""
        action = {
            "type": "chat_kick_user",
            "member_id": 123,  # Same as from_id
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, MemberRemoveEvent)
        assert event.is_self_leave is True
        assert event.is_kicked is False

    def test_create_pin_message_event(self):
        """Test creating PinMessageEvent"""
        action = {
            "type": "chat_pin_message",
            "member_id": 123,
            "conversation_message_id": 279,
            "message": "Pinned message text",
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, PinMessageEvent)
        assert event.member_id == 123
        assert event.conversation_message_id == 279
        assert event.message == "Pinned message text"

    def test_create_unpin_message_event(self):
        """Test creating UnpinMessageEvent"""
        action = {
            "type": "chat_unpin_message",
            "member_id": 123,
            "conversation_message_id": 279,
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, UnpinMessageEvent)
        assert event.member_id == 123
        assert event.conversation_message_id == 279

    def test_create_chat_photo_update_event(self):
        """Test creating ChatPhotoUpdateEvent"""
        action = {
            "type": "chat_photo_update",
            "photo": {
                "photo_50": "https://vk.com/photo_50.jpg",
                "photo_100": "https://vk.com/photo_100.jpg",
                "photo_200": "https://vk.com/photo_200.jpg",
            },
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, ChatPhotoUpdateEvent)
        assert event.is_photo_update is True
        assert event.photo is not None
        assert event.photo.photo_50 == "https://vk.com/photo_50.jpg"

    def test_create_chat_photo_remove_event(self):
        """Test creating ChatPhotoRemoveEvent"""
        action = {"type": "chat_photo_remove"}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, ChatPhotoRemoveEvent)
        assert event.is_photo_remove is True
        assert event.photo is None

    def test_create_chat_title_update_event(self):
        """Test creating ChatTitleUpdateEvent"""
        action = {
            "type": "chat_title_update",
            "text": "New Chat Title",
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, ChatTitleUpdateEvent)
        assert event.is_title_update is True
        assert event.text == "New Chat Title"
        assert event.new_title == "New Chat Title"

    def test_create_chat_create_event(self):
        """Test creating ChatCreateEvent"""
        action = {
            "type": "chat_create",
            "text": "My New Chat",
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert isinstance(event, ChatCreateEvent)
        assert event.text == "My New Chat"
        assert event.chat_title == "My New Chat"

    def test_unknown_action_type(self):
        """Test handling unknown action type"""
        action = {"type": "unknown_action"}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        # Should return base ChatActionEvent
        assert isinstance(event, ChatActionEvent)
        assert event.action_type == "unknown_action"

    def test_no_action_type(self):
        """Test handling action without type"""
        action = {}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert event is None


class TestListenerChatAction:
    """Test Listener with chat action events"""

    def test_listener_is_chat_action(self):
        """Test listener knows it's a chat action listener"""

        async def on_member_join(event):
            pass

        lst = listener()(on_member_join)
        assert lst.is_chat_action is True
        assert lst.event_name == "member_join"
        assert "chat_invite_user" in lst.action_types
        assert "chat_invite_user_by_link" in lst.action_types

    def test_listener_not_chat_action(self):
        """Test regular listener is not chat action"""

        async def on_message_new(event):
            pass

        lst = listener()(on_message_new)
        assert lst.is_chat_action is False
        assert lst.action_types == []

    def test_listener_matches_action_type(self):
        """Test listener.matches_action_type"""

        async def on_member_join(event):
            pass

        lst = listener()(on_member_join)
        assert lst.matches_action_type("chat_invite_user") is True
        assert lst.matches_action_type("chat_invite_user_by_link") is True
        assert lst.matches_action_type("chat_kick_user") is False

    def test_listener_specific_action_type(self):
        """Test listener for specific action type"""

        async def on_chat_invite_user(event):
            pass

        lst = listener()(on_chat_invite_user)
        assert lst.is_chat_action is True
        assert lst.matches_action_type("chat_invite_user") is True
        assert lst.matches_action_type("chat_invite_user_by_link") is False

    def test_listener_raw_chat_action(self):
        """Test raw chat action listener"""

        async def on_raw_member_join(payload, member_id):
            pass

        lst = listener()(on_raw_member_join)
        assert lst.is_raw is True
        assert lst.is_chat_action is True
        assert lst.event_name == "member_join"

    def test_listener_pin_message_alias(self):
        """Test pin_message alias (without chat_ prefix)"""

        async def on_pin_message(event):
            pass

        lst = listener()(on_pin_message)
        assert lst.is_chat_action is True
        assert lst.matches_action_type("chat_pin_message") is True

    def test_listener_repr_chat_action(self):
        """Test listener repr for chat action"""

        async def on_member_join(event):
            pass

        lst = listener()(on_member_join)
        repr_str = repr(lst)
        assert "member_join" in repr_str
        assert "chat_invite_user" in repr_str


class TestListenerChatActionInvoke:
    """Test Listener.invoke_chat_action"""

    class FakeMessage:
        def __init__(self, action, from_id=123, peer_id=2000000001):
            self.action = action
            self.from_id = from_id
            self.peer_id = peer_id

    class FakeNewMessage:
        def __init__(self, msg):
            self.msg = msg
            self.bot = "fake_bot"
            self.api = "fake_api"

    @pytest.mark.asyncio
    async def test_invoke_chat_action_with_event(self):
        """Test invoking chat action listener with event parameter"""
        result = {}

        async def on_member_join(event):
            result["event"] = event
            result["member_id"] = event.member_id

        lst = listener()(on_member_join)

        action = {"type": "chat_invite_user", "member_id": 456}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        action_event = create_chat_action_event(ctx, action)

        await lst.invoke_chat_action(action_event, action)

        assert isinstance(result["event"], MemberJoinEvent)
        assert result["member_id"] == 456

    @pytest.mark.asyncio
    async def test_invoke_chat_action_with_params(self):
        """Test invoking chat action listener with specific params"""
        result = {}

        async def on_member_join(member_id, inviter_id, from_id, peer_id):
            result["member_id"] = member_id
            result["inviter_id"] = inviter_id
            result["from_id"] = from_id
            result["peer_id"] = peer_id

        lst = listener()(on_member_join)

        action = {"type": "chat_invite_user", "member_id": 456}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        action_event = create_chat_action_event(ctx, action)

        await lst.invoke_chat_action(action_event, action)

        assert result["member_id"] == 456
        assert result["inviter_id"] == 123
        assert result["from_id"] == 123
        assert result["peer_id"] == 2000000001

    @pytest.mark.asyncio
    async def test_invoke_raw_chat_action(self):
        """Test invoking raw chat action listener"""
        result = {}

        async def on_raw_member_join(payload, member_id, raw):
            result["payload"] = payload
            result["member_id"] = member_id
            result["raw"] = raw

        lst = listener()(on_raw_member_join)

        action = {"type": "chat_invite_user", "member_id": 456}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        action_event = create_chat_action_event(ctx, action)

        await lst.invoke_chat_action(action_event, action)

        assert result["payload"] == action
        assert result["member_id"] == 456
        assert result["raw"] == action

    @pytest.mark.asyncio
    async def test_invoke_chat_action_with_ctx(self):
        """Test invoking chat action listener with ctx"""
        result = {}

        async def on_member_join(ctx, bot, api):
            result["ctx"] = ctx
            result["bot"] = bot
            result["api"] = api

        lst = listener()(on_member_join)

        action = {"type": "chat_invite_user", "member_id": 456}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        action_event = create_chat_action_event(ctx, action)

        await lst.invoke_chat_action(action_event, action)

        assert result["ctx"] == ctx
        assert result["bot"] == "fake_bot"
        assert result["api"] == "fake_api"

    @pytest.mark.asyncio
    async def test_invoke_pin_message(self):
        """Test invoking pin message listener"""
        result = {}

        async def on_pin_message(event, conversation_message_id, member_id):
            result["event"] = event
            result["conversation_message_id"] = conversation_message_id
            result["member_id"] = member_id

        lst = listener()(on_pin_message)

        action = {
            "type": "chat_pin_message",
            "member_id": 123,
            "conversation_message_id": 279,
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        action_event = create_chat_action_event(ctx, action)

        await lst.invoke_chat_action(action_event, action)

        assert isinstance(result["event"], PinMessageEvent)
        assert result["conversation_message_id"] == 279
        assert result["member_id"] == 123

    @pytest.mark.asyncio
    async def test_invoke_chat_edit(self):
        """Test invoking chat edit listener for title update"""
        result = {}

        async def on_chat_edit(event, text):
            result["event"] = event
            result["text"] = text

        lst = listener()(on_chat_edit)

        action = {
            "type": "chat_title_update",
            "text": "New Title",
        }
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        action_event = create_chat_action_event(ctx, action)

        await lst.invoke_chat_action(action_event, action)

        assert isinstance(result["event"], ChatTitleUpdateEvent)
        assert result["text"] == "New Title"


class TestMemberJoinEventProperties:
    """Test MemberJoinEvent properties"""

    class FakeMessage:
        def __init__(self, action, from_id=123, peer_id=2000000001):
            self.action = action
            self.from_id = from_id
            self.peer_id = peer_id

    class FakeNewMessage:
        def __init__(self, msg):
            self.msg = msg
            self.bot = None
            self.api = None

    def test_invited_alias(self):
        """Test invited property is alias for member_id"""
        action = {"type": "chat_invite_user", "member_id": 456}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert event.invited == event.member_id
        assert event.invited == 456

    def test_inviter_alias(self):
        """Test inviter property is alias for inviter_id"""
        action = {"type": "chat_invite_user", "member_id": 456}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert event.inviter == event.inviter_id
        assert event.inviter == 123


class TestChatEditEventProperties:
    """Test ChatEditEvent properties"""

    class FakeMessage:
        def __init__(self, action, from_id=123, peer_id=2000000001):
            self.action = action
            self.from_id = from_id
            self.peer_id = peer_id

    class FakeNewMessage:
        def __init__(self, msg):
            self.msg = msg
            self.bot = None
            self.api = None

    def test_edit_type_property(self):
        """Test edit_type property removes chat_ prefix"""
        action = {"type": "chat_title_update", "text": "Test"}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert event.edit_type == "title_update"

    def test_new_title_alias(self):
        """Test new_title property is alias for text"""
        action = {"type": "chat_title_update", "text": "New Title"}
        ctx = self.FakeNewMessage(self.FakeMessage(action))
        event = create_chat_action_event(ctx, action)

        assert event.new_title == event.text
        assert event.new_title == "New Title"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
