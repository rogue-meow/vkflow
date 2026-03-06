---
hide:
  - navigation
---

# Примеры

## Простой бот

```python
import vkflow as vf

app = vf.App(prefixes=["!"])

@app.command("ping")
async def ping():
    return "Pong!"

@app.command("привет")
async def greet(user: vf.User):
    return f"Привет, {user:@[first_name]}!"

@app.command("дата")
async def reg_date(user: vf.User):
    date = await vf.get_user_registration_date(user.id)
    return f"{user:@[first_name]} зарегистрирован {date:%d.%m.%Y}"

app.run("$VK_TOKEN")
```

## Бот с проверками и cooldown

```python
import vkflow as vf
from vkflow import commands

app = vf.App(prefixes=["!"])

@commands.command(name="бонус")
@commands.cooldown(rate=1, per=3600, type=commands.BucketType.USER)
@vf.is_group_chat()
async def bonus(ctx: commands.Context):
    await ctx.reply("Вы получили бонус!")

@bonus.on_cooldown()
async def bonus_cd(ctx, remaining: float):
    await ctx.send(f"Подождите {remaining:.0f} сек.")

app.commands.append(bonus)
app.run("$VK_TOKEN")
```

## Бот с клавиатурой и View

```python
import vkflow as vf
from vkflow.ui.view import View, button

class MenuView(View):
    def __init__(self):
        super().__init__(timeout=120, inline=True)

    @button(label="Информация", color="primary")
    async def info_btn(self, interaction):
        await interaction.show_snackbar("VKFlow bot v1.0")

    @button(label="Помощь", color="positive")
    async def help_btn(self, interaction):
        await interaction.show_snackbar("Напишите !помощь")

app = vf.App(prefixes=["!"])

@app.command("меню")
async def menu(ctx: vf.Context):
    view = MenuView()
    await ctx.send("Главное меню:", view=view)

app.run("$VK_TOKEN")
```

## Бот с FSM (анкета)

```python
import vkflow as vf
from vkflow.app.fsm import StateGroup, State, MemoryStorage

class Survey(StateGroup):
    name = State()
    age = State()

app = vf.App(prefixes=["!"])
app.set_fsm_storage(MemoryStorage())

@app.command("анкета")
async def start(ctx: vf.NewMessage):
    fsm = app.get_fsm(ctx)
    await fsm.set_state(Survey.name)
    await ctx.reply("Как вас зовут?")

@app.state(Survey.name)
async def get_name(ctx, msg):
    await ctx.update_data(name=msg.msg.text)
    await ctx.set_state(Survey.age)
    await msg.reply("Сколько вам лет?")

@app.state(Survey.age)
async def get_age(ctx, msg):
    data = await ctx.finish()
    await msg.reply(f"Анкета: {data['name']}, {msg.msg.text} лет")

app.run("$VK_TOKEN")
```

## Бот с Cog-модулями

```python
import vkflow as vf
from vkflow import commands

class Admin(commands.Cog):
    """Административные команды"""

    async def cog_check(self, ctx) -> bool:
        return ctx.peer_id > 2000000000  # Только в чатах

    @commands.command(name="кик")
    @commands.is_admin()
    async def kick(self, ctx: commands.Context, user: vf.User):
        if ctx.chat:
            await ctx.chat.kick(user_id=user.id)
            await ctx.reply(f"{user:@[first_name]} кикнут!")

class Fun(commands.Cog):
    """Развлечения"""

    @commands.command(name="монетка")
    async def coin(self, ctx: commands.Context):
        import random
        result = random.choice(["Орёл", "Решка"])
        await ctx.reply(f"Выпало: {result}")

    @commands.command(name="кубик")
    async def dice(self, ctx: commands.Context):
        import random
        await ctx.reply(f"Выпало: {random.randint(1, 6)}")

app = vf.App(prefixes=["!"])

@app.on_startup()
async def setup(bot):
    await app.add_cog(Admin())
    await app.add_cog(Fun())

app.run("$VK_TOKEN")
```

## Бот с группами команд

```python
import vkflow as vf
from vkflow import commands

@commands.group(name="config", aliases=["cfg"])
async def config(ctx: commands.Context):
    if ctx.invoked_subcommand is None:
        await ctx.send("Подкоманды: show, set, reset")

@config.command()
async def show(ctx: commands.Context):
    await ctx.send("Текущая конфигурация: ...")

@config.command()
async def set(ctx: commands.Context, key: str, value: str):
    await ctx.send(f"Установлено: {key} = {value}")

@config.command()
async def reset(ctx: commands.Context):
    await ctx.send("Конфигурация сброшена!")

app = vf.App(prefixes=["!"])
app.commands.append(config)
app.run("$VK_TOKEN")
```

## Бот с фоновыми задачами

```python
import vkflow as vf
from vkflow import commands
from vkflow.commands import loop

class Reminder(commands.Cog):
    def __init__(self, chat_id: int):
        self.chat_id = chat_id

    async def cog_load(self):
        self.remind.start()

    async def cog_unload(self):
        self.remind.cancel()

    @loop(hours=1)
    async def remind(self):
        bot = self.app._bots[0]
        await bot.api.messages.send(
            peer_id=self.chat_id,
            message="Ежечасное напоминание!",
            random_id=vf.random_id(),
        )

    @remind.before_loop
    async def before_remind(self):
        await self.app.wait_until_ready()

app = vf.App(prefixes=["!"])

@app.on_startup()
async def setup(bot):
    await app.add_cog(Reminder(chat_id=2000000001))

app.run("$VK_TOKEN")
```

## Мульти-бот

```python
import vkflow as vf

app = vf.App(prefixes=["!"])

@app.command("кто_я")
async def who_am_i(ctx: vf.Context):
    mention = await ctx.bot.mention()
    return f"Я - {mention}"

# Три бота с одними командами
app.run("TOKEN_BOT_1", "TOKEN_BOT_2", "TOKEN_BOT_3")
```

## API-клиент

```python
import vkflow as vf

app = vf.App(prefixes=["!"])

@app.command("стена")
async def wall(ctx: vf.Context):
    # Dot-notation для методов API
    posts = await ctx.api.wall.get(owner_id=ctx.author, count=5)

    texts = [p["text"][:50] for p in posts["items"] if p["text"]]
    await ctx.reply("\n".join(texts) or "Нет постов")

@app.command("загрузить_фото")
async def upload_photo(ctx: vf.Context):
    photos = await ctx.api.upload_photos_to_message(
        "https://example.com/image.jpg",
        peer_id=ctx.peer_id,
    )
    await ctx.send("Вот фото:", attachments=photos)

@app.command("загрузить_док")
async def upload_doc(ctx: vf.Context):
    doc = await ctx.api.upload_doc_to_message(
        b"Hello, world!",
        "test.txt",
        peer_id=ctx.peer_id,
    )
    await ctx.send("Документ:", attachment=doc)
```
