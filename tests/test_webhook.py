"""
Тесты для webhook-транспорта
"""

import hmac
import hashlib

import pytest

from vkflow.webhook import WebhookApp, WebhookBotEntry, WebhookValidator


def test_webhook_validator_secret_valid():
    """Валидация secret ключа — совпадение"""
    data = {"secret": "my_secret", "type": "message_new"}
    assert WebhookValidator.validate_secret(data, "my_secret") is True


def test_webhook_validator_secret_invalid():
    """Валидация secret ключа — несовпадение"""
    data = {"secret": "wrong_secret", "type": "message_new"}
    assert WebhookValidator.validate_secret(data, "my_secret") is False


def test_webhook_validator_secret_missing():
    """Валидация secret ключа — отсутствует в данных"""
    data = {"type": "message_new"}
    assert WebhookValidator.validate_secret(data, "my_secret") is False


def test_webhook_validator_signature_valid():
    """Валидация HMAC-SHA256 подписи — корректная"""
    body = b'{"type":"message_new"}'
    secret = "my_secret"
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert WebhookValidator.validate_signature(body, secret, expected) is True


def test_webhook_validator_signature_invalid():
    """Валидация HMAC-SHA256 подписи — некорректная"""
    body = b'{"type":"message_new"}'
    assert WebhookValidator.validate_signature(body, "my_secret", "wrong_sig") is False


def test_webhook_bot_entry_defaults():
    """WebhookBotEntry имеет правильные значения по умолчанию"""
    entry = WebhookBotEntry(token="my_token")
    assert entry.token == "my_token"
    assert entry.secret_key is None
    assert entry.confirmation_key is None


def test_webhook_bot_entry_custom():
    """WebhookBotEntry с кастомными ключами"""
    entry = WebhookBotEntry(
        token="my_token",
        secret_key="secret",
        confirmation_key="confirm",
    )
    assert entry.secret_key == "secret"
    assert entry.confirmation_key == "confirm"


def test_webhook_app_defaults():
    """WebhookApp имеет правильные значения по умолчанию"""
    app = WebhookApp()
    assert app.secret_key is None
    assert app.confirmation_key is None
    assert app.path == "/webhook"


def test_webhook_app_custom_path():
    """WebhookApp с кастомным путём"""
    app = WebhookApp(path="/api/vk")
    assert app.path == "/api/vk"


def test_resolve_entry_plain_token():
    """_resolve_entry оборачивает строковый токен в WebhookBotEntry"""
    app = WebhookApp(secret_key="app_secret", confirmation_key="app_confirm")
    entry = app._resolve_entry("token123")
    assert isinstance(entry, WebhookBotEntry)
    assert entry.token == "token123"
    assert entry.secret_key == "app_secret"
    assert entry.confirmation_key == "app_confirm"


def test_resolve_entry_webhook_bot_entry():
    """_resolve_entry сохраняет ключи из WebhookBotEntry"""
    app = WebhookApp(secret_key="app_secret", confirmation_key="app_confirm")
    entry = app._resolve_entry(WebhookBotEntry("token123", secret_key="custom_secret"))
    assert entry.secret_key == "custom_secret"
    assert entry.confirmation_key == "app_confirm"


def test_resolve_entry_inherits_app_keys():
    """_resolve_entry наследует ключи приложения, если не указаны"""
    app = WebhookApp(secret_key="app_secret", confirmation_key="app_confirm")
    entry = app._resolve_entry(WebhookBotEntry("token123"))
    assert entry.secret_key == "app_secret"
    assert entry.confirmation_key == "app_confirm"


def test_webhook_app_creates_aiohttp_app():
    """create_aiohttp_app возвращает aiohttp Application"""
    import aiohttp.web

    app = WebhookApp(path="/hook")
    aio_app = app.create_aiohttp_app()
    assert isinstance(aio_app, aiohttp.web.Application)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
