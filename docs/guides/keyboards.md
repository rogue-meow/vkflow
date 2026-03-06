# Клавиатуры и View

## Клавиатуры

### Через add_button

```python
import vkflow as vf

@app.command("меню")
async def menu(ctx: vf.Context):
    kb = vf.Keyboard(inline=True)
    kb.add_button("Кнопка 1", color="positive")
    kb.add_button("Кнопка 2", color="negative")
    kb.row()  # Новый ряд (алиас для new_line())
    kb.add_button("Во всю ширину", color="primary")

    await ctx.send("Выберите:", keyboard=kb)
```

### Через конструктор

```python
from vkflow import Keyboard, Button

kb = Keyboard(
    Button.text("Кнопка 1").positive(),
    Button.text("Кнопка 2").negative(),
    ...,  # Ellipsis = новый ряд
    Button.text("Во всю ширину").primary(),
    inline=True,
)
```

### Через add + new_line (цепочка)

```python
kb = vf.Keyboard(inline=True)
kb.add(Button.text("A").positive()).add(Button.text("B").negative())
kb.new_line()
kb.add(Button.text("C").primary())
```

### Цвета кнопок

| Цвет | Метод | Вид |
|------|-------|-----|
| `"primary"` | `.primary()` | Синяя |
| `"secondary"` | `.secondary()` | Белая (по умолчанию) |
| `"positive"` | `.positive()` | Зелёная |
| `"negative"` | `.negative()` | Красная |

### Типы кнопок

```python
from vkflow import Button

# Текстовая (обычная)
Button.text("Текст")

# Callback (не отправляет сообщение, только событие)
Button.callback("Нажми", payload={"action": "click"})

# Открыть ссылку
Button.open_link("Перейти", link="https://vk.com")

# Открыть приложение VK Mini App
Button.open_app("Открыть", app_id=123456, owner_id=-100, hash="...")

# Геолокация
Button.location()
```

### Обычная (не inline) клавиатура

```python
kb = vf.Keyboard(one_time=True)  # one_time=True -скрыть после нажатия
kb.add_button("Привет")
kb.add_button("Пока")

await ctx.send("Выбери:", keyboard=kb)
```

### Убрать клавиатуру

```python
await ctx.send("Готово", keyboard=vf.Keyboard.empty())
```

### Payload у кнопок

```python
# Через add_button
kb.add_button("Товар 1", color="positive", payload={"item_id": 1})

# Через Button
Button.text("Товар 1", payload={"item_id": 1}).positive()
```

### Обработка payload

```python
@app.on_clicked_button()
async def handle_click(ctx: vf.NewMessage, item_id: int):
    """Вызывается при нажатии кнопки с payload {"command": "handle_click", "args": {"item_id": 1}}"""
    return f"Выбран товар: {item_id}"
```

## Интерактивные View

View -класс с callback-кнопками и автоматическим управлением состоянием. Кнопки View используют `Button.callback` и обрабатываются через VK Callback API (`message_event`).

### Создание View

```python
from vkflow.ui.view import View, button

class ConfirmView(View):
    def __init__(self):
        super().__init__(timeout=60, inline=True)
        self.result = None

    @button(label="Да", color="positive")
    async def yes(self, interaction: vf.CallbackButtonPressed):
        self.result = True
        await interaction.show_snackbar("Принято!")
        self.stop()

    @button(label="Нет", color="negative")
    async def no(self, interaction: vf.CallbackButtonPressed):
        self.result = False
        await interaction.show_snackbar("Отменено")
        self.stop()

    async def on_timeout(self):
        """Вызывается при истечении таймаута"""
        pass
```

### Использование View

```python
@app.command("подтвердить")
async def confirm(ctx: vf.Context):
    view = ConfirmView()
    await ctx.send("Вы уверены?", view=view)

    timed_out = await view.wait()
    if not timed_out:
        await ctx.send(f"Ответ: {'Да' if view.result else 'Нет'}")
    else:
        await ctx.send("Время вышло!")
```

### Параметры View

```python
class MyView(View):
    def __init__(self):
        super().__init__(
            timeout=180,      # Таймаут в секундах (None = бесконечный)
            inline=True,      # Inline-клавиатура
        )
```

### Параметры кнопок

```python
@button(
    label="Текст",          # Текст на кнопке
    emoji="🎉",              # Эмодзи перед текстом
    custom_id="my_btn",     # Уникальный ID (по умолчанию = имя метода)
    color="positive",       # Цвет: positive/negative/primary/secondary
    row=0,                  # Номер ряда (None = авто)
    disabled=False,         # Неактивная кнопка
)
async def my_button(self, interaction):
    ...
```

### Проверка пользователя

```python
class PrivateView(View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120, inline=True)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: vf.CallbackButtonPressed) -> bool:
        """Только владелец может нажимать кнопки"""
        return interaction.msg.user_id == self.owner_id
```

### Управление View

```python
view = MyView()

view.stop()           # Остановить View
view.refresh()        # Сбросить таймер таймаута
view.is_finished()    # Завершён ли View
view.is_dispatching() # Обрабатывается ли сейчас нажатие
view.is_persistent()  # True если timeout=None
```

### View с FSM

View может интегрироваться с FSM для управления состояниями через кнопки:

```python
from vkflow.app.fsm import MemoryStorage

class OrderView(View):
    fsm_storage = MemoryStorage()  # Атрибут класса

    @button(label="Подтвердить", color="positive")
    async def confirm(self, ctx, fsm):
        # fsm автоматически инжектируется из fsm_storage
        data = await fsm.finish()
        await ctx.show_snackbar(f"Заказ: {data}")
        self.stop()

    @button(label="Отмена", color="negative")
    async def cancel(self, ctx, fsm):
        await fsm.clear()
        await ctx.show_snackbar("Отменено")
        self.stop()
```

### Пример: Калькулятор

```python
class CalculatorView(View):
    def __init__(self):
        super().__init__(timeout=120, inline=True)
        self.value = 0

    @button(label="+1", color="positive", row=0)
    async def add_one(self, interaction):
        self.value += 1
        await interaction.show_snackbar(f"Значение: {self.value}")

    @button(label="-1", color="negative", row=0)
    async def sub_one(self, interaction):
        self.value -= 1
        await interaction.show_snackbar(f"Значение: {self.value}")

    @button(label="Сброс", color="primary", row=1)
    async def reset(self, interaction):
        self.value = 0
        await interaction.show_snackbar("Сброшено!")

    @button(label="Готово", color="secondary", row=1)
    async def done(self, interaction):
        await interaction.show_snackbar(f"Итого: {self.value}")
        self.stop()
```

## Карусели

```python
from vkflow import Carousel, Element

@app.command("магазин")
async def shop(ctx: vf.Context):
    carousel = Carousel()
    carousel.add_element(
        Element(
            title="Товар 1",
            description="Описание товара",
            photo_id="-123_456",
            buttons=[Button.text("Купить", payload={"item": 1}).positive()],
        )
    )
    carousel.add_element(
        Element(
            title="Товар 2",
            description="Другой товар",
            photo_id="-123_789",
            buttons=[Button.text("Купить", payload={"item": 2}).positive()],
        )
    )
    await ctx.send("Наш магазин:", carousel=carousel)
```
