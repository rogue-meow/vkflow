<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-dark.svg">
    <img alt="VKFlow" src="docs/assets/logo-dark.svg" width="120">
  </picture>
</p>

<h1 align="center">VKFlow</h1>

<p align="center">
  <b>Современный асинхронный фреймворк для создания ботов ВКонтакте</b>
</p>

<p align="center">
  <a href="https://pypi.org/project/vkflow"><img src="https://img.shields.io/pypi/v/vkflow?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/vkflow"><img src="https://img.shields.io/pypi/pyversions/vkflow" alt="Python"></a>
  <a href="https://github.com/rogue-meow/vkflow/blob/main/LICENSE"><img src="https://img.shields.io/github/license/rogue-meow/vkflow" alt="License"></a>
  <a href="https://rogue-meow.github.io/vkflow"><img src="https://img.shields.io/badge/docs-mkdocs-blue" alt="Docs"></a>
  <a href="https://vk.com/club236460230"><img src="https://img.shields.io/badge/VK-community-blue?logo=vk" alt="VK"></a>
</p>

---

## Установка

```shell
pip install vkflow
```

С дополнениями для производительности:

```shell
pip install vkflow[speed]
```

## Быстрый старт

```python
import vkflow as vf

app = vf.App()

@app.command("ping")
async def ping():
    return "Pong!"

@app.command("дата")
async def reg_date(user: vf.User):
    date = await vf.get_user_registration_date(user.id)
    return f"{user:@[first_name]} зарегистрирован {date:%d.%m.%Y}"

app.run("YOUR_TOKEN")
```

## Возможности

<table>
<tr><td>

**Type hints как аргументы** - параметры команд парсятся из аннотаций типов

</td><td>

**Интерактивный UI** - клавиатуры, карусели, View с callback-кнопками

</td></tr>
<tr><td>

**FSM** - конечные автоматы для многошаговых диалогов

</td><td>

**Cog-система** - группировка команд в модули

</td></tr>
<tr><td>

**Проверки и cooldown** - декораторы для контроля доступа

</td><td>

**Webhook и LongPoll** - оба режима из коробки

</td></tr>
<tr><td colspan="2">

**Система аддонов** - расширение функциональности через плагины

</td></tr>
</table>

<details>
<summary><b>Интерактивные View</b></summary>

```python
class ConfirmView(vf.ui.View):
    def __init__(self):
        super().__init__(timeout = 60, inline = True)
        self.result = None

    @vf.ui.button(label = "Да", color = "positive")
    async def yes(self, interaction: vf.Callback):
        self.result = True
        await interaction.answer("Принято!")
        self.stop()

    @vf.ui.button(label = "Нет", color = "negative")
    async def no(self, interaction: vf.Callback):
        self.result = False
        await interaction.answer("Отменено")
        self.stop()
```

</details>

<details>
<summary><b>Cog-модули</b></summary>

```python
class Admin(vf.Cog):
    @vf.command("бан")
    @vf.check(...)
    async def ban(self, ctx: vf.Context, user: vf.User):
        ...
        await ctx.reply(f"{user:@[first_name]} забанен")
```

</details>

## Требования

- Python 3.11+
- VK API 5.199

## Credits

Based on [vkquick](https://github.com/deknowny/vkquick).

## Лицензия

[MIT](LICENSE)
