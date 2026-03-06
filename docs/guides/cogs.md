# Cog-модули

Cog - способ группировки команд, слушателей и обработчиков в классы для организации кода. Cog в VKFlow подобен когам из discord.py.

## Создание Cog

```python
import vkflow as vf
from vkflow import commands

class Moderation(commands.Cog):
    """Команды модерации"""

    @commands.command(name="бан")
    @commands.is_admin()
    async def ban(self, ctx: commands.Context, user: vf.User):
        await ctx.reply(f"{user:@[first_name]} забанен")

    @commands.command(name="кик")
    @commands.is_admin()
    async def kick(self, ctx: commands.Context, user: vf.User):
        await ctx.reply(f"{user:@[first_name]} кикнут")
```

!!! note "super().__init__() не обязателен"
    В VKFlow базовая инициализация Cog выполняется автоматически через `__new__`. Вы можете переопределять `__init__` без вызова `super().__init__()`.

## Подключение к App

```python
import vkflow as vf

app = vf.App(prefixes=["!"])

@app.on_startup()
async def setup(bot):
    await app.add_cog(Moderation())

app.run("TOKEN")
```

Или в `startup`:

```python
class MyApp(vf.App):
    async def startup(self, bot):
        await self.add_cog(Moderation())
```

## Cog с состоянием

Cog может хранить данные в атрибутах:

```python
class Economy(commands.Cog):
    def __init__(self):
        self.balances: dict[int, int] = {}

    @commands.command(name="баланс")
    async def balance(self, ctx: commands.Context):
        bal = self.balances.get(ctx.author, 0)
        return f"Ваш баланс: {bal}"

    @commands.command(name="дать")
    @commands.is_admin()
    async def give(self, ctx: commands.Context, user: vf.User, amount: int):
        self.balances[user.id] = self.balances.get(user.id, 0) + amount
        await ctx.reply(f"Выдано {amount} монет")
```

## Lifecycle-хуки

### cog_load / cog_unload

```python
class DatabaseCog(commands.Cog):
    async def cog_load(self):
        """Вызывается после добавления Cog в App"""
        self.db = await connect_to_database()
        print(f"Cog {self.qualified_name} загружен!")

    async def cog_unload(self):
        """Вызывается перед удалением Cog из App"""
        await self.db.close()
        print(f"Cog {self.qualified_name} выгружен!")
```

### cog_check

Глобальная проверка для всех команд в коге:

```python
class AdminCog(commands.Cog):
    def __init__(self):
        self.admin_ids = {123456, 789012}

    async def cog_check(self, ctx) -> bool:
        """Все команды в этом коге доступны только админам"""
        return ctx.author in self.admin_ids

    @commands.command(name="бан")
    async def ban(self, ctx: commands.Context, user: vf.User):
        await ctx.reply("Забанен!")

    @commands.command(name="кик")
    async def kick(self, ctx: commands.Context, user: vf.User):
        await ctx.reply("Кикнут!")
```

### cog_before_invoke / cog_after_invoke

```python
class LoggedCog(commands.Cog):
    async def cog_before_invoke(self, ctx):
        """Перед каждой командой. Верните False для отмены."""
        print(f"[{self.qualified_name}] Starting {ctx.command.name}")

    async def cog_after_invoke(self, ctx, result=None, error=None):
        """После каждой команды (всегда, даже при ошибке)"""
        if error:
            print(f"[{self.qualified_name}] Error in {ctx.command.name}: {error}")
        else:
            print(f"[{self.qualified_name}] Completed {ctx.command.name}")
```

### Обработка ошибок

```python
class SafeCog(commands.Cog):
    async def cog_command_error(self, ctx, error):
        """Информационный -вызывается для КАЖДОЙ ошибки в коге"""
        print(f"Error in {ctx.command.name}: {error}")

    async def cog_command_fallback(self, ctx, error):
        """Fallback -если ни один обработчик не обработал ошибку"""
        await ctx.send(f"Произошла ошибка: {type(error).__name__}")
```

## Слушатели в Cog

```python
class EventsCog(commands.Cog):
    @commands.listener()
    async def on_message_new(self, payload):
        print(f"New message!")

    @commands.listener()
    async def on_member_join(self, event: commands.MemberJoinEvent):
        await event.ctx.reply(f"Добро пожаловать, {event.member_id}!")

    @commands.listener("ready")
    async def bot_ready(self, bot):
        mention = await bot.mention()
        print(f"Bot ready: {mention}")
```

## Фоновые задачи в Cog

```python
from vkflow.commands import loop

class TasksCog(commands.Cog):
    def __init__(self):
        self.counter = 0

    async def cog_load(self):
        self.ticker.start()

    async def cog_unload(self):
        self.ticker.cancel()

    @loop(seconds=30)
    async def ticker(self):
        self.counter += 1
        print(f"Tick #{self.counter}")

    @ticker.before_loop
    async def before_ticker(self):
        await self.app.wait_until_ready()
```

## FSM в Cog

```python
from vkflow.app.fsm import MemoryStorage, StateGroup, State, state as fsm_state

class OrderStates(StateGroup):
    waiting_name = State()
    waiting_phone = State()

class OrderCog(commands.Cog):
    def __init__(self):
        self.fsm_storage = MemoryStorage()

    @commands.command(name="заказ")
    async def start_order(self, ctx: commands.Context):
        fsm = self.get_fsm(ctx)
        await fsm.set_state(OrderStates.waiting_name)
        await ctx.reply("Введите имя:")

    @fsm_state(OrderStates.waiting_name)
    async def handle_name(self, ctx, msg):
        await ctx.update_data(name=msg.msg.text)
        await ctx.set_state(OrderStates.waiting_phone)
        await msg.reply("Введите телефон:")

    @fsm_state(OrderStates.waiting_phone)
    async def handle_phone(self, ctx, msg):
        data = await ctx.finish()
        await msg.reply(f"Заказ: {data['name']}, тел: {msg.msg.text}")
```

## Extensions (загрузка по пути)

Вместо ручного импорта можно загружать модули по строковому пути. Модуль должен содержать функцию `setup(app)`:

```
project/
  bot.py
  cogs/
    moderation.py
    economy.py
```

**cogs/moderation.py:**

```python
import vkflow as vf
from vkflow import commands

class Moderation(commands.Cog):
    """Модерация"""

    @commands.command(name="бан")
    @commands.is_admin()
    async def ban(self, ctx: commands.Context, user: vf.User):
        await ctx.reply(f"{user:@[first_name]} забанен")

async def setup(app):
    await app.add_cog(Moderation())

async def teardown(app):
    """Опционально -вызывается при выгрузке"""
    print("Moderation cog unloaded")
```

**bot.py:**

```python
import vkflow as vf

app = vf.App(prefixes=["!"])

@app.on_startup()
async def setup(bot):
    await app.load_extension("cogs.moderation")
    await app.load_extension("cogs.economy")

app.run("TOKEN")
```

### Выгрузка и перезагрузка

```python
# Выгрузить (вызовет teardown(app), если определена)
await app.unload_extension("cogs.moderation")

# Перезагрузить (unload + load)
await app.reload_extension("cogs.moderation")
```

## Управление когами

```python
# Добавить ког
await app.add_cog(MyCog())

# Удалить ког (вызовет cog_unload)
await app.remove_cog("MyCog")

# Получить ког по имени
cog = app.get_cog("MyCog")

# Получить команду по имени
cmd = app.get_command("бан")
```

## Навигация по командам Cog

```python
cog = app.get_cog("Moderation")

# Список команд
for cmd in cog.get_commands():
    print(f"{cmd.name}: {cmd.trusted_description}")

# Рекурсивно (включая подкоманды групп)
for cmd in cog.walk_commands():
    print(cmd.name)

# FSM-состояния
states = cog.get_fsm_states()
```

## Свойства Cog

```python
class MyCog(commands.Cog):
    @commands.command(name="инфо")
    async def info(self, ctx: commands.Context):
        await ctx.send(
            f"Cog: {self.qualified_name}\n"
            f"Description: {self.description}\n"
            f"App: {self.app}\n"
        )
```

| Свойство | Описание |
|----------|----------|
| `qualified_name` | Имя кога (по умолчанию = имя класса) |
| `description` | Описание (по умолчанию = docstring класса) |
| `app` | Экземпляр App (инжектируется при `add_cog`) |
