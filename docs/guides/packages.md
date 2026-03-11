# Package-модули

Package — функциональная альтернатива [Cog-модулям](cogs.md) для организации кода. Вместо классов используются декораторы на уровне модуля, что делает код проще и ближе к стилю самого `App`.

## Cog vs Package

| | Cog | Package |
|---|---|---|
| Стиль | Классы (ООП) | Функции и декораторы |
| Состояние | Атрибуты экземпляра (`self.data`) | Переменные модуля |
| Lifecycle | `cog_load` / `cog_unload` | `on_startup` / `on_shutdown` |
| Подключение | `await app.add_cog(MyCog())` | `app.include_package(pkg)` |
| FSM | `self.fsm_storage = ...` | `Package(fsm_storage=...)` |
| Лучше для | Сложная логика с состоянием | Простые модули, скрипты, быстрое прототипирование |

## Создание Package

```python
import vkflow as vf
from vkflow.app import Package

pkg = Package(prefixes=["/"])

@pkg.command("пинг")
async def ping(ctx: vf.Context):
    await ctx.reply("Понг!")

@pkg.command("инфо")
async def info(ctx: vf.Context):
    await ctx.reply(f"Пакет: {pkg.name}")
```

!!! note "Автоматическое имя"
    Имя пакета определяется автоматически по имени переменной (`pkg`), модуля или файла. Можно задать явно: `Package(name="moderation")`.

## Подключение к App

```python
import vkflow as vf
from my_packages.moderation import pkg as moderation_pkg

app = vf.App(prefixes=["/"])
app.include_package(moderation_pkg)

app.run("$VK_TOKEN")
```

## Команды

### Простые команды

```python
@pkg.command("привет", "хай")
async def hello(ctx: vf.Context):
    await ctx.reply("Привет!")
```

Первый аргумент — основное имя, остальные — алиасы.

### Параметры команды

```python
@pkg.command(
    "бан",
    description="Забанить пользователя",
    hidden=False,
    enabled=True,
)
async def ban(ctx: vf.Context, user: vf.User):
    await ctx.reply(f"{user:@[first_name]} забанен")
```

### Группы команд

```python
@pkg.group("настройки", invoke_without_command=True)
async def settings(ctx: vf.Context):
    await ctx.reply("Используйте: настройки язык / настройки тема")

@settings.command("язык")
async def set_lang(ctx: vf.Context, lang: str):
    await ctx.reply(f"Язык изменён на {lang}")

@settings.command("тема")
async def set_theme(ctx: vf.Context, theme: str):
    await ctx.reply(f"Тема изменена на {theme}")
```

## События

```python
@pkg.listener()
async def on_message_new(payload):
    print(f"Новое сообщение: {payload}")

@pkg.listener("message_reply")
async def handle_reply(payload):
    print(f"Ответ: {payload}")
```

## Обработка сырых сообщений

```python
@pkg.on_message()
async def log_all(msg):
    print(f"[{msg.msg.from_id}] {msg.msg.text}")
```

С фильтром:

```python
from vkflow.app.filters import RegexFilter

@pkg.on_message(filter=RegexFilter(r".*бот.*"))
async def bot_mention(msg):
    await msg.reply("Вы упомянули бота!")
```

## Lifecycle-хуки

```python
@pkg.on_startup()
async def startup(bot):
    print(f"Пакет {pkg.name} запущен")

@pkg.on_shutdown()
async def shutdown(bot):
    print(f"Пакет {pkg.name} остановлен")
```

## Хуки команд

### before_invoke / after_invoke

Один обработчик на пакет, аналог `cog_before_invoke` / `cog_after_invoke`:

```python
@pkg.before_invoke()
async def before(ctx):
    print(f"Запуск команды: {ctx.command.name}")

@pkg.after_invoke()
async def after(ctx, result=None, error=None):
    if error:
        print(f"Ошибка: {error}")
```

Если `before_invoke` вернёт `False`, выполнение команды будет отменено.

### before_command / after_command (middleware)

Можно зарегистрировать несколько обработчиков:

```python
@pkg.before_command()
async def log_command(ctx):
    print(f"Команда: {ctx.command.name}")

@pkg.before_command()
async def check_maintenance(ctx):
    if MAINTENANCE_MODE:
        await ctx.reply("Бот на обслуживании")
        return False
```

## Обработка ошибок

```python
@pkg.error_handler()
async def on_error(ctx, error):
    """Информационный — вызывается при любой ошибке (не влияет на поток)"""
    print(f"Ошибка в {ctx.command.name}: {error}")

@pkg.error_fallback()
async def fallback(ctx, error):
    """Fallback — если ошибка не обработана другими обработчиками"""
    await ctx.send(f"Произошла ошибка: {type(error).__name__}")
```

## FSM в Package

Package поддерживает FSM напрямую — передайте хранилище при создании:

```python
from vkflow.app import Package
from vkflow.app.fsm import MemoryStorage, StateGroup, State

class OrderStates(StateGroup):
    waiting_name = State()
    waiting_phone = State()

pkg = Package(prefixes=["/"], fsm_storage=MemoryStorage())

@pkg.command("заказ")
async def start_order(ctx):
    fsm = pkg.get_fsm(ctx)
    await fsm.set_state(OrderStates.waiting_name)
    await ctx.reply("Введите имя:")

@pkg.state(OrderStates.waiting_name)
async def handle_name(ctx, msg):
    await ctx.update_data(name=msg.msg.text)
    await ctx.set_state(OrderStates.waiting_phone)
    await msg.reply("Введите телефон:")

@pkg.state(OrderStates.waiting_phone)
async def handle_phone(ctx, msg):
    data = await ctx.finish()
    await msg.reply(f"Заказ: {data['name']}, тел: {msg.msg.text}")
```

### Инъекция параметров в обработчиках состояний

Аргументы инжектируются по имени — так же, как в `app.state()`:

| Имя параметра | Что подставляется |
|---------------|-------------------|
| `ctx`, `fsm` | `FSMContext` |
| `msg`, `message` | `NewMessage` |
| `data` | Текущие данные FSM (`dict`) |
| `state` | Текущее состояние (`str`) |

## Обработка кнопок

```python
@pkg.on_clicked_button()
async def handle_click(msg):
    await msg.reply("Кнопка нажата!")

@pkg.on_called_button()
async def handle_callback(ctx):
    await ctx.show_snackbar("Callback получен!")
```

## События чата

```python
@pkg.on_returned_user()
async def user_returned(msg, user_id):
    await msg.reply(f"С возвращением, {user_id}!")

@pkg.on_user_joined_by_link()
async def joined_by_link(msg, user_id):
    await msg.reply(f"Пользователь {user_id} присоединился по ссылке")

@pkg.on_added_page()
async def user_added(msg, added_user, invited_by):
    await msg.reply(f"{invited_by} добавил {added_user}")
```

## Навигация по командам

```python
for cmd in pkg.get_commands():
    print(f"{cmd.name}: {cmd.trusted_description}")

for cmd in pkg.walk_commands():
    print(cmd.name)

states = pkg.get_fsm_states()
```

## Пример: структура проекта

```
project/
  bot.py
  packages/
    moderation.py
    economy.py
    fun.py
```

**packages/moderation.py:**

```python
import vkflow as vf
from vkflow.app import Package

pkg = Package(prefixes=["/"])

@pkg.command("бан")
async def ban(ctx: vf.Context, user: vf.User):
    await ctx.reply(f"{user:@[first_name]} забанен")

@pkg.command("кик")
async def kick(ctx: vf.Context, user: vf.User):
    await ctx.reply(f"{user:@[first_name]} кикнут")
```

**bot.py:**

```python
import vkflow as vf
from packages.moderation import pkg as moderation
from packages.economy import pkg as economy

app = vf.App(prefixes=["/"])
app.include_package(moderation)
app.include_package(economy)

app.run("$VK_TOKEN")
```
