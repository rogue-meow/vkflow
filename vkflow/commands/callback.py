from __future__ import annotations

import typing
import inspect
import functools

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.app.storages import CallbackButtonPressed


CallbackMatcherFunction = typing.Callable[[typing.Any], bool | typing.Awaitable[bool]]


class CallbackHandler:
    def __init__(
        self,
        func: typing.Callable,
        **matchers: str | CallbackMatcherFunction,
    ):
        self.func = func
        self.matchers = matchers
        functools.update_wrapper(self, func)

    async def check(self, ctx: CallbackButtonPressed) -> bool:
        if not ctx.msg.payload:
            return False

        payload = ctx.msg.payload

        for key, matcher in self.matchers.items():
            if key not in payload:
                return False

            payload_value = payload[key]

            if isinstance(matcher, str):
                if payload_value != matcher:
                    return False

            elif callable(matcher):
                result = matcher(payload_value)

                if inspect.iscoroutine(result):
                    result = await result

                if not result:
                    return False

        return True

    async def __call__(self, ctx: CallbackButtonPressed, *args, **kwargs):
        return await self.func(ctx, *args, **kwargs)


def callback(
    **matchers: str | CallbackMatcherFunction,
) -> typing.Callable[[typing.Callable], CallbackHandler]:
    """
    Decorator for callback button handlers.

    Example:
        >>> @commands.callback(cmd_id="example")
        ... async def my_callback(ctx: CallbackButtonPressed):
        ...     await ctx.answer("Button clicked!")

        >>> @commands.callback(action=lambda x: x.startswith("delete_"))
        ... async def delete_callback(ctx: CallbackButtonPressed):
        ...     await ctx.answer("Deleting...")

    Arguments:
        **matchers: Key-value pairs to match in callback payload.
                   Values can be strings (exact match) or callable (custom match)

    Returns:
        Decorated callback handler
    """

    def decorator(func: typing.Callable) -> CallbackHandler:
        return CallbackHandler(func, **matchers)

    return decorator
