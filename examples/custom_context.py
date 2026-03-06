"""
Пример кастомного Context.

Демонстрирует:
- Создание кастомного Context с дополнительными свойствами
- Переопределение App.get_context() для глобального использования
- Использование кастомного контекста в командах
"""

import vkflow

from vkflow import commands


# =============================================
# 1. Кастомный Context
# =============================================


class MyContext(commands.Context):
    """Кастомный контекст с дополнительными свойствами"""

    @property
    def db(self):
        """Доступ к базе данных через контекст"""
        return self.app.database

    @property
    def config(self):
        """Доступ к конфигурации"""
        return self.app.bot_config

    async def send_embed(self, title: str, description: str, **kwargs):
        """Отправка стилизованного сообщения"""
        text = f"📋 {title}\n\n{description}"
        return await self.send(text, **kwargs)

    async def send_error(self, message: str):
        """Отправка сообщения об ошибке"""
        return await self.send(f"❌ Ошибка: {message}")

    async def send_success(self, message: str):
        """Отправка сообщения об успехе"""
        return await self.send(f"✅ {message}")

    @property
    def is_admin(self) -> bool:
        """Быстрая проверка на администратора"""
        return self.author in self.config.get("admin_ids", [])


# =============================================
# 2. Кастомный App с переопределением get_context
# =============================================


class MyApp(vkflow.App):
    """Кастомное приложение"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Пользовательские данные
        self.database = {}  # Заглушка для базы данных
        self.bot_config = {
            "admin_ids": [123456, 789012],
            "prefix": "!",
        }

    async def get_context(self, message, *, cls=MyContext, **kwargs):
        """Глобально используем MyContext вместо стандартного"""
        return await super().get_context(message, cls=cls, **kwargs)


app = MyApp(prefixes=["!"])


# =============================================
# 3. Использование в командах
# =============================================


@app.command()
async def save(ctx: MyContext, key: str, value: str):
    """Сохранить значение: !save name Алиса"""
    ctx.db[key] = value
    await ctx.send_success(f"Сохранено: {key} = {value}")


@app.command()
async def load(ctx: MyContext, key: str):
    """Загрузить значение: !load name"""
    value = ctx.db.get(key)

    if value is None:
        await ctx.send_error(f"Ключ '{key}' не найден")
    else:
        await ctx.send_embed("Данные", f"{key} = {value}")


@app.command()
async def admin(ctx: MyContext):
    """Проверка админских прав"""
    if ctx.is_admin:
        await ctx.send_success("Вы администратор!")
    else:
        await ctx.send_error("У вас нет прав администратора")


# =============================================
# 4. Кастомный Context в Cog
# =============================================


class InfoCog(commands.Cog):
    """Информационный ког"""

    @commands.command()
    async def status(self, ctx: MyContext):
        """Статус бота"""
        await ctx.send_embed(
            "Статус бота",
            f"База данных: {len(ctx.db)} записей\nАдминистраторов: {len(ctx.config.get('admin_ids', []))}",
        )


async def setup():
    await app.add_cog(InfoCog())


app.run_when_ready(setup)
app.run("$VK_TOKEN")
