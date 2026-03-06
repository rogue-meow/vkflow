# Система аддонов

Аддоны расширяют функциональность приложения, добавляя новые возможности при старте и остановке бота.

## Подключение аддонов

### При создании App

```python
import vkflow as vf
from vkflow.addons.autodoc import AutoDoc

app = vf.App(addons=[AutoDoc()])
```

### После создания

```python
app = vf.App()
app.add_addon(AutoDoc())
```

### Получение аддона

```python
autodoc = app.get_addon("autodoc")
```

## Встроенные аддоны

### AutoDoc

Автоматическая генерация HTML-документации по командам бота. Использует Jinja2 для рендеринга.

```python
from vkflow.addons.autodoc import AutoDoc

app = vf.App(addons=[AutoDoc()])

@app.command("ping")
async def ping():
    """Проверка работоспособности бота"""
    return "Pong!"

@app.command("инфо")
async def info(user: vf.User):
    """Показать информацию о пользователе"""
    return f"{user.first_name} {user.last_name}"

# AutoDoc сгенерирует HTML-страницу со списком команд,
# их описаниями (из docstring) и аргументами
```

### FastAPI

Интеграция с FastAPI для создания веб-интерфейса рядом с ботом:

```python
from vkflow.addons.fastapi import FastAPIAddon

addon = FastAPIAddon(
    host="0.0.0.0",
    port=8080,
)
app.add_addon(addon)
```

FastAPI-аддон предоставляет:

- Встроенные эндпоинты для VK Callback API
- API Key middleware для защиты эндпоинтов
- Dependency injection хелперы (`get_vk_app`, `get_bot`, `get_api`)

```python
from vkflow.addons.fastapi.dependencies import get_vk_app, get_bot, get_api

# В ваших FastAPI-маршрутах:
@router.get("/stats")
async def stats(app=Depends(get_vk_app)):
    return {"commands": len(app.commands)}
```

### Callback API через FastAPI

```python
from vkflow.addons.fastapi import FastAPIAddon

addon = FastAPIAddon(
    host="0.0.0.0",
    port=8080,
    confirmation_code="abc123",  # Код подтверждения из настроек VK
    secret="my_secret",          # Секретный ключ (опционально)
)
app.add_addon(addon)
```

## Создание своего аддона

```python
from vkflow.addons.base import BaseAddon, AddonMeta

class AnalyticsAddon(BaseAddon):
    meta = AddonMeta(
        name="analytics",
        description="Аналитика использования команд",
        version="1.0.0",
    )

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.db = None

    async def on_startup(self, app, bots):
        """Вызывается при запуске приложения (после создания всех ботов)"""
        self.db = await connect(self.db_url)
        print(f"Analytics connected to {self.db_url}")

    async def on_shutdown(self, app, bots):
        """Вызывается при остановке приложения"""
        if self.db:
            await self.db.close()

# Использование
app = vf.App(addons=[AnalyticsAddon("postgresql://...")])
```

### Зависимости между аддонами

```python
class MyAddon(BaseAddon):
    meta = AddonMeta(
        name="my_addon",
        description="Мой аддон",
        dependencies=["analytics"],  # Требует analytics-аддон
    )

    def check_dependencies(self):
        """Вызывается автоматически при регистрации"""
        super().check_dependencies()
        # Дополнительные проверки
```

### Конфликты аддонов

Нельзя зарегистрировать два аддона с одним именем:

```python
app.add_addon(AutoDoc())
app.add_addon(AutoDoc())  # AddonConflictError!
```

## Обнаружение аддонов

VKFlow поддерживает автоматическое обнаружение аддонов через entry_points:

```python
from vkflow.addons import get_available_addons

# Показать все доступные аддоны (включая установленные пакеты)
for name, addon_class in get_available_addons().items():
    print(f"{name}: {addon_class}")
```
