# Проверки, cooldown и max_concurrency

## Встроенные проверки

```python
import vkflow as vf
from vkflow import commands

@app.command("бан")
@vf.is_admin()
async def ban(ctx: vf.Context, user: vf.User):
    """Только для администраторов чата (is_admin в ЛС всегда False)"""
    ...

@app.command("настройки")
@vf.is_owner()
async def settings(ctx: vf.Context):
    """Только для владельца/администратора группы-бота"""
    ...

@app.command("лс")
@vf.is_private_message()
async def dm_only(ctx: vf.Context):
    """Только в личных сообщениях"""
    ...

@app.command("чат")
@vf.is_group_chat()
async def chat_only(ctx: vf.Context):
    """Только в групповых чатах"""
    ...
```

### Кэширование проверок

`is_admin()` кэширует результат на 5 минут, `is_owner()` -на 10 минут. Это означает, что изменения прав вступят в силу не сразу.

### Параметр delete_after

Все встроенные проверки поддерживают `delete_after` -автоудаление сообщения об ошибке:

```python
@app.command("секрет")
@vf.is_admin(delete_after=10)
async def secret(ctx: vf.Context):
    """Сообщение 'Вы должны быть администратором...' удалится через 10 секунд"""
    ...
```

### Алиасы

| Проверка | Алиас |
|----------|-------|
| `is_private_message()` | `dm_only()` |
| `is_group_chat()` | `guild_only()` |

## Cooldown

Ограничение частоты вызова команды:

```python
from vkflow.commands import cooldown, BucketType

# 1 раз в 60 секунд на пользователя
@commands.command()
@commands.cooldown(rate=1, per=60, type=BucketType.USER)
async def bonus(ctx: commands.Context):
    await ctx.send("Бонус получен!")

# 3 раза в 60 секунд на пользователя
@commands.command()
@commands.cooldown(rate=3, per=60, type=BucketType.USER)
async def spam(ctx: commands.Context):
    await ctx.send("Спам!")

# 1 раз в 30 секунд на чат
@commands.command()
@commands.cooldown(rate=1, per=30, type=BucketType.CHAT)
async def global_cmd(ctx: commands.Context):
    await ctx.send("Глобальная команда!")

# 1 раз в 10 секунд на пользователя в конкретном чате
@commands.command()
@commands.cooldown(rate=1, per=10, type=BucketType.MEMBER)
async def limited(ctx: commands.Context):
    await ctx.send("Ограниченная!")
```

### BucketType

| Тип | Описание |
|-----|----------|
| `BucketType.DEFAULT` | Глобальный cooldown (один на всех) |
| `BucketType.USER` | На пользователя (одинаковый во всех чатах) |
| `BucketType.CHAT` | На чат |
| `BucketType.MEMBER` | На пользователя в конкретном чате |

### Обработка cooldown

```python
@commands.command()
@commands.cooldown(rate=1, per=60, type=BucketType.USER)
async def daily(ctx: commands.Context):
    await ctx.send("Готово!")

# Обработчик cooldown
@daily.on_cooldown()
async def on_daily_cooldown(ctx: commands.Context, remaining: float):
    await ctx.send(f"Подождите {remaining:.0f} сек.")

# Или с полным объектом ошибки
@daily.on_cooldown()
async def on_daily_cooldown(ctx: commands.Context, error: commands.OnCooldownError):
    await ctx.send(f"Подождите {error.retry_after:.1f}с (тип: {error.type})")
```

### Сброс cooldown

```python
# Сбросить все cooldown для всех
daily.reset_cooldown()

# Сбросить для конкретного пользователя (из контекста)
daily.reset_cooldown(ctx)

# Сбросить для конкретного ID
daily.reset_cooldown(user=123456)

# Сбросить для конкретного чата
daily.reset_cooldown(chat=2000000001)

# Сбросить только определённый тип
daily.reset_cooldown(type=BucketType.USER)
```

## Max Concurrency

Ограничение количества одновременных выполнений команды:

```python
from vkflow.commands import max_concurrency, BucketType

@commands.command()
@commands.max_concurrency(2, BucketType.CHAT)
async def heavy(ctx: commands.Context):
    import asyncio
    await asyncio.sleep(10)
    await ctx.send("Готово!")

# Обработчик превышения лимита
@heavy.on_max_concurrency()
async def on_heavy_concurrency(ctx: commands.Context, limit: int, current: int):
    await ctx.send(f"Слишком много одновременных выполнений: {current}/{limit}")

# Или с объектом ошибки
@heavy.on_max_concurrency()
async def on_heavy_concurrency(ctx: commands.Context, error: commands.MaxConcurrencyReachedError):
    await ctx.send(f"Лимит: {error.current}/{error.number}")
```

## Свои проверки

```python
from vkflow import check

# Создание через функцию check()
VIP_LIST = [123456, 789012]

def is_vip():
    async def predicate(ctx) -> bool:
        return ctx.author in VIP_LIST
    return check(predicate, error_message="Только для VIP!")

# С удалением сообщения об ошибке
def is_premium():
    def predicate(ctx) -> bool:
        return ctx.author in PREMIUM_IDS
    return check(predicate, error_message="Только для премиум!", delete_after=10)

# Использование
@commands.command()
@is_vip()
async def vip_command(ctx: commands.Context):
    await ctx.send("VIP-команда!")

# Синхронные проверки тоже работают
def is_not_bot():
    return check(lambda ctx: ctx.author > 0, error_message="Боты не допускаются!")
```

## Комбинирование проверок

### Логическое ИЛИ (check_any)

```python
from vkflow.commands import check_any

@commands.command()
@check_any(is_owner(), is_admin(), error_message="Нужны права владельца или админа!")
async def manage(ctx: commands.Context):
    await ctx.send("Вы владелец или админ!")
```

### Логическое И (несколько декораторов)

```python
@commands.command()
@is_vip()
@vf.is_group_chat()
async def vip_chat_cmd(ctx: commands.Context):
    """Доступно только VIP-пользователям И только в групповых чатах"""
    ...
```

## Обработка ошибок проверок

### Через on_error на команде

```python
@commands.command()
@vf.is_admin()
async def admin_cmd(ctx: commands.Context):
    return "Доступ есть"

@admin_cmd.on_error(vf.CheckFailureError)
async def admin_error(ctx: commands.Context, error: vf.CheckFailureError):
    await ctx.send("У вас нет прав администратора!")
```

### Через события

```python
from vkflow import commands

@commands.listener()
async def on_check_error(ctx, error, command):
    """Глобальный слушатель ошибок проверок"""
    print(f"Check failed for {command.name}: {error}")
```

## Пример: Полный бот с проверками

```python
import vkflow as vf
from vkflow import commands

app = vf.App(prefixes=["!"])

OWNER_ID = 123456789

def is_bot_owner():
    return vf.check(
        lambda ctx: ctx.author == OWNER_ID,
        error_message="Только владелец бота!"
    )

@commands.command(name="перезагрузка")
@is_bot_owner()
async def reload_cmd(ctx: commands.Context, ext: str):
    """Перезагрузить расширение (только для владельца)"""
    await ctx.app.reload_extension(ext)
    await ctx.send(f"Расширение {ext} перезагружено!")

@commands.command(name="бонус")
@commands.cooldown(rate=1, per=3600, type=commands.BucketType.USER)
@vf.is_group_chat()
async def bonus(ctx: commands.Context):
    """Ежечасный бонус (только в чатах)"""
    await ctx.send("Вы получили бонус!")

@bonus.on_cooldown()
async def bonus_cd(ctx: commands.Context, remaining: float):
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    await ctx.send(f"Бонус доступен через {mins}м {secs}с")

@bonus.on_error(vf.CheckFailureError)
async def bonus_check_error(ctx, error):
    await ctx.send("Бонус доступен только в групповых чатах!")

app.commands.extend([reload_cmd, bonus])
app.run("TOKEN")
```
