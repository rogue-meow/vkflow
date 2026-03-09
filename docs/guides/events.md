# События и слушатели

VKFlow позволяет обрабатывать любые события VK API через слушатели (`listener`). Слушатели можно регистрировать как напрямую в приложении, так и внутри Cog-модулей.

## Быстрый старт

```python
import vkflow as vf

app = vf.App()

@app.listener()
async def on_message_new(payload):
    print(f"Новое сообщение: {payload}")

app.run("TOKEN")
```

Имя события определяется по имени функции — префикс `on_` убирается автоматически.

## Регистрация через app.listener()

Подходит для небольших ботов без Cog-модулей:

```python
import vkflow as vf

app = vf.App()

# По имени функции (on_ убирается)
@app.listener()
async def on_message_new(payload):
    print(f"Новое сообщение: {payload}")

# С явным именем события
@app.listener("message_reply")
async def handle_reply(payload, user_id):
    print(f"Ответ от {user_id}")

# Событие готовности бота
@app.listener()
async def on_ready(bot):
    mention = await bot.mention()
    print(f"Бот запущен: {mention}")

app.run("TOKEN")
```

## Регистрация в Cog

Для организованных проектов слушатели размещаются внутри Cog-классов:

```python
from vkflow import commands

class Events(commands.Cog):
    @commands.listener()
    async def on_message_new(self, payload):
        print(f"Новое сообщение!")

    @commands.listener("message_reply")
    async def handle_reply(self, user_id, text):
        print(f"Ответ от {user_id}: {text}")

    @commands.listener()
    async def on_ready(self, bot):
        mention = await bot.mention()
        print(f"Бот запущен: {mention}")
```

!!! note "self обязателен"
    В Cog первый параметр — всегда `self`, остальные — параметры события.

## Алиасы событий

VKFlow поддерживает короткие имена для часто используемых событий:

| Алиас | Событие VK |
|-------|------------|
| `message` | `message_new` |
| `callback` | `message_event` |
| `typing` | `message_typing_state` |
| `ready` | `ready` (внутреннее) |

```python
@app.listener()
async def on_callback(payload):
    # Эквивалентно on_message_event
    print(f"Callback-кнопка: {payload}")
```

## Инъекция параметров

Слушатели автоматически извлекают нужные данные из события по именам параметров:

```python
@app.listener()
async def on_message_new(payload, peer_id, from_id, text):
    # payload — весь объект события (dict)
    # peer_id, from_id, text — поля из payload
    print(f"[{peer_id}] {from_id}: {text}")
```

Специальные параметры:

| Параметр | Значение |
|----------|----------|
| `payload` | Весь объект события (`event.object`) |
| `event` | Объект `NewEvent` целиком |
| `bot` | Экземпляр `Bot` |

Все остальные имена параметров извлекаются из словаря `payload`.

## Chat-action события

VKFlow автоматически распознаёт действия в чатах (приглашение, кик, закрепление и т.д.) и оборачивает их в удобные event-классы.

### Типы chat-action событий

| Событие | Класс | VK action types |
|---------|-------|-----------------|
| `member_join` | `MemberJoinEvent` | `chat_invite_user`, `chat_invite_user_by_link`, `chat_invite_user_by_message_request` |
| `member_remove` | `MemberRemoveEvent` | `chat_kick_user` |
| `pin_message` | `PinMessageEvent` | `chat_pin_message` |
| `unpin_message` | `UnpinMessageEvent` | `chat_unpin_message` |
| `chat_edit` | `ChatEditEvent` | `chat_photo_update`, `chat_photo_remove`, `chat_title_update` |
| `chat_create` | `ChatCreateEvent` | `chat_create` |

### Использование

```python
from vkflow import commands

class ChatEvents(commands.Cog):
    @commands.listener()
    async def on_member_join(self, event: commands.MemberJoinEvent):
        await event.ctx.reply(f"Добро пожаловать, {event.member_id}!")

        # Дополнительные свойства
        if event.is_self_return:
            print("Пользователь вернулся сам")
        elif event.is_by_link:
            print("Пользователь зашёл по ссылке")

    @commands.listener()
    async def on_member_remove(self, event: commands.MemberRemoveEvent):
        if event.is_self_leave:
            await event.ctx.reply("Пользователь покинул чат")
        elif event.is_kicked:
            await event.ctx.reply(f"Пользователь {event.member_id} кикнут")

    @commands.listener()
    async def on_pin_message(self, event: commands.PinMessageEvent):
        print(f"Сообщение {event.conversation_message_id} закреплено")

    @commands.listener()
    async def on_chat_edit(self, event: commands.ChatEditEvent):
        if event.is_title_update:
            print(f"Название чата изменено: {event.text}")
        elif event.is_photo_update:
            print("Фото чата обновлено")
```

Или напрямую в приложении:

```python
@app.listener()
async def on_member_join(event: commands.MemberJoinEvent):
    await event.ctx.reply(f"Добро пожаловать, {event.member_id}!")
```

### Свойства event-классов

**MemberJoinEvent:**

| Свойство | Тип | Описание |
|----------|-----|----------|
| `member_id` | `int` | ID вступившего пользователя |
| `inviter_id` | `int \| None` | ID пригласившего (если есть) |
| `is_self_return` | `bool` | Пользователь вернулся сам |
| `is_by_link` | `bool` | Вступил по ссылке |
| `is_by_request` | `bool` | Вступил по заявке |

**MemberRemoveEvent:**

| Свойство | Тип | Описание |
|----------|-----|----------|
| `member_id` | `int` | ID удалённого пользователя |
| `kicker_id` | `int \| None` | ID кикнувшего (если есть) |
| `is_self_leave` | `bool` | Пользователь ушёл сам |
| `is_kicked` | `bool` | Пользователь был кикнут |

**PinMessageEvent / UnpinMessageEvent:**

| Свойство | Тип | Описание |
|----------|-----|----------|
| `member_id` | `int` | ID выполнившего действие |
| `conversation_message_id` | `int` | ID сообщения в беседе |
| `message` | `str` | Текст сообщения (только PinMessageEvent) |

**ChatEditEvent:**

| Свойство | Тип | Описание |
|----------|-----|----------|
| `text` | `str \| None` | Новое значение (название/URL фото) |
| `is_title_update` | `bool` | Изменение названия |
| `is_photo_update` | `bool` | Обновление фото |

У всех event-классов есть общие свойства: `ctx`, `bot`, `api`, `payload`.

### Алиасы chat-action событий

Можно слушать группу событий или конкретный VK action type:

```python
# Группа: member_join ловит invite_user + invite_by_link + invite_by_request
@app.listener()
async def on_member_join(event): ...

# Конкретный тип
@app.listener()
async def on_chat_invite_user_by_link(event): ...

# Конкретный тип через явное имя
@app.listener("chat_invite_user")
async def on_invite(event): ...
```

## Raw-режим

Префикс `raw_` (или `on_raw_`) отключает обёртки event-классов и передаёт сырые данные:

```python
from vkflow import commands

class RawEvents(commands.Cog):
    # Сырое VK-событие
    @commands.listener()
    async def on_raw_message_new(self, payload, from_id, text):
        print(f"Raw: {from_id} написал {text}")

    # Сырое chat-action (dict вместо event-класса)
    @commands.listener()
    async def on_raw_member_join(self, payload, member_id):
        print(f"Raw: user {member_id} joined")
```

В raw-режиме параметры извлекаются напрямую из словаря `payload` по именам.

## Ожидание событий (wait_for)

`wait_for` позволяет приостановить выполнение и дождаться конкретного события:

```python
import vkflow as vf

app = vf.App()

@app.command("подтверди")
async def confirm(ctx: vf.Context):
    await ctx.send("Нажмите callback-кнопку для подтверждения")

    try:
        event = await app.wait_for(
            "message_event",
            timeout=30,
            check=lambda e: e.event.object.get("user_id") == ctx.author
        )
        await ctx.send("Подтверждено!")
    except vf.EventTimeoutError:
        await ctx.send("Время вышло!")
```

### Параметры wait_for

| Параметр | Тип | Описание |
|----------|-----|----------|
| `event_name` | `str` | Имя события для ожидания |
| `timeout` | `float \| None` | Таймаут в секундах (`None` — без ограничения) |
| `check` | `Callable \| None` | Функция-фильтр, должна вернуть `True` для нужного события |

`wait_for` также доступен через контекст:

```python
@app.command("имя")
async def ask_name(ctx: vf.Context):
    await ctx.send("Как тебя зовут?")

    try:
        reply = await ctx.wait_for_message(timeout=30)
        await ctx.send(f"Привет, {reply.msg.text}!")
    except vf.EventTimeoutError:
        await ctx.send("Время вышло!")
```

## Ручная отправка событий (dispatch_event)

Можно программно генерировать события:

```python
# Отправить кастомное событие
await app.dispatch_event("my_custom_event", data="hello")

# Слушатель поймает его
@app.listener("my_custom_event")
async def on_custom(payload):
    print(f"Получено: {payload}")
```

## Низкоуровневый on_event

Для прямого доступа к `NewEvent` без инъекции параметров:

```python
from vkflow.event import GroupEvent

@app.on_event(GroupEvent.MESSAGE_NEW)
async def raw_handler(event):
    # event — объект NewEvent
    print(event.event.object)
```

`on_event` принимает `EventType` (enum) и передаёт в обработчик полный `NewEvent`.

## Полный пример

```python
import vkflow as vf
from vkflow import commands

app = vf.App(prefixes=["!"])

class MyEvents(commands.Cog):
    """Обработка всех событий бота"""

    @commands.listener()
    async def on_ready(self, bot):
        mention = await bot.mention()
        print(f"Бот запущен: {mention}")

    @commands.listener()
    async def on_message_new(self, payload):
        text = payload.get("text", "")
        if "привет" in text.lower():
            print("Кто-то поздоровался!")

    @commands.listener()
    async def on_member_join(self, event: commands.MemberJoinEvent):
        await event.ctx.reply(
            f"Добро пожаловать! Твой ID: {event.member_id}"
        )

    @commands.listener()
    async def on_member_remove(self, event: commands.MemberRemoveEvent):
        if event.is_kicked:
            await event.ctx.reply("Пользователь был кикнут")

    @commands.listener()
    async def on_pin_message(self, event: commands.PinMessageEvent):
        await event.ctx.reply(f"Сообщение закреплено: {event.message}")

@app.on_startup()
async def setup(bot):
    await app.add_cog(MyEvents())

app.run("TOKEN")
```
