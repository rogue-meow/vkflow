# Префиксы

Префиксы определяют, с какого символа (или символов) должно начинаться сообщение, чтобы оно было распознано как команда.

## Базовые префиксы

```python
import vkflow as vf

# Один префикс
app = vf.App(prefixes=["!"])
# Пользователь пишет: !ping

# Несколько
app = vf.App(prefixes=["!", "/", "."])
# Пользователь может писать: !ping, /ping, .ping
```

## Без префикса

Если не указать префиксы, команды работают без них:

```python
app = vf.App()  # prefixes=[]

@app.command("ping")
async def ping():
    return "Pong!"

# Пользователь пишет просто: ping
```

## Динамические префиксы

Функция получает контекст сообщения и возвращает префикс(ы):

```python
# Разные префиксы для ЛС и чатов
def get_prefix(ctx):
    if ctx.msg.peer_id > 2000000000:
        return "!"  # В чатах
    return "/"      # В ЛС

app = vf.App(prefixes=get_prefix)
```

## Асинхронные префиксы

```python
async def get_prefix(ctx):
    # Из базы данных
    prefix = await db.get_prefix(ctx.msg.peer_id)
    return prefix or "!"

app = vf.App(prefixes=get_prefix)
```

Функция может возвращать:

- `str` -один префикс
- `list[str]` -несколько префиксов
- вызвать себя рекурсивно через цепочку

## Упоминание бота

Бот реагирует на упоминание (@имя_бота или [club123|@бот]):

```python
# Только упоминание
app = vf.App(prefixes=vf.when_mentioned())

# Упоминание ИЛИ обычные префиксы
app = vf.App(prefixes=vf.when_mentioned_or("!", "/"))
```

`when_mentioned()` автоматически определяет ID бота (группы или пользователя) из токена и формирует паттерны `[club123|...]` / `[id123|...]`.

### Пример с упоминанием

```python
app = vf.App(prefixes=vf.when_mentioned_or("!"))

@app.command("помощь")
async def help_cmd(ctx: vf.Context):
    return "Доступные команды: ..."

# Работает и так:
# !помощь
# @бот помощь
# [club123456|@бот] помощь
```

## Префиксы для конкретной команды

Переопределяют глобальные префиксы:

```python
app = vf.App(prefixes=["!"])

# Эта команда использует / вместо !
@app.command("бан", prefixes=["/"])
async def ban(user: vf.User):
    ...

# Эта использует глобальный !
@app.command("помощь")
async def help_cmd():
    ...
```

## Регистронезависимость

По умолчанию команды регистронезависимы (через `re.IGNORECASE`):

```python
@app.command("Ping")
async def ping():
    return "Pong!"

# Работает: ping, Ping, PING, pInG
```

Можно отключить:

```python
import re

@app.command("Ping", routing_re_flags=0)
async def ping():
    return "Pong!"

# Работает только: Ping
```

## Clean prefix в контексте

```python
@app.command("помощь")
async def help_cmd(ctx: vf.Context):
    prefix = ctx.clean_prefix  # "!" для обычных, "" для упоминаний
    cmd_name = ctx.invoked_with  # "помощь"
    await ctx.send(f"Использование: {prefix}{cmd_name} <аргумент>")
```
