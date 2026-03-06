from __future__ import annotations

import inspect
import typing
from collections import defaultdict

from vkflow.app.package import (
    EventHandler,
    MessageHandler,
    SignalHandler,
    UserAddedHandler,
    UserJoinedByLinkHandler,
    UserReturnedHandler,
)

if typing.TYPE_CHECKING:
    from vkflow.app.bot import App, Bot
    from .core import Command


__all__ = ("Cog",)


class CogMeta(type):
    """
    Метакласс для автоматического сбора метаданных команд и обработчиков.

    Этот метакласс собирает метаданные о командах и обработчиках при создании
    КЛАССА (а не экземпляра), что эффективнее, чем сбор при каждом создании экземпляра.

    Также собирает обработчики FSM-состояний, отмеченные декоратором @fsm.state.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        if name == "Cog":
            cls.__cog_commands_meta__ = []
            cls.__cog_event_handlers_meta__ = {}
            cls.__cog_message_handlers_meta__ = []
            cls.__cog_startup_handlers_meta__ = []
            cls.__cog_shutdown_handlers_meta__ = []
            cls.__cog_inviting_handlers_meta__ = []
            cls.__cog_listeners_meta__ = []
            cls.__cog_fsm_handlers_meta__ = {}

            return cls

        from .core import Command
        from .listener import Listener

        commands_meta = []
        event_handlers_meta = defaultdict(list)
        message_handlers_meta = []
        startup_handlers_meta = []
        shutdown_handlers_meta = []
        inviting_handlers_meta = []
        listeners_meta = []
        fsm_handlers_meta = {}

        for attr_name, attr_value in namespace.items():
            if attr_name.startswith("_"):
                continue

            if isinstance(attr_value, Command):
                commands_meta.append(attr_name)

            elif isinstance(attr_value, Listener):
                event_name = attr_value.event_name
                event_handlers_meta[event_name].append(attr_name)

            elif isinstance(attr_value, EventHandler):
                for event_type in getattr(attr_value, "_event_types", []):
                    event_handlers_meta[event_type].append(attr_name)

            elif isinstance(attr_value, MessageHandler):
                message_handlers_meta.append(attr_name)

            elif isinstance(attr_value, SignalHandler):
                if getattr(attr_value, "_is_startup", False):
                    startup_handlers_meta.append(attr_name)
                elif getattr(attr_value, "_is_shutdown", False):
                    shutdown_handlers_meta.append(attr_name)

            elif isinstance(attr_value, (UserAddedHandler, UserJoinedByLinkHandler, UserReturnedHandler)):
                inviting_handlers_meta.append(attr_name)

            elif hasattr(attr_value, "__cog_listener__"):
                listeners_meta.append(attr_name)

            if hasattr(attr_value, "__fsm_state__"):
                fsm_state = attr_value.__fsm_state__
                state_name = fsm_state.name if hasattr(fsm_state, "name") else str(fsm_state)
                fsm_handlers_meta[state_name] = attr_name

        cls.__cog_commands_meta__ = commands_meta
        cls.__cog_event_handlers_meta__ = dict(event_handlers_meta)
        cls.__cog_message_handlers_meta__ = message_handlers_meta
        cls.__cog_startup_handlers_meta__ = startup_handlers_meta
        cls.__cog_shutdown_handlers_meta__ = shutdown_handlers_meta
        cls.__cog_inviting_handlers_meta__ = inviting_handlers_meta
        cls.__cog_listeners_meta__ = listeners_meta
        cls.__cog_fsm_handlers_meta__ = fsm_handlers_meta

        return cls


class Cog(metaclass=CogMeta):
    """
    Базовый класс для создания когов -коллекций команд и обработчиков.

    Система когов позволяет организовать функциональность бота в отдельные модули.

    Атрибуты:
        qualified_name: Имя кога (по умолчанию -имя класса)
        description: Описание кога (по умолчанию -docstring класса)
        app: Экземпляр App (инжектируется при добавлении кога)
        bot: Экземпляр Bot (инжектируется при добавлении кога)

    Примеры:
        app.add_cog(SimpleCog())
        app.add_cog(CounterCog())
    """

    def __new__(cls, *args, **kwargs):
        """
        Создать новый экземпляр Cog и выполнить базовую инициализацию.

        Этот метод вызывается ДО __init__ и гарантирует, что базовая
        инициализация всегда происходит, даже если пользователь
        не вызывает super().__init__().

        Это ключ к тому, чтобы super().__init__() был необязательным!
        """
        instance = super().__new__(cls)
        instance._cog_base_init()

        return instance

    def _cog_base_init(self):
        """
        Базовая инициализация Cog.

        Вызывается автоматически из __new__, гарантируя, что ВСЕГДА выполняется
        до любого пользовательского кода в __init__.

        Включена защита от повторного вызова для обратной совместимости
        с кодом, вызывающим super().__init__().
        """
        if hasattr(self, "_cog_base_initialized"):
            return

        self._cog_base_initialized = True

        self.app: App | None = None
        self.bot: Bot | None = None

        if not hasattr(self, "__cog_name__"):
            self.__cog_name__ = self.__class__.__name__

        if not hasattr(self, "__cog_description__"):
            self.__cog_description__ = inspect.getdoc(self.__class__) or ""

        self._cog_commands = []
        self._cog_event_handlers = defaultdict(list)
        self._cog_message_handlers = []
        self._cog_startup_handlers = []
        self._cog_shutdown_handlers = []
        self._cog_inviting_handlers = []
        self._cog_listeners = []
        self._cog_fsm_handlers: dict[str, typing.Callable] = {}

        if not hasattr(self, "fsm_storage"):
            self.fsm_storage = None
        if not hasattr(self, "fsm_strategy"):
            self.fsm_strategy = "user_chat"

        self._collect_handlers_from_meta()

    def __init__(self):
        """
        Инициализация Cog.

        Этот метод может быть переопределён в подклассах БЕЗ вызова super().__init__().
        Базовая инициализация выполняется автоматически в __new__.

        Для обратной совместимости вызов super().__init__() по-прежнему работает,
        но не является обязательным.
        """
        self._cog_base_init()

    @property
    def qualified_name(self) -> str:
        """Квалифицированное имя кога"""
        return getattr(self, "__cog_name__", self.__class__.__name__)

    @property
    def description(self) -> str:
        """Описание кога"""
        return getattr(self, "__cog_description__", "")

    def _collect_handlers_from_meta(self):
        """
        Собрать обработчики из метаданных, собранных метаклассом.

        Это эффективнее старого метода _collect_handlers(), потому что:
        1. Метаданные собираются один раз при создании КЛАССА (а не при каждом экземпляре)
        2. Не нужно итерироваться по dir() при каждом создании экземпляра
        3. Мы привязываем только те обработчики, которые точно существуют (из метаданных)

        Этот метод привязывает обработчики к текущему экземпляру через протокол дескрипторов.
        """
        for cmd_name in self.__cog_commands_meta__:
            bound_cmd = getattr(self, cmd_name)
            self._cog_commands.append(bound_cmd)

        for event_name, handler_names in self.__cog_event_handlers_meta__.items():
            for handler_name in handler_names:
                bound_handler = getattr(self, handler_name)
                self._cog_event_handlers[event_name].append(bound_handler)

        for handler_name in self.__cog_message_handlers_meta__:
            bound_handler = getattr(self, handler_name)
            self._cog_message_handlers.append(bound_handler)

        for handler_name in self.__cog_startup_handlers_meta__:
            bound_handler = getattr(self, handler_name)
            self._cog_startup_handlers.append(bound_handler)

        for handler_name in self.__cog_shutdown_handlers_meta__:
            bound_handler = getattr(self, handler_name)
            self._cog_shutdown_handlers.append(bound_handler)

        for handler_name in self.__cog_inviting_handlers_meta__:
            bound_handler = getattr(self, handler_name)
            self._cog_inviting_handlers.append(bound_handler)

        for listener_name in self.__cog_listeners_meta__:
            bound_listener = getattr(self, listener_name)
            self._cog_listeners.append(bound_listener)

        for state_name, handler_name in self.__cog_fsm_handlers_meta__.items():
            bound_handler = getattr(self, handler_name)
            self._cog_fsm_handlers[state_name] = bound_handler

    def _inject_app(self, app: App):
        """Инжектировать экземпляр app в ког"""
        self.app = app

    @classmethod
    def listener(cls, name: str | None = None):
        """
        Декоратор для пометки метода как обработчика событий.

        Аргументы:
            name: Имя события для прослушивания. Если не указано, используется имя метода

        Пример:
            @commands.Cog.listener()
            async def on_message_new(self, event):
                print(f"Новое сообщение: {event}")

            @commands.Cog.listener("message_new")
            async def handle_message(self, event):
                print(f"Обработка: {event}")
        """

        def decorator(func):
            func.__cog_listener__ = True
            func.__cog_listener_name__ = name or func.__name__

            return func

        return decorator

    def get_commands(self) -> list[Command]:
        """
        Получить все команды в этом коге.

        Возвращает:
            Список объектов Command
        """
        return self._cog_commands.copy()

    def walk_commands(self) -> typing.Generator[Command, None, None]:
        """
        Итерация по всем командам в этом коге, включая подкоманды групп.

        Yields:
            Объекты Command
        """
        for command in self._cog_commands:
            yield command

            if hasattr(command, "all_commands"):
                yield from set(command.all_commands.values())

    async def cog_load(self):
        """
        Вызывается при загрузке Cog в App.

        Это асинхронный хук, вызываемый после регистрации Cog
        и добавления всех команд/обработчиков в App.

        Переопределите этот метод для пользовательской логики инициализации:
        - Загрузка данных из базы данных
        - Установка соединений
        - Запуск фоновых задач

        Пример:
            class MyCog(commands.Cog):
                async def cog_load(self):
                    print(f"Ког {self.qualified_name} загружен!")
                    self.db = await connect_to_database()
        """

    async def cog_unload(self):
        """
        Вызывается при выгрузке Cog из App.

        Это асинхронный хук, вызываемый перед удалением Cog
        и снятием регистрации его команд/обработчиков из App.

        Переопределите этот метод для пользовательской логики очистки:
        - Закрытие соединений с базой данных
        - Сохранение состояния
        - Отмена фоновых задач

        Пример:
            class MyCog(commands.Cog):
                async def cog_unload(self):
                    print(f"Ког {self.qualified_name} выгружается...")
                    await self.db.close()
        """

    async def cog_check(self, ctx) -> bool:
        """
        Глобальная проверка, применяемая ко всем командам в этом коге.

        Эта проверка вызывается для каждой команды в коге до
        оценки собственных фильтров/проверок команды.

        Аргументы:
            ctx: Контекст команды (Context)

        Возвращает:
            True, если команда должна быть выполнена, False иначе

        Пример:
            class AdminCog(commands.Cog):
                async def cog_check(self, ctx):
                    return ctx.author in self.admin_ids
        """
        return True

    async def cog_before_invoke(self, ctx):
        """
        Вызывается перед выполнением любой команды в этом коге.

        Этот хук вызывается после прохождения всех проверок, но до
        выполнения handler команды. Если метод вернёт False,
        команда будет отменена.

        Аргументы:
            ctx: Контекст команды (Context)

        Возвращает:
            True для продолжения выполнения, False для отмены

        Пример:
            class MyCog(commands.Cog):
                async def cog_before_invoke(self, ctx):
                    print(f"Запускаю {ctx.command.name}")
        """

    async def cog_after_invoke(self, ctx, result=None, error=None):
        """
        Вызывается после завершения любой команды в этом коге (успех или ошибка).

        Этот хук вызывается всегда, независимо от того, завершилась
        команда успешно или вызвала исключение.

        Аргументы:
            ctx: Контекст команды (Context)
            result: Возвращаемое значение команды (None, если команда упала)
            error: Исключение, если команда упала, None при успехе

        Пример:
            class MyCog(commands.Cog):
                async def cog_after_invoke(self, ctx, result, error):
                    if error:
                        print(f"Команда {ctx.command.name} упала: {error}")
                    else:
                        print(f"Команда {ctx.command.name} выполнена")
        """

    async def cog_command_error(self, ctx, error):
        """
        Вызывается при возникновении ошибки в любой команде этого кога.

        Этот обработчик выполняется параллельно с обычным потоком обработки
        ошибок и НЕ влияет на то, будет ли ошибка проброшена или обработана.
        Полезен для логирования, метрик или уведомлений.

        Аргументы:
            ctx: Контекст команды (Context)
            error: Возникшее исключение

        Пример:
            class MyCog(commands.Cog):
                async def cog_command_error(self, ctx, error):
                    print(f"Ошибка в {ctx.command.name}: {error}")
                    await self.send_error_to_admin(error)
        """

    async def cog_command_fallback(self, ctx, error):
        """
        Вызывается, когда ошибка команды не обработана ни одним обработчиком ошибок.

        Это fallback, который выполняется ПОСЛЕ проверки всех обработчиков
        ошибок конкретной команды. Если этот метод вызван, значит ни один
        обработчик @command.on_error() не подошёл к ошибке.

        В отличие от cog_command_error, может «обработать» ошибку и
        предотвратить её повторный проброс.

        Аргументы:
            ctx: Контекст команды (Context)
            error: Возникшее исключение

        Пример:
            class MyCog(commands.Cog):
                async def cog_command_fallback(self, ctx, error):
                    await ctx.send(f"Произошла ошибка: {type(error).__name__}")
        """

    def get_fsm(self, ctx, *, strategy: str | None = None):
        """
        Получить FSMContext для данного контекста.

        Аргументы:
            ctx: Context, NewMessage или CallbackButtonPressed
            strategy: Опциональное переопределение стратегии ключа

        Возвращает:
            Экземпляр FSMContext

        Исключения:
            ValueError: Если fsm_storage не настроен

        Пример:
            @commands.command()
            async def start_order(self, ctx):
                fsm = self.get_fsm(ctx)
                await fsm.set_state(OrderStates.waiting_name)
                await ctx.send("Введите ваше имя:")
        """
        from vkflow.app.fsm import Context as FSMContext

        if self.fsm_storage is None:
            raise ValueError(
                f"FSM-хранилище не настроено для {self.qualified_name}. "
                "Установите self.fsm_storage в __init__ или как атрибут класса."
            )

        message = ctx._message if hasattr(ctx, "_message") else ctx

        return FSMContext.from_message(
            self.fsm_storage,
            message,
            strategy=strategy or self.fsm_strategy,
        )

    async def process_fsm(self, message) -> bool:
        """
        Обработать сообщение через FSM-обработчики в этом коге.

        Аргументы:
            message: NewMessage для обработки

        Возвращает:
            True, если обработчик был вызван, False иначе

        Пример:
            # В App.route_message или пользовательском обработчике:
            for cog in self.cogs.values():
                if await cog.process_fsm(message):
                    return  # FSM обработал сообщение
        """
        if self.fsm_storage is None or not self._cog_fsm_handlers:
            return False

        from vkflow.app.fsm import Context as FSMContext

        fsm_ctx = FSMContext.from_message(
            self.fsm_storage,
            message,
            strategy=self.fsm_strategy,
        )

        current_state = await fsm_ctx.get_state()
        if current_state is None:
            return False

        handler = self._cog_fsm_handlers.get(current_state)
        if handler is None:
            return False

        sig = inspect.signature(handler)
        kwargs = {}

        for param_name in sig.parameters:
            if param_name == "self":
                continue
            if param_name in ("ctx", "fsm"):
                kwargs[param_name] = fsm_ctx
            elif param_name in ("msg", "message"):
                kwargs[param_name] = message
            elif param_name == "data":
                kwargs[param_name] = await fsm_ctx.get_data()
            elif param_name == "state":
                kwargs[param_name] = current_state

        await handler(**kwargs)
        return True

    def get_fsm_states(self) -> list[str]:
        """
        Получить все FSM-состояния, обрабатываемые этим когом.

        Возвращает:
            Список строк с именами состояний
        """
        return list(self._cog_fsm_handlers.keys())

    def __repr__(self):
        return f"<Cog {self.qualified_name!r}>"
