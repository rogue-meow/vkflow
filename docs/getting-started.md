---
hide:
  - navigation
---

# Быстрый старт

## Установка

```shell
pip install vkflow
```

Для максимальной производительности:

```shell
pip install vkflow[speed]
```

Включает `msgspec`/`orjson` (быстрый JSON), `aiodns` (асинхронный DNS), `Brotli` (сжатие).

## Получение токена

### Токен сообщества (рекомендуется)

1. Создайте сообщество или откройте существующее
2. Настройки → Работа с API → Создать ключ
3. Выберите нужные права доступа (как минимум: сообщения сообщества)
4. В настройках Long Poll API включите Long Poll и выберите версию 5.199+
5. Включите нужные типы событий (как минимум: входящие сообщения)

### Токен пользователя

Используйте [VK Admin](https://vkhost.github.io/) или другой способ авторизации.

!!! tip "Переменные окружения"
    Токен можно передавать через переменные окружения. Если токен начинается с `$`, VKFlow автоматически подставит значение:

    ```python
    # Считает токен из переменной окружения VK_TOKEN
    app.run("$VK_TOKEN")
    ```

## Первый бот

```python
import vkflow as vf

app = vf.App()

@app.command("ping")
async def ping():
    """Простая команда -отвечает Pong!"""
    return "Pong!"

@app.command("привет")
async def greet(user: vf.User):
    """Приветствие с упоминанием пользователя"""
    return f"Привет, {user:@[first_name]}!"

app.run("YOUR_TOKEN")
```

Замените `"YOUR_TOKEN"` на свой токен и запустите скрипт. Бот начнёт слушать сообщения через Long Poll.

### Как это работает

1. `App()` - создаёт приложение (наследник `Package`)
2. `@app.command("ping")` - регистрирует команду с именем "ping"
3. `return "Pong!"` - если команда возвращает строку, она автоматически отправляется как ответ
4. `user: vf.User` - аргумент автоматически парсится из упоминания/ссылки в сообщении
5. `app.run("YOUR_TOKEN")` - определяет тип токена, создаёт `Bot` и запускает Long Poll

## Режим отладки

```python
app = vf.App(debug=True)
```

В режиме отладки:

- Включается подробное логирование (уровень DEBUG)
- При ошибках парсинга аргументов бот отвечает пользователю описанием проблемы

## Строгий режим

```python
app = vf.App(strict_mode=True)
```

В строгом режиме:

- Ошибки парсинга аргументов выбрасывают `ArgumentParsingError` (вместо молчаливого пропуска)
- Лишний текст после аргументов считается ошибкой
- Команда без аргументов отклоняет сообщения с аргументами

## Мульти-бот

Можно запустить несколько ботов в одном приложении:

```python
app = vf.App()

@app.command("ping")
async def ping():
    return "Pong!"

# Все боты разделяют одни и те же команды
app.run("TOKEN_1", "TOKEN_2", "TOKEN_3")
```

Также можно передать готовый экземпляр `API`:

```python
api = vf.API("YOUR_TOKEN", version="5.199")
app.run(api)
```

## Lifecycle: startup и shutdown

```python
import vkflow as vf

class MyApp(vf.App):
    async def startup(self, bot: vf.Bot):
        """Вызывается при запуске каждого бота"""
        print(f"Bot started: {bot}")

    async def shutdown(self, bot: vf.Bot):
        """Вызывается при остановке каждого бота"""
        print(f"Bot stopped: {bot}")

app = MyApp()
```

Или через декораторы:

```python
app = vf.App()

@app.on_startup()
async def on_startup(bot):
    print(f"Bot started: {bot}")

@app.on_shutdown()
async def on_shutdown(bot):
    print(f"Bot stopped: {bot}")
```

## Ожидание готовности

```python
# Выполнить код, когда все боты готовы
async def do_something():
    await app.wait_until_ready()
    print("Все боты готовы!")

app.run_when_ready(do_something)
```

## Что дальше?

- [Команды](guides/commands.md) - подробнее о создании команд, группах, ошибках
- [Аргументы](guides/arguments.md) - type hints и парсинг аргументов
- [Клавиатуры](guides/keyboards.md) - интерактивный UI
- [FSM](guides/fsm.md) - многошаговые диалоги
- [Cog-модули](guides/cogs.md) - организация кода
- [Проверки](guides/checks.md) - контроль доступа, cooldown
