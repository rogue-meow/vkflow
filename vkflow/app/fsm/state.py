from __future__ import annotations

import typing
from dataclasses import dataclass, field


__all__ = (
    "State",
    "StateGroup",
)


class StateMeta(type):
    """
    Metaclass for automatic state name assignment in StateGroup.

    When a StateGroup subclass is created, this metaclass:
    1. Finds all State attributes
    2. Sets their names based on attribute names
    3. Sets their group reference
    4. Collects them into __states__ dict
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        if name == "StateGroup":
            cls.__states__ = {}
            cls.__group_name__ = ""
            return cls

        states: dict[str, State] = {}

        for attr_name, attr_value in namespace.items():
            if isinstance(attr_value, State):
                attr_value._set_state_name(attr_name)
                attr_value._set_group(cls)
                states[attr_name] = attr_value

        cls.__states__ = states
        cls.__group_name__ = name

        return cls


@dataclass
class State:
    """
    Represents a state in FSM.

    Can be used as:
    - Standalone state: state = State("waiting_name")
    - Part of StateGroup: waiting_name = State() inside class

    Examples:
        # Standalone
        my_state = State("waiting_input")

        # In StateGroup
        class OrderStates(StateGroup):
            waiting_name = State()
            waiting_phone = State()

        # Access
        OrderStates.waiting_name.name  # "OrderStates:waiting_name"
    """

    _name: str | None = field(default=None, repr=False)
    _group: type | None = field(default=None, repr=False)

    def __init__(self, name: str | None = None):
        """
        Initialize a State.

        Args:
            name: Optional explicit name. If not provided, will be set
                  automatically when used in StateGroup.
        """
        self._name = name
        self._group = None

    def _set_state_name(self, name: str) -> None:
        """Set the state name (called by StateMeta)."""
        if self._name is None:
            self._name = name

    def _set_group(self, group: type) -> None:
        """Set the group reference (called by StateMeta)."""
        self._group = group

    @property
    def name(self) -> str:
        """
        Full state name: "GroupName:state_name" or just "state_name".

        Returns:
            The full qualified name of the state.
        """
        if self._group is not None:
            return f"{self._group.__name__}:{self._name}"
        return self._name or ""

    @property
    def state(self) -> str:
        """
        Short state name (without group).

        Returns:
            The state name without group prefix.
        """
        return self._name or ""

    @property
    def group(self) -> type | None:
        """
        The StateGroup this state belongs to.

        Returns:
            The StateGroup class or None if standalone.
        """
        return self._group

    def __eq__(self, other: object) -> bool:
        if isinstance(other, State):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other or self.state == other
        return False

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"<State {self.name!r}>"

    def __str__(self) -> str:
        return self.name


class StateGroup(metaclass=StateMeta):
    """
    A group of related states.

    StateGroup provides a way to organize states logically and
    access them as class attributes.

    Examples:
        class OrderStates(StateGroup):
            waiting_name = State()
            waiting_phone = State()
            confirm = State()

        # Access states
        OrderStates.waiting_name  # <State 'OrderStates:waiting_name'>

        # Get all states
        OrderStates.all_states()  # [State, State, State]

        # Check if state is in group
        OrderStates.waiting_name in OrderStates.all_states()  # True
    """

    __states__: typing.ClassVar[dict[str, State]]
    __group_name__: typing.ClassVar[str]

    @classmethod
    def all_states(cls) -> list[State]:
        """
        Get all states in this group.

        Returns:
            List of all State objects in this group.
        """
        return list(cls.__states__.values())

    @classmethod
    def get_state(cls, name: str) -> State | None:
        """
        Get a state by its short name.

        Args:
            name: The short name of the state (without group prefix).

        Returns:
            The State object or None if not found.
        """
        return cls.__states__.get(name)

    @classmethod
    def __contains__(cls, item: State | str) -> bool:
        """
        Check if a state belongs to this group.

        Args:
            item: State object or state name string.

        Returns:
            True if the state is in this group.
        """
        if isinstance(item, State):
            return item in cls.__states__.values()
        if isinstance(item, str):
            if ":" in item:
                group_name, state_name = item.split(":", 1)
                return group_name == cls.__group_name__ and state_name in cls.__states__
            return item in cls.__states__
        return False
