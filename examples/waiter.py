"""
Пример ожидания событий с wait_for / wait_for_message.

Демонстрирует:
- ctx.wait_for_message() - ожидание сообщения от того же пользователя
- ctx.wait_for() - ожидание произвольного события
- Таймауты и обработка EventTimeoutError
- Фильтрация событий через check
- Многошаговые диалоги
"""

import vkflow

from vkflow import commands
from vkflow.exceptions import EventTimeoutError


app = vkflow.App(prefixes=["!"])


# =============================================
# 1. Простое ожидание сообщения
# =============================================


@app.command()
async def ask_name(ctx: commands.Context):
    """Спросить имя пользователя"""
    await ctx.send("Как тебя зовут?")

    try:
        # Ждём ответ от того же пользователя в том же чате (30 сек)
        reply = await ctx.wait_for_message(timeout=30)
        await ctx.send(f"Привет, {reply.msg.text}!")
    except EventTimeoutError:
        await ctx.send("Время вышло! Вы не ответили.")


# =============================================
# 2. Подтверждение действия (да/нет)
# =============================================


@app.command()
async def confirm(ctx: commands.Context, action: str):
    """Подтвердить действие: !confirm удалить"""
    await ctx.send(f"Вы уверены, что хотите '{action}'? (да/нет)")

    try:
        reply = await ctx.wait_for_message(timeout=15)
        answer = reply.msg.text.lower().strip()

        if answer in ("да", "yes", "y", "д"):
            await ctx.send(f"Действие '{action}' выполнено! ✅")
        else:
            await ctx.send("Действие отменено.")
    except EventTimeoutError:
        await ctx.send("Время вышло, действие отменено.")


# =============================================
# 3. Многошаговый диалог (анкета)
# =============================================


@app.command()
async def register(ctx: commands.Context):
    """Регистрация через диалог"""
    data = {}

    steps = [
        ("Введите ваше имя:", "name"),
        ("Введите ваш возраст:", "age"),
        ("Введите ваш город:", "city"),
    ]

    for prompt, key in steps:
        await ctx.send(prompt)

        try:
            reply = await ctx.wait_for_message(timeout=60)
            data[key] = reply.msg.text
        except EventTimeoutError:
            await ctx.send("Время вышло! Регистрация отменена.")
            return

    # Валидация возраста
    try:
        age = int(data["age"])

        if age < 1 or age > 150:
            raise ValueError
    except ValueError:
        await ctx.send("Некорректный возраст! Регистрация отменена.")
        return

    await ctx.send(
        f"Регистрация завершена!\nИмя: {data['name']}\nВозраст: {data['age']}\nГород: {data['city']}"
    )


# =============================================
# 4. Ожидание с фильтрацией (check)
# =============================================


@app.command()
async def wait_number(ctx: commands.Context):
    """Ожидание числа от пользователя"""
    await ctx.send("Введите число от 1 до 100:")

    def is_valid_number(event, **kw):
        """Проверка: сообщение содержит число от 1 до 100"""
        raw = event.event.object if hasattr(event, "event") else {}
        msg = raw.get("message", raw) if isinstance(raw, dict) else {}

        text = msg.get("text", "")

        try:
            n = int(text)
            return 1 <= n <= 100
        except (ValueError, TypeError):
            return False

    try:
        reply = await ctx.wait_for_message(timeout=30, check=is_valid_number)
        number = int(reply.msg.text)

        await ctx.send(f"Вы ввели число: {number}")
    except EventTimeoutError:
        await ctx.send("Время вышло!")


# =============================================
# 5. Ожидание от любого пользователя в чате
# =============================================


@app.command()
async def quiz(ctx: commands.Context):
    """Викторина - ответить может любой в чате"""
    question = "Столица Франции?"
    answer = "париж"

    await ctx.send(f"Вопрос: {question}\nОтвечайте!")

    def check_answer(event, **kw):
        raw = event.event.object if hasattr(event, "event") else {}
        msg = raw.get("message", raw) if isinstance(raw, dict) else {}

        return msg.get("text", "").lower().strip() == answer

    try:
        # filter_author = False - ждём ответ от ЛЮБОГО пользователя
        reply = await ctx.wait_for_message(
            timeout=30,
            check=check_answer,
            filter_author=False,
        )

        winner_id = reply.msg.from_id
        await ctx.send(f"Правильно! Победитель: [id{winner_id}|ответивший]")
    except EventTimeoutError:
        await ctx.send(f"Время вышло! Ответ: {answer.capitalize()}")


# =============================================
# 6. Ожидание произвольного события (wait_for)
# =============================================


@app.command()
async def wait_callback(ctx: commands.Context):
    """Ожидание нажатия callback-кнопки"""
    keyboard = vkflow.Keyboard(inline=True)
    keyboard.add_callback_button("Нажми меня!", payload={"action": "pressed"})

    await ctx.send("Нажмите кнопку:", keyboard=keyboard.build())

    try:
        event = await ctx.wait_for("message_event", timeout=30)
        await ctx.send("Кнопка нажата!")
    except EventTimeoutError:
        await ctx.send("Вы не нажали кнопку.")


# =============================================
# 7. Выбор из нескольких вариантов
# =============================================


@app.command()
async def choose(ctx: commands.Context):
    """Выбор цвета"""
    options = {"1": "Красный", "2": "Синий", "3": "Зелёный"}
    options_text = "\n".join(f"{k}. {v}" for k, v in options.items())

    await ctx.send(f"Выберите цвет:\n{options_text}")

    for attempt in range(3):
        try:
            reply = await ctx.wait_for_message(timeout=15)
            choice = reply.msg.text.strip()

            if choice in options:
                await ctx.send(f"Вы выбрали: {options[choice]} ✅")
                return

            remaining = 2 - attempt

            if remaining > 0:
                await ctx.send(f"Неверный вариант! Попробуйте ещё ({remaining} попыток)")

        except EventTimeoutError:
            await ctx.send("Время вышло!")
            return

    await ctx.send("Попытки закончились.")


# =============================================
# Запуск
# =============================================

app.run("$VK_TOKEN")
