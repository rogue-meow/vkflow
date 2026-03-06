"""
Пример редактирования и удаления сообщений.

Демонстрирует:
- Отправка сообщения и получение SentMessage
- Редактирование отправленного сообщения
- Удаление сообщения через delete_after
- Пересылка сообщений (forward)
"""

import asyncio

import vkflow

from vkflow import commands


app = vkflow.App(prefixes=["!"])


# =============================================
# 1. Редактирование сообщения
# =============================================


@app.command()
async def countdown(ctx: commands.Context):
    """Обратный отсчёт с редактированием сообщения"""
    msg = await ctx.send("Обратный отсчёт: 5...")

    for i in range(4, 0, -1):
        await asyncio.sleep(1)
        await msg.edit(f"Обратный отсчёт: {i}...")

    await asyncio.sleep(1)
    await msg.edit("Готово! 🎉")


# =============================================
# 2. Удаление через delete_after
# =============================================


@app.command()
async def secret(ctx: commands.Context):
    """Сообщение, которое удалится через 5 секунд"""
    await ctx.send("Это секретное сообщение! 🤫", delete_after=5)


@app.command()
async def temp_reply(ctx: commands.Context):
    """Временный ответ"""
    await ctx.reply("Это сообщение исчезнет через 10 секунд", delete_after=10)


# =============================================
# 3. Редактирование + удаление
# =============================================


@app.command()
async def loading(ctx: commands.Context):
    """Индикатор загрузки"""
    msg = await ctx.send("Загрузка ⏳")

    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    for i in range(20):
        await asyncio.sleep(0.5)
        await msg.edit(f"Загрузка {frames[i % len(frames)]}")

    await msg.edit("Загрузка завершена! ✅")


# =============================================
# 4. Пересылка сообщений
# =============================================


@app.command()
async def forward_to(ctx: commands.Context, peer_id: int):
    """Переслать сообщение: !forward_to 123456789"""
    await ctx.forward(peer_id, message="Пересланное сообщение!")
    await ctx.send(f"Сообщение переслано в {peer_id}")


# =============================================
# 5. Отправка с последующим редактированием по результату
# =============================================


@app.command()
async def process(ctx: commands.Context, data: str):
    """Обработка данных с обновлением статуса"""
    msg = await ctx.send(f"Обрабатываю '{data}'...")

    # Имитация обработки
    await asyncio.sleep(2)

    if len(data) > 5:
        await msg.edit(f"Обработка '{data}' завершена успешно! ✅")
    else:
        await msg.edit(f"Данные '{data}' слишком короткие. ❌")


# =============================================
# Запуск
# =============================================

app.run("$VK_TOKEN")
