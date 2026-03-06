"""
Пример работы с событиями (listeners).

Демонстрирует:
- Стандартные VK-события (message_new, message_reply и т.д.)
- События чат-действий (member_join, member_remove, pin/unpin)
- Собственные события (ready, command, command_error)
- Raw-события (on_raw_*)
- Listener в Cog
- Dispatch своих кастомных событий
"""

import vkflow

from vkflow import commands

from vkflow.commands import listener
from vkflow.commands.chat_actions import (
    MemberJoinEvent,
    MemberRemoveEvent,
    PinMessageEvent,
    ChatTitleUpdateEvent,
)


app = vkflow.App(prefixes=["!"])


# =============================================
# 1. Стандартные VK-события (standalone)
# =============================================


# Имя функции определяет событие: on_message_new → message_new
@listener()
async def on_message_new(event):
    """Вызывается при каждом новом сообщении"""
    print(f"Новое событие message_new: {event}")


# Явное указание события
@listener("message_reply")
async def handle_reply(event, payload):
    """Вызывается при ответе бота"""
    print(f"Бот ответил: {payload}")


# Событие typing
@listener()
async def on_typing(event):
    """Пользователь печатает"""
    print("Кто-то печатает...")


# Регистрируем standalone-листенеры в пакете
app.event_handlers.setdefault("message_new", []).append(on_message_new)
app.event_handlers.setdefault("message_reply", []).append(handle_reply)
app.event_handlers.setdefault("message_typing_state", []).append(on_typing)


# =============================================
# 2. События чат-действий
# =============================================


class WelcomeCog(commands.Cog):
    """Приветствие новых участников и логирование действий в чате"""

    # --- Вступление участника ---
    @listener()
    async def on_member_join(self, event: MemberJoinEvent):
        """
        Вызывается при вступлении пользователя в чат.
        Ловит: chat_invite_user, chat_invite_user_by_link
        """
        await event.ctx.reply(f"Добро пожаловать, [id{event.member_id}|участник]! 🎉")

    # --- Выход/кик участника ---
    @listener()
    async def on_member_remove(self, event: MemberRemoveEvent):
        """Вызывается при выходе или кике пользователя"""
        await event.ctx.reply(f"Пользователь [id{event.member_id}|участник] покинул чат. 👋")

    # --- Закрепление сообщения ---
    @listener()
    async def on_pin_message(self, event: PinMessageEvent):
        """Вызывается при закреплении сообщения"""
        await event.ctx.reply(f"Сообщение закреплено! ID: {event.conversation_message_id}")

    # --- Изменение названия чата ---
    @listener()
    async def on_title_update(self, event: ChatTitleUpdateEvent):
        """Вызывается при изменении названия беседы"""
        await event.ctx.reply(f"Новое название чата: {event.text}")


# =============================================
# 3. Raw-события (без обёртки ChatActionEvent)
# =============================================


class RawEventsCog(commands.Cog):
    """Обработка raw-событий"""

    # Raw-версия: получаем сырой dict вместо обёрток
    @listener("raw_member_join")
    async def on_raw_join(self, payload, member_id):
        """raw_* версия - payload содержит сырые данные VK"""
        print(f"[RAW] Вступил пользователь {member_id}")

    @listener("raw_chat_invite_user")
    async def on_raw_invite(self, payload, member_id):
        """Конкретный тип действия (не обобщённый member_join)"""
        print(f"[RAW] Приглашён пользователь {member_id}")


# =============================================
# 4. Собственные события фреймворка
# =============================================


class BotEventsCog(commands.Cog):
    """Обработка событий фреймворка"""

    # Событие ready - бот запущен и готов к работе
    @listener()
    async def on_ready(self, bot):
        """Вызывается когда бот полностью готов"""
        mention = await bot.mention()
        print(f"Бот {mention} готов!")

    # Событие command - команда вызвана
    @listener("command")
    async def on_command(self, context, command, arguments):
        """Вызывается при каждом вызове команды"""
        print(f"Команда: {command.name}, аргументы: {arguments}")

    # Событие command_complete - команда завершена успешно
    @listener("command_complete")
    async def on_command_complete(self, context, command, result):
        """Вызывается при успешном завершении команды"""
        print(f"Команда {command.name} завершена")

    # Событие command_error - ошибка в команде
    @listener("command_error")
    async def on_command_error(self, context, command, error):
        """Вызывается при ошибке в команде"""
        print(f"Ошибка в {command.name}: {error}")


# =============================================
# 5. Listener через Cog.listener() (альтернативный синтаксис)
# =============================================


class AltListenerCog(commands.Cog):
    """Альтернативный способ регистрации листенеров через Cog.listener()"""

    @commands.Cog.listener("message_new")
    async def handle_all_messages(self, event):
        """Обработка всех сообщений через Cog.listener()"""
        print("[ALT] Новое сообщение")


# =============================================
# 6. Dispatch своих событий
# =============================================
# app.dispatch() позволяет отправлять произвольные
# события, на которые можно подписаться через listener.


class AwardCog(commands.Cog):
    """Пример с кастомными событиями"""

    @commands.command()
    async def award(self, ctx: commands.Context, user_id: int, reason: str):
        """Выдать награду и уведомить через кастомное событие"""
        await ctx.app.dispatch(
            "award_given",
            user_id=user_id,
            reason=reason,
            awarded_by=ctx.author_id,
        )

        await ctx.reply(f"Награда выдана пользователю [id{user_id}|участнику]!")

    @listener("award_given")
    async def on_award_given(self, user_id, reason, awarded_by, **kwargs):
        """Логирование всех наград"""
        print(f"[AWARD] Пользователь {awarded_by} наградил {user_id}: {reason}")


# =============================================
# Тестовые команды
# =============================================


@app.command()
async def test(ctx: commands.Context):
    """Тестовая команда для проверки событий"""
    await ctx.send("Тестовое сообщение!")


@app.command()
async def error_test(ctx: commands.Context):
    """Команда, вызывающая ошибку (для проверки command_error)"""
    raise ValueError("Тестовая ошибка!")


# =============================================
# Запуск
# =============================================


async def setup():
    await app.add_cog(WelcomeCog())
    await app.add_cog(RawEventsCog())
    await app.add_cog(BotEventsCog())
    await app.add_cog(AltListenerCog())
    await app.add_cog(AwardCog())


app.run_when_ready(setup)
app.run("$VK_TOKEN")
