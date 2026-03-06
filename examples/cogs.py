"""
Детальный пример системы Cog (когов).

Демонстрирует:
- Создание Cog (без обязательного super().__init__())
- Команды и подкоманды в Cog
- Lifecycle: cog_load / cog_unload
- cog_check - глобальная проверка для всех команд кога
- cog_before_invoke / cog_after_invoke - хуки
- cog_command_error / cog_command_fallback - обработка ошибок
- Listener в Cog
- Loop (фоновые задачи) в Cog
- Динамическая загрузка/выгрузка когов
- Extensions (модульная загрузка)
"""

import datetime

import vkflow

from vkflow import commands
from vkflow.commands import listener, loop


app = vkflow.App(prefixes=["!"])


# =============================================
# 1. Простой Cog
# =============================================


class BasicCog(commands.Cog):
    """Простой ког - super().__init__() НЕ требуется"""

    @commands.command()
    async def hello(self, ctx: commands.Context):
        """Приветствие"""
        await ctx.send(f"Привет от {self.qualified_name}!")

    @commands.command(aliases=["p"])
    async def ping(self, ctx: commands.Context):
        """Проверка"""
        return "Pong!"


# =============================================
# 2. Cog с конструктором и состоянием
# =============================================


class CounterCog(commands.Cog):
    """Ког со счётчиком - пример Cog с __init__"""

    def __init__(self, initial: int = 0):
        # super().__init__() вызывать НЕ обязательно - базовая
        # инициализация происходит автоматически в __new__
        self.count = initial

    @commands.command()
    async def increment(self, ctx: commands.Context, amount: int = 1):
        """Увеличить счётчик: !increment 5"""
        self.count += amount
        await ctx.send(f"Счётчик: {self.count}")

    @commands.command()
    async def decrement(self, ctx: commands.Context, amount: int = 1):
        """Уменьшить счётчик: !decrement 3"""
        self.count -= amount
        await ctx.send(f"Счётчик: {self.count}")

    @commands.command()
    async def count_value(self, ctx: commands.Context):
        """Текущее значение счётчика"""
        await ctx.send(f"Счётчик: {self.count}")


# =============================================
# 3. Lifecycle: cog_load / cog_unload
# =============================================


class DatabaseCog(commands.Cog):
    """Ког с lifecycle-хуками"""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def cog_load(self):
        """Вызывается при загрузке кога в App"""
        print(f"[{self.qualified_name}] Загружен! Инициализация БД...")
        self.data = {"default_key": "default_value"}

    async def cog_unload(self):
        """Вызывается при выгрузке кога"""
        print(f"[{self.qualified_name}] Выгружается. Сохранение данных...")
        self.data.clear()

    @commands.command()
    async def db_get(self, ctx: commands.Context, key: str):
        """Получить значение: !db_get key"""
        value = self.data.get(key, "не найдено")
        await ctx.send(f"{key} = {value}")

    @commands.command()
    async def db_set(self, ctx: commands.Context, key: str, value: str):
        """Установить значение: !db_set key value"""
        self.data[key] = value
        await ctx.send(f"Сохранено: {key} = {value}")


# =============================================
# 4. cog_check - глобальная проверка
# =============================================


class AdminCog(commands.Cog):
    """Ког, доступный только администраторам"""

    ADMIN_IDS = {123456, 789012}

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Все команды этого кога доступны только админам"""
        if ctx.author not in self.ADMIN_IDS:
            await ctx.send("Только для администраторов!")

            return False
        return True

    @commands.command()
    async def admin_info(self, ctx: commands.Context):
        """Информация (только для админов)"""
        await ctx.send(f"Админов: {len(self.ADMIN_IDS)}")

    @commands.command()
    async def admin_kick(self, ctx: commands.Context, user_id: int):
        """Кикнуть пользователя (только для админов)"""
        await ctx.send(f"Пользователь {user_id} кикнут!")


# =============================================
# 5. Before/After invoke хуки в Cog
# =============================================


class LoggedCog(commands.Cog):
    """Ког с логированием всех команд"""

    async def cog_before_invoke(self, ctx: commands.Context):
        """Вызывается перед каждой командой в этом коге"""
        print(f"[BEFORE] {ctx.command.name} от {ctx.author}")
        # Верните False для отмены:
        # return False

    async def cog_after_invoke(self, ctx, result=None, error=None):
        """Вызывается после каждой команды (успех или ошибка)"""
        if error:
            print(f"[AFTER] {ctx.command.name} ОШИБКА: {error}")
        else:
            print(f"[AFTER] {ctx.command.name} OK, результат: {result}")

    @commands.command()
    async def logged_cmd(self, ctx: commands.Context):
        """Команда с автоматическим логированием"""
        await ctx.send("Эта команда логируется!")


# =============================================
# 6. Обработка ошибок в Cog
# =============================================


class SafeCog(commands.Cog):
    """Ког с полной обработкой ошибок"""

    async def cog_command_error(self, ctx, error):
        """
        Информационный обработчик - вызывается ВСЕГДА при ошибке.
        Не влияет на дальнейшую обработку.
        """
        print(f"[COG ERROR] {ctx.command.name}: {error}")

    async def cog_command_fallback(self, ctx, error):
        """
        Fallback - вызывается если ни один @on_error не обработал ошибку.
        Если завершается без raise - ошибка считается обработанной.
        """
        await ctx.send(f"Произошла ошибка: {type(error).__name__}")

    @commands.command()
    async def safe(self, ctx: commands.Context):
        """Безопасная команда с fallback"""
        raise RuntimeError("Тестовая ошибка!")

    @commands.command()
    async def divide(self, ctx: commands.Context, a: int, b: int):
        """Деление: !divide 10 2"""
        result = a / b
        await ctx.send(f"{a} / {b} = {result}")

    # Локальный обработчик для конкретной команды
    @divide.on_error(ZeroDivisionError)
    async def on_divide_zero(self, ctx: commands.Context, error):
        await ctx.send("Деление на ноль!")


# =============================================
# 7. Listeners в Cog
# =============================================


class EventsCog(commands.Cog):
    """Ког с обработчиками событий"""

    @listener()
    async def on_ready(self, bot):
        """Бот готов к работе"""
        print("EventsCog: бот готов!")

    @listener("command_complete")
    async def on_command_done(self, context, command, **kw):
        """Команда успешно выполнена"""
        print(f"Команда {command.name} завершена")


# =============================================
# 8. Loop (фоновые задачи) в Cog
# =============================================


class TasksCog(commands.Cog):
    """Ког с фоновыми задачами"""

    def __init__(self):
        self.tick_count = 0

    async def cog_load(self):
        self.ticker.start()

    async def cog_unload(self):
        self.ticker.cancel()

    @loop(seconds=30)
    async def ticker(self):
        """Тикает каждые 30 секунд"""
        self.tick_count += 1
        print(f"[TICK #{self.tick_count}] {datetime.datetime.now()}")

    @ticker.before_loop
    async def before_ticker(self):
        await self.app.wait_until_ready()

    @commands.command()
    async def ticks(self, ctx: commands.Context):
        """Показать количество тиков"""
        await ctx.send(f"Тиков: {self.tick_count}")


# =============================================
# 9. Подкоманды (Group) в Cog
# =============================================


class SettingsCog(commands.Cog):
    """Ког с подкомандами"""

    def __init__(self):
        self.settings = {"language": "ru", "theme": "dark"}

    @commands.group()
    async def settings(self, ctx: commands.Context):
        """Настройки бота: !settings [show|set|reset]"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Подкоманды: show, set, reset")

    @settings.command()
    async def show(self, ctx: commands.Context):
        """Показать настройки"""
        text = "\n".join(f"  {k}: {v}" for k, v in self.settings.items())
        await ctx.send(f"Настройки:\n{text}")

    @settings.command()
    async def set(self, ctx: commands.Context, key: str, value: str):
        """Установить настройку: !settings set language en"""
        self.settings[key] = value
        await ctx.send(f"Установлено: {key} = {value}")

    @settings.command()
    async def reset(self, ctx: commands.Context):
        """Сбросить настройки"""
        self.settings = {"language": "ru", "theme": "dark"}
        await ctx.send("Настройки сброшены!")


# =============================================
# 10. Динамическая загрузка/выгрузка когов
# =============================================


@app.command()
async def load_cog(ctx: commands.Context, name: str):
    """Загрузить ког: !load_cog CounterCog"""
    cog_map = {
        "CounterCog": CounterCog,
        "DatabaseCog": DatabaseCog,
        "TasksCog": TasksCog,
    }

    cog_cls = cog_map.get(name)

    if cog_cls is None:
        return f"Ког '{name}' не найден. Доступные: {', '.join(cog_map)}"

    try:
        await app.add_cog(cog_cls())
        await ctx.send(f"Ког '{name}' загружен!")
    except ValueError as e:
        await ctx.send(f"Ошибка: {e}")


@app.command()
async def unload_cog(ctx: commands.Context, name: str):
    """Выгрузить ког: !unload_cog CounterCog"""
    try:
        await app.remove_cog(name)
        await ctx.send(f"Ког '{name}' выгружен!")
    except ValueError as e:
        await ctx.send(f"Ошибка: {e}")


@app.command()
async def list_cogs(ctx: commands.Context):
    """Список загруженных когов"""
    cogs = list(app._cogs.keys())

    if not cogs:
        return "Нет загруженных когов."

    await ctx.send("Загруженные коги:\n" + "\n".join(f"  - {c}" for c in cogs))


# =============================================
# Запуск
# =============================================


async def setup():
    await app.add_cog(BasicCog())
    await app.add_cog(CounterCog(initial=10))
    await app.add_cog(DatabaseCog())
    await app.add_cog(AdminCog())
    await app.add_cog(LoggedCog())
    await app.add_cog(SafeCog())
    await app.add_cog(EventsCog())
    await app.add_cog(TasksCog())
    await app.add_cog(SettingsCog())


app.run_when_ready(setup)
app.run("$VK_TOKEN")
