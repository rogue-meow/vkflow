# Аргументы команд

VKFlow автоматически парсит аргументы команд из аннотаций типов. Каждый параметр функции (кроме `ctx`/`self`) становится аргументом команды.

## Базовые типы

```python
@app.command("сумма")
async def add(a: int, b: int):
    return f"Результат: {a + b}"

@app.command("повтор")
async def repeat(text: str, count: int = 1):
    return text * count

@app.command("среднее")
async def avg(a: float, b: float):
    return f"Среднее: {(a + b) / 2:.2f}"
```

| Тип | Описание | Пример ввода |
|-----|----------|-------------|
| `int` | Целое число | `42` |
| `float` | Дробное число | `3.14` |
| `str` | Строка (вся оставшаяся строка) | `hello world` |

## VK-сущности

```python
@app.command("инфо")
async def user_info(user: vf.User):
    """Автоматически резолвит упоминание/ссылку/ID в объект User"""
    return f"{user.first_name} {user.last_name}, ID: {user.id}"

@app.command("группа")
async def group_info(group: vf.Group):
    """Резолвит упоминание/ссылку группы"""
    return f"Группа: {group.name}"

@app.command("страница")
async def page_info(page: vf.Page):
    """User или Group -определяется автоматически"""
    return f"Страница: {page.mention()}"
```

### Специальные типы ID

```python
from vkflow import Mention, UserID, GroupID, PageID

@app.command("ид")
async def get_id(user_id: UserID):
    """Парсит только числовой ID пользователя"""
    return f"ID: {user_id}"

@app.command("упоминание")
async def mention(m: Mention):
    """Парсит VK-упоминание [id123|Имя]"""
    return f"Упоминание: {m}"
```

## Вложения

```python
from vkflow import Photo, Document, Video, Audio

@app.command("фото")
async def get_photo(photo: Photo):
    """Получить первое фото из сообщения"""
    return f"Фото: {photo.sizes[-1].url}"

@app.command("док")
async def get_doc(doc: Document):
    """Получить документ"""
    return f"Документ: {doc.title}"

# Списки вложений
@app.command("все_фото")
async def all_photos(photos: list[Photo]):
    return f"Всего фото: {len(photos)}"

@app.command("все_доки")
async def all_docs(docs: list[Document]):
    return f"Документов: {len(docs)}"
```

Поддерживаемые типы вложений: `Photo`, `Document`, `Video`, `Audio`, `Sticker`, `AudioMessage`, `Graffiti`, `Wall`, `Poll`, `Story`, `Link`, `Gift`, `Market`.

## Optional аргументы

```python
from typing import Optional

@app.command("привет")
async def greet(ctx: vf.Context, user: Optional[vf.User] = None):
    if user:
        return f"Привет, {user:@[first_name]}!"
    return "Привет!"
```

## Значения по умолчанию

```python
@app.command("повтор")
async def repeat(text: str, count: int = 1):
    return text * count

# "!повтор hello" -> "hello"
# "!повтор hello 3" -> "hellohellohello"
```

## Валидаторы

Валидаторы применяются через `typing.Annotated` после парсинга значения:

```python
from typing import Annotated
from vkflow import Range, MinLength, MaxLength, Regex, OneOf, Transform, Between

# Диапазон чисел
@app.command("бросок")
async def roll(sides: Annotated[int, Range(1, 100)] = 6):
    import random
    return f"Выпало: {random.randint(1, sides)}"

# Ограничение длины строки
@app.command("ник")
async def nick(name: Annotated[str, MinLength(3), MaxLength(20)]):
    return f"Ник: {name}"

# Регулярное выражение
@app.command("код")
async def code(value: Annotated[str, Regex(r"^[A-Z]{3}-\d{4}$", message="Формат: ABC-1234")]):
    return f"Код: {value}"

# Список допустимых значений
@app.command("выбор")
async def choice(item: Annotated[str, OneOf("камень", "ножницы", "бумага")]):
    return f"Вы выбрали: {item}"

# Трансформация (цепочка функций)
@app.command("нижний")
async def lower(text: Annotated[str, Transform(str.strip, str.lower)]):
    return f"Результат: {text}"

# Комбинирование валидаторов
@app.command("пароль")
async def password(pwd: Annotated[str, MinLength(8), MaxLength(32), Regex(r".*\d.*", message="Нужна цифра")]):
    return "Пароль принят!"
```

### Все валидаторы

| Валидатор | Типы | Описание |
|-----------|------|----------|
| `Range(min, max)` | `int`, `float` | Значение в диапазоне |
| `MinLength(n)` | `str` | Минимальная длина строки |
| `MaxLength(n)` | `str` | Максимальная длина строки |
| `Regex(pattern)` | `str` | Соответствие регулярному выражению |
| `OneOf(*values)` | любой | Значение из списка |
| `Between(min, max)` | `list` | Количество элементов в списке |
| `Transform(*funcs)` | любой | Цепочка преобразований |

## Enum как аргумент

```python
from enum import Enum
from typing import Annotated
from vkflow import EnumCutter

class Color(Enum):
    RED = "красный"
    GREEN = "зелёный"
    BLUE = "синий"

@app.command("цвет")
async def set_color(color: Annotated[Color, EnumCutter()]):
    return f"Выбран цвет: {color.value}"

# Использование: !цвет красный
```

## Dict-аргумент

```python
from typing import Annotated
from vkflow import DictCutter

ITEMS = {
    "меч": {"damage": 10, "price": 100},
    "щит": {"defense": 5, "price": 50},
}

@app.command("купить")
async def buy(item: Annotated[dict, DictCutter(ITEMS)]):
    return f"Куплено: цена {item['price']}"

# Использование: !купить меч
```

## Флаги (Flag) и именованные аргументы (Named)

Непозиционные аргументы, которые могут стоять в любом месте:

```python
from typing import Annotated
from vkflow import Flag, Named

@app.command("поиск")
async def search(
    query: str,
    limit: Annotated[int, Named("limit")] = 10,
    reverse: Annotated[bool, Flag("reverse")] = False,
):
    return f"Поиск: {query}, лимит: {limit}, реверс: {reverse}"

# Использование:
# !поиск котики --limit 5
# !поиск собаки --reverse
# !поиск птички --limit 3 --reverse
```

## Ответ на сообщение

```python
from vkflow.commands import ReplyUser, ReplyMessage

@app.command("кто_ответил")
async def who_replied(reply_user: ReplyUser):
    """Получить пользователя из reply-сообщения"""
    return f"Ответ на сообщение от: {reply_user.first_name}"

@app.command("цитата")
async def quote(reply: ReplyMessage):
    """Получить объект пересланного сообщения"""
    return f"Цитата: {reply.text}"
```

## Union типы

```python
@app.command("страница")
async def page(entity: vf.User | vf.Group):
    """Принимает и пользователя, и группу"""
    return f"Страница: {entity.mention()}"
```

## Greedy (жадный парсинг)

```python
from vkflow.commands import Greedy

@app.command("сумма")
async def sum_all(numbers: Greedy[int]):
    """Собирает все числа из сообщения"""
    return f"Сумма: {sum(numbers)}"

# Использование: !сумма 1 2 3 4 5 -> Сумма: 15
```

## Literal типы

```python
from typing import Literal

@app.command("режим")
async def mode(m: Literal["on", "off"]):
    return f"Режим: {m}"

# Использование: !режим on / !режим off
```

## Кортежи, множества, списки

```python
@app.command("пара")
async def pair(items: tuple[int, int]):
    return f"Сумма: {items[0] + items[1]}"

@app.command("уникальные")
async def unique(items: set[str]):
    return f"Уникальных: {len(items)}"

@app.command("список")
async def items(vals: list[int]):
    return f"Элементов: {len(vals)}"
```

## Конвертеры

Создание собственных конвертеров:

```python
from vkflow.commands import Converter, ConversionError

class UpperConverter(Converter):
    async def convert(self, ctx, argument: str):
        if not argument.isalpha():
            raise ConversionError("Только буквы!")
        return argument.upper()

@app.command("верхний")
async def upper(text: UpperConverter):
    return text
```

### Регистрация кастомного cutter для типа

```python
from vkflow import register_cutter

# Теперь MyType будет автоматически распознаваться
register_cutter(MyType, MyCutter())
```
