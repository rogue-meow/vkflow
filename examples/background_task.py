"""
Пример фоновых задач с commands.loop.

Демонстрирует:
- Простой периодический цикл (seconds/minutes/hours)
- Цикл с ограниченным числом итераций (count)
- Хуки before_loop / after_loop / error
- Динамическое изменение интервала
- Использование в Cog
"""

import datetime

import vkflow

from vkflow import commands
from vkflow.commands import loop


app = vkflow.App(prefixes=["/"])

# ID чата, куда будут отправляться сообщения
NOTIFY_PEER_ID = 2000000001


# =============================================
# Вариант 1: Standalone-задача (без Cog)
# =============================================


@loop(minutes=5)
async def periodic_check():
    """Выполняется каждые 5 минут"""
    print(f"[{datetime.datetime.now()}] Периодическая проверка...")


@periodic_check.before_loop
async def before_periodic_check():
    """Выполняется один раз перед началом цикла"""
    print("Периодическая проверка запускается...")
    await app.wait_until_ready()


@periodic_check.after_loop
async def after_periodic_check():
    """Выполняется после завершения цикла"""
    print("Периодическая проверка остановлена.")


@periodic_check.error
async def on_periodic_check_error(error: Exception):
    """Обработка ошибок в цикле"""
    print(f"Ошибка в периодической проверке: {error}")


# =============================================
# Вариант 2: Задача в Cog
# =============================================


class ReminderCog(commands.Cog):
    """Ког с фоновыми задачами"""

    def __init__(self, target_peer_id: int):
        self.target_peer_id = target_peer_id
        self.counter = 0

    async def cog_load(self):
        """Запускаем задачи при загрузке кога"""
        self.reminder_loop.start()
        self.limited_task.start()

    async def cog_unload(self):
        """Останавливаем задачи при выгрузке"""
        self.reminder_loop.cancel()
        self.limited_task.cancel()

    @loop(hours=1)
    async def reminder_loop(self):
        """Отправляет напоминание каждый час"""
        self.counter += 1
        bot = self.app._bots[0]

        await bot.api.messages.send(
            peer_id=self.target_peer_id,
            message=f"Напоминание #{self.counter}!",
            random_id=vkflow.random_id(),
        )

    @reminder_loop.before_loop
    async def before_reminder(self):
        """Ждём, пока бот будет готов"""
        await self.app.wait_until_ready()

    @reminder_loop.after_loop
    async def after_reminder(self):
        print(f"Напоминания завершены. Всего: {self.counter}")

    @loop(seconds=10, count=5)
    async def limited_task(self):
        """Выполняется 5 раз с интервалом 10 секунд"""
        print(f"Итерация {self.limited_task.current_loop + 1}/5")

    # --- Команды для управления задачами ---

    @commands.command()
    async def task_status(self, ctx: commands.Context):
        """Статус фоновой задачи"""
        if self.reminder_loop.is_running():
            next_iter = self.reminder_loop.next_iteration

            await ctx.send(
                f"Задача запущена.\n"
                f"Текущая итерация: {self.reminder_loop.current_loop}\n"
                f"Следующая: {next_iter}"
            )

        else:
            await ctx.send("Задача не запущена.")

    @commands.command()
    async def task_stop(self, ctx: commands.Context):
        """Остановить задачу"""
        self.reminder_loop.stop()
        await ctx.send("Задача остановлена.")

    @commands.command()
    async def task_restart(self, ctx: commands.Context):
        """Перезапустить задачу"""
        self.reminder_loop.restart()
        await ctx.send("Задача перезапущена.")

    @commands.command()
    async def set_interval(self, ctx: commands.Context, minutes: float):
        """Изменить интервал задачи"""
        self.reminder_loop.change_interval(minutes=minutes)
        await ctx.send(f"Интервал изменён на {minutes} минут.")


# =============================================
# Вариант 3: Задача по расписанию (time)
# =============================================


class ScheduledCog(commands.Cog):
    """Ког с задачей по расписанию"""

    async def cog_load(self):
        self.morning_report.start()

    async def cog_unload(self):
        self.morning_report.cancel()

    @loop(
        time=[
            datetime.time(hour=9, minute=0, tzinfo=datetime.UTC),
            datetime.time(hour=18, minute=0, tzinfo=datetime.UTC),
        ]
    )
    async def morning_report(self):
        """Выполняется в 9:00 и 18:00 UTC каждый день"""
        print(f"Отчёт в {datetime.datetime.now(datetime.UTC)}")

    @morning_report.before_loop
    async def before_morning_report(self):
        await self.app.wait_until_ready()


# =============================================
# Запуск
# =============================================


async def setup():
    await app.add_cog(ReminderCog(target_peer_id=NOTIFY_PEER_ID))
    await app.add_cog(ScheduledCog())

    periodic_check.start()


app.run_when_ready(setup)
app.run("$VK_TOKEN")
