# Команды

VKFlow предоставляет два стиля создания команд: простой через `app.command()` и расширенный через `commands.command()`.

## Простой стиль: app.command()

Подходит для небольших ботов. Команда регистрируется напрямую в приложении:

```python
import vkflow as vf

app = vf.App()

@app.command("ping")
async def ping():
    return "Pong!"

@app.command("привет", "hello", "hi")
async def greet():
    return "Привет!"

app.run("TOKEN")
```

### Параметры app.command()

```python
@app.command(
    "бан",                              # имена команды (можно несколько)
    prefixes=["/"],                      # префиксы (переопределяют глобальные)
    filter=some_filter,                  # фильтр BaseFilter
    description="Забанить пользователя", # описание
    exclude_from_autodoc=False,          # исключить из автодокументации
    routing_re_flags=re.IGNORECASE,      # флаги regex
)
async def ban(user: vf.User):
    ...
```

## Расширенный стиль: commands.command()

Для более сложных ботов -поддерживает алиасы, cooldown, before/after хуки, группы:

```python
from vkflow import commands

@commands.command(
    name="бан",
    aliases=["ban", "block"],
    prefixes=["/"],
    description="Забанить пользователя",
    help="Используйте: /бан @пользователь",
    brief="Бан пользователя",
    usage="<@пользователь>",
    hidden=False,
    enabled=True,
)
@commands.is_admin()
async def ban_cmd(ctx: commands.Context, user: vf.User):
    await ctx.reply(f"{user:@[first_name]} забанен!")

# Добавить команду в приложение
app.commands.append(ban_cmd)
```

### Минимальный вариант

```python
@commands.command()
async def hello(ctx: commands.Context):
    """Поздороваться (имя команды = имя функции)"""
    await ctx.send("Hello!")
```

## Контекст (Context)

`Context` даёт доступ к сообщению, API, боту и приложению:

```python
@app.command("инфо")
async def info(ctx: vf.Context):
    # Свойства
    ctx.msg          # объект Message
    ctx.author       # ID автора (int)
    ctx.peer_id      # peer_id чата
    ctx.text         # текст сообщения
    ctx.payload      # payload сообщения (dict | None)
    ctx.chat_id      # локальный ID чата (без смещения 2000000000)
    ctx.guild        # peer_id если чат, иначе None
    ctx.api          # экземпляр API
    ctx.bot          # экземпляр Bot
    ctx.me           # алиас для ctx.bot
    ctx.app          # экземпляр App
    ctx.command      # объект Command
    ctx.prefix       # использованный префикс
    ctx.invoked_with # имя/алиас, использованный для вызова
    ctx.clean_prefix # префикс без упоминания
    ctx.extra        # dict из command.extra
    ctx.valid        # True если контекст валиден
```

### Chat-обёртка

```python
@app.command("чат")
async def chat_info(ctx: vf.Context):
    if ctx.chat:
        members = await ctx.chat.get_members()
        await ctx.chat.kick(user_id=123)
```

### Отправка сообщений

```python
@app.command("тест")
async def test(ctx: vf.Context):
    # Отправить в тот же чат
    msg = await ctx.send("Привет!")

    # Ответить на сообщение (reply)
    msg = await ctx.reply("Ответ!")

    # Переслать в другой чат
    await ctx.forward(peer_id=123456789)

    # С вложениями
    await ctx.send("Фото", file=vf.File("photo.jpg"))
    await ctx.send("Файлы", files=[vf.File("a.jpg"), vf.File("b.jpg")])

    # С клавиатурой
    kb = vf.Keyboard(inline=True)
    kb.add_button("Кнопка", color="positive")
    await ctx.send("Выбери:", keyboard=kb)

    # С View (callback-кнопки)
    view = MyView()
    await ctx.send("Нажми:", view=view)

    # Автоудаление через N секунд
    await ctx.send("Исчезну через 5 сек!", delete_after=5)
```

### Получение отправителя

```python
@app.command("кто")
async def who(ctx: vf.Context):
    # Получить автора (User или Group)
    author = await ctx.fetch_author()
    await ctx.reply(f"Ты: {author.mention()}")

    # С падежом
    author = await ctx.fetch_author(name_case="gen")
    await ctx.reply(f"Нет {author.mention()}")

    # Конкретный тип
    user = await ctx.fetch_sender(vf.User)
    await ctx.reply(f"ID: {user.id}, Имя: {user.first_name}")
```

### Получение вложений

```python
@app.command("фотки")
async def get_photos(ctx: vf.Context):
    photos = await ctx.fetch_photos()
    docs = await ctx.fetch_docs()
    photo_bytes = await ctx.download_photos()  # list[bytes]
```

### Ожидание сообщений

```python
@app.command("имя")
async def ask_name(ctx: vf.Context):
    await ctx.send("Как тебя зовут?")

    try:
        # Ждём ответ от того же пользователя в том же чате
        reply = await ctx.wait_for_message(timeout=30)
        await ctx.send(f"Привет, {reply.msg.text}!")
    except vf.EventTimeoutError:
        await ctx.send("Время вышло!")

# Без фильтрации по автору (любое сообщение в чате)
reply = await ctx.wait_for_message(timeout=30, filter_author=False)

# Ожидание любого события
event = await ctx.wait_for("message_event", timeout=60, check=lambda e: ...)
```

### Вызов других команд

```python
@commands.command()
async def parent(ctx: commands.Context):
    # Вызвать другую команду (с проверками)
    other = ctx.app.get_command("other")
    await ctx.invoke(other, arg1="value")

    # Вызвать без проверок
    await ctx.reinvoke(other)
```

### Cooldown из контекста

```python
@commands.command()
async def status(ctx: commands.Context):
    if ctx.is_on_cooldown():
        remaining = ctx.get_cooldown_retry_after()
        await ctx.send(f"Подожди {remaining:.1f}с")
```

## Возврат строки

Если команда возвращает строку, она автоматически отправляется как reply:

```python
@app.command("ping")
async def ping():
    return "Pong!"  # Эквивалентно await ctx.reply("Pong!")
```

## Группы команд (подкоманды)

```python
from vkflow import commands

# Создание группы
@commands.group(name="config", aliases=["cfg", "conf"])
async def config(ctx: commands.Context):
    """Команды конфигурации"""
    if ctx.invoked_subcommand is None:
        await ctx.send("Используйте: !config show / !config set")

# Подкоманды
@config.command()
async def show(ctx: commands.Context):
    """Показать конфигурацию"""
    await ctx.send("Config: ...")

@config.command()
async def set(ctx: commands.Context, key: str, value: str):
    """Установить параметр"""
    await ctx.send(f"Установлено {key} = {value}")

# Вложенные группы
@config.group()
async def advanced(ctx: commands.Context):
    pass

@advanced.command()
async def reset(ctx: commands.Context):
    await ctx.send("Сброс расширенных настроек")

app.commands.append(config)
```

Пользователь вызывает: `!config show`, `!config set ключ значение`, `!config advanced reset`.

### Обход всех команд в группе

```python
cmd = app.get_command("config")
if hasattr(cmd, 'walk_commands'):
    for subcmd in cmd.walk_commands():
        print(f"{subcmd.name}: {subcmd.trusted_description}")
```

## Обработка ошибок

### Локальные обработчики

```python
@commands.command()
async def dangerous(ctx: commands.Context):
    raise ValueError("Что-то пошло не так")

# Обработка конкретного типа ошибки
@dangerous.on_error(ValueError)
async def on_value_error(ctx: commands.Context, error: ValueError):
    await ctx.send(f"Ошибка: {error}")

# Универсальный обработчик (catch-all)
@dangerous.on_error()
async def on_any_error(ctx: commands.Context, error: Exception):
    await ctx.send(f"Неизвестная ошибка: {type(error).__name__}")
```

!!! warning "on_error, а не error"
    Метод называется `on_error()`, а не `error`. Он принимает типы ошибок как аргументы. Без аргументов -catch-all.

### Цепочка обработки ошибок

При ошибке в команде обработчики проверяются в следующем порядке:

1. `cog_command_error(ctx, error)` -информационный (всегда вызывается, не обрабатывает)
2. `@command.on_error(ErrorType)` -локальные обработчики команды
3. `cog_command_fallback(ctx, error)` -fallback в коге
4. `app.on_command_error_fallback(ctx, error)` -глобальный fallback

```python
class MyApp(vf.App):
    async def on_command_error(self, ctx, error):
        """Информационный -вызывается для КАЖДОЙ ошибки"""
        print(f"Error in {ctx}: {error}")

    async def on_command_error_fallback(self, ctx, error):
        """Fallback -вызывается если ни один обработчик не подошёл"""
        await ctx.reply(f"Произошла ошибка: {error}")
```

## Хуки before/after invoke

### На уровне команды

```python
@commands.command()
async def test(ctx: commands.Context, user: vf.User):
    await ctx.send(f"Hello, {user.first_name}!")

# Перед выполнением (можно отменить, вернув False)
@test.before_invoke()
async def before_test(ctx: commands.Context):
    print(f"Запускаю {ctx.command.name}")

# Можно отменить выполнение
@test.before_invoke()
async def check_perm(ctx: commands.Context):
    if not has_permission(ctx.author):
        await ctx.send("Нет прав!")
        return False  # Отменяет команду

# После выполнения (всегда вызывается, даже при ошибке)
@test.after_invoke()
async def after_test(ctx: commands.Context, result, error):
    if error:
        print(f"Ошибка: {error}")
    else:
        print(f"Результат: {result}")
```

## Слушатели событий

### Стандартные VK-события

```python
from vkflow import commands

# По имени функции (on_ убирается автоматически)
@commands.listener()
async def on_message_new(payload):
    print(f"Новое сообщение: {payload}")

# По явному имени
@commands.listener("message_reply")
async def handle_reply(payload, user_id):
    print(f"Ответ от {user_id}")

# Встроенные алиасы: callback -> message_event, message -> message_new
@commands.listener()
async def on_ready(bot):
    print(f"Bot is ready: {bot}")
```

### Chat-action события

VKFlow автоматически оборачивает VK chat-actions в удобные event-классы:

```python
from vkflow import commands

# Вход пользователя (по приглашению или по ссылке)
@commands.listener()
async def on_member_join(event: commands.MemberJoinEvent):
    await event.ctx.reply(f"Добро пожаловать, {event.member_id}!")

# Удаление пользователя
@commands.listener()
async def on_member_remove(event: commands.MemberRemoveEvent):
    await event.ctx.reply(f"Пользователь {event.member_id} покинул чат")

# Закрепление/открепление сообщения
@commands.listener()
async def on_pin_message(event: commands.PinMessageEvent):
    print(f"Сообщение закреплено")

# Обновление чата (фото, название)
@commands.listener()
async def on_chat_edit(event: commands.ChatEditEvent):
    print(f"Чат изменён")

# Raw-режим (без обёрток)
@commands.listener()
async def on_raw_member_join(payload, member_id):
    print(f"Raw: user {member_id} joined")
```

## Фоновые задачи (Loop)

```python
from vkflow.commands import loop
import datetime

class MyCog(commands.Cog):
    def __init__(self):
        self.counter = 0

    async def cog_load(self):
        self.my_task.start()

    async def cog_unload(self):
        self.my_task.cancel()

    @loop(minutes=5)
    async def my_task(self):
        self.counter += 1
        print(f"Tick #{self.counter}")

    @my_task.before_loop
    async def before_task(self):
        await self.app.wait_until_ready()

    @my_task.after_loop
    async def after_task(self):
        print("Task stopped")

    @my_task.error
    async def on_task_error(self, error):
        print(f"Task error: {error}")
```

### Параметры loop

```python
# По интервалу
@loop(seconds=30)
@loop(minutes=5)
@loop(hours=1)

# По конкретному времени (UTC)
@loop(time=datetime.time(hour=12, minute=0))

# Несколько раз в день
@loop(time=[datetime.time(hour=9), datetime.time(hour=18)])

# Ограниченное число итераций
@loop(seconds=10, count=5)

# Управление
task = my_task.start()   # Запустить
my_task.stop()           # Остановить после текущей итерации
my_task.cancel()         # Отменить немедленно
my_task.restart()        # Перезапустить
my_task.is_running()     # Запущена ли
my_task.current_loop     # Номер текущей итерации
my_task.change_interval(seconds=10)  # Изменить интервал на лету
```

## Middleware

```python
from vkflow.commands import before_command, after_command

# Хук перед каждой командой
@before_command
async def log_command(ctx):
    print(f"Command {ctx.command.name} by {ctx.author}")

# Верните False для отмены
@before_command
async def check_banned(ctx):
    if ctx.author in BANNED_USERS:
        await ctx.send("Вы заблокированы!")
        return False

# Хук после каждой команды
@after_command
async def track_usage(ctx, result, error):
    if error:
        print(f"Error: {error}")

# Регистрация в приложении
app.middleware_manager.add_before_command_hook(log_command)
app.middleware_manager.add_after_command_hook(track_usage)
```

## Дополнительные данные команды (extra)

```python
@commands.command(extra={"category": "admin", "cost": 100})
async def admin_cmd(ctx: commands.Context):
    category = ctx.extra["category"]
    await ctx.send(f"Категория: {category}")
```

## Кастомный Context

```python
class MyContext(commands.Context):
    @property
    def db(self):
        return self.app.database

class MyApp(vf.App):
    async def get_context(self, message, *, cls=MyContext, **kwargs):
        return await super().get_context(message, cls=cls, **kwargs)

app = MyApp()
```
