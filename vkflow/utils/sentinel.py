"""
Sentinel value for distinguishing missing parameters from None.
"""

__all__ = ["MISSING", "MissingSentinel"]


class MissingSentinel:
    """Sentinel singleton for missing parameter detection."""

    __slots__ = ()
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __eq__(self, other):
        return self is other

    def __bool__(self):
        return False

    def __hash__(self):
        return hash("MISSING")

    def __repr__(self):
        return "MISSING"


MISSING: MissingSentinel = MissingSentinel()
