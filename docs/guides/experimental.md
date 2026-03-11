# Экспериментальные возможности

Система экспериментальных флагов позволяет включать новые оптимизации и поведения, которые ещё не стали частью стандартного поведения фреймворка.

## Подключение

Флаги передаются через параметр `experimental` при создании `App`:

```python
import vkflow as vf

app = vf.App(
    prefixes=["/"],
    experimental={"eager_task_factory": True},
)
```

Каждый флаг — это пара `"имя": True/False`.

## Проверка состояния

```python
if app.has_experiment("eager_task_factory"):
    print("eager_task_factory включён")
```

## Доступные флаги

| Флаг | Python | Описание |
|------|--------|----------|
| `eager_task_factory` | 3.12+ | Ускоряет создание asyncio-задач через `asyncio.eager_task_factory` |

## eager_task_factory

При включении устанавливает `asyncio.eager_task_factory` на event loop. Это заставляет корутины, созданные через `asyncio.create_task()` и `TaskGroup.create_task()`, начинать выполнение **сразу** — синхронно, до первого реального `await`. Без этого флага каждая задача откладывается до следующей итерации event loop.

### Когда это полезно

- Бот обрабатывает много событий в секунду
- Много пакетов с фильтрами, которые быстро отклоняют события
- Корутины, которые возвращают результат без I/O (кэшированные данные, простые проверки)

### Пример

```python
import vkflow as vf

app = vf.App(
    prefixes=["/"],
    experimental={"eager_task_factory": True},
)

@app.command("ping")
async def ping(ctx):
    await ctx.reply("Pong!")

app.run("$VK_TOKEN")
```

!!! note "Требования к версии Python"
    Если `eager_task_factory` включён на Python ниже 3.12, фреймворк выдаст предупреждение и проигнорирует флаг. Приложение продолжит работу в обычном режиме.

!!! warning "Асинхронный запуск"
    При вызове `app.run()` внутри уже существующего event loop флаг также применяется. Это повлияет на весь event loop, включая сторонний код.

## Неизвестные флаги

Если передать несуществующий ключ, фреймворк выдаст предупреждение:

```python
app = vf.App(experimental={"nonexistent": True})
# UserWarning: Unknown experimental feature: 'nonexistent'. Available: ['eager_task_factory']
```
