"""Registry artifact model — the schema the Policy Generator reads (persistence.load_registry)."""
from __future__ import annotations
from enum import IntEnum


class Sensitivity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def parse(cls, v) -> "Sensitivity":
        if isinstance(v, Sensitivity):
            return v
        if isinstance(v, int):
            return cls(v)
        s = str(v).strip().upper()
        return cls[s] if s in cls.__members__ else cls.LOW
