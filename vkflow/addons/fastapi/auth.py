from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Sequence


class APIKeyMiddleware:
    """ASGI middleware for API key authentication via Authorization: Bearer header."""

    def __init__(
        self,
        app,
        api_key: str,
        exclude_paths: Sequence[str] | None = None,
    ):
        self.app = app
        self.api_key = api_key
        self.exclude_paths = list(exclude_paths or [])

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if not self._is_excluded(path):
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode()
                if auth != f"Bearer {self.api_key}":
                    await self._send_401(send)
                    return

        await self.app(scope, receive, send)

    def _is_excluded(self, path: str) -> bool:
        return any(path == excluded or path.startswith(excluded + "/") for excluded in self.exclude_paths)

    @staticmethod
    async def _send_401(send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"Unauthorized"}',
            }
        )
