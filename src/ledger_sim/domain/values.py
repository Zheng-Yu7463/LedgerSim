"""Strong value objects and deterministic identifiers for the domain kernel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Self
from uuid import UUID, uuid5

DOMAIN_NAMESPACE = UUID("469fd1ac-05ca-5a21-a731-98559970316b")


class ValueContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DomainId:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueContractError("domain IDs cannot be empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "amount",
            self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    @classmethod
    def zero(cls) -> Self:
        return cls.parse("0")

    def __add__(self, other: Money) -> Money:
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        return Money(self.amount - other.amount)

    def __mul__(self, other: Quantity | Decimal) -> Money:
        factor = other.amount if isinstance(other, Quantity) else other
        return Money(self.amount * factor)

    def __lt__(self, other: Money) -> bool:
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        return self.amount <= other.amount

    def __str__(self) -> str:
        return format(self.amount, ".2f")


@dataclass(frozen=True, slots=True)
class Quantity:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = self.amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if normalized <= 0:
            raise ValueContractError("quantity must be positive")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def __str__(self) -> str:
        return format(self.amount, ".4f")


@dataclass(frozen=True, slots=True)
class QuantityBalance:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = self.amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if normalized < 0:
            raise ValueContractError("quantity balance cannot be negative")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def subtract(self, quantity: Quantity) -> QuantityBalance:
        return QuantityBalance(self.amount - quantity.amount)

    def __str__(self) -> str:
        return format(self.amount, ".4f")


@dataclass(frozen=True, slots=True)
class UnitPrice:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = self.amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if normalized < 0:
            raise ValueContractError("unit price cannot be negative")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def total(self, quantity: Quantity) -> Money:
        return Money(self.amount * quantity.amount)

    def __str__(self) -> str:
        return format(self.amount, ".4f")


@dataclass(frozen=True, slots=True)
class UnitCost:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = self.amount.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if normalized < 0:
            raise ValueContractError("unit cost cannot be negative")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def total(self, quantity: Quantity) -> Money:
        return Money(self.amount * quantity.amount)

    def __str__(self) -> str:
        return format(self.amount, ".6f")


@dataclass(frozen=True, slots=True)
class Instant:
    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise ValueContractError("instant must be timezone aware")
        object.__setattr__(self, "value", self.value.astimezone(UTC))

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(datetime.fromisoformat(value.replace("Z", "+00:00")))

    def __lt__(self, other: Instant) -> bool:
        return self.value < other.value

    def __le__(self, other: Instant) -> bool:
        return self.value <= other.value

    def __str__(self) -> str:
        return self.value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def deterministic_id(kind: str, *parts: object) -> DomainId:
    material = "|".join((kind, *(str(part) for part in parts)))
    return DomainId(str(uuid5(DOMAIN_NAMESPACE, material)))
