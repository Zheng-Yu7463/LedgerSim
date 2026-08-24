"""Strong value objects, business dates, and deterministic identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Self
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

DOMAIN_NAMESPACE = UUID("469fd1ac-05ca-5a21-a731-98559970316b")
MONEY_PLACES = Decimal("0.01")


class ValueContractError(ValueError):
    pass


def _decimal(value: str | Decimal, places: Decimal) -> Decimal:
    candidate = Decimal(value)
    if not candidate.is_finite():
        raise ValueContractError("numeric values must be finite")
    return candidate.quantize(places, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class DomainId:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueContractError("domain IDs cannot be empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SignedMoney:
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _decimal(self.amount, MONEY_PLACES))

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    @classmethod
    def zero(cls) -> Self:
        return cls.parse("0")

    def __add__(self, other: SignedMoney) -> SignedMoney:
        return SignedMoney(self.amount + other.amount)

    def __sub__(self, other: SignedMoney) -> SignedMoney:
        return SignedMoney(self.amount - other.amount)

    def add_amount(self, other: PositiveMoney | NonNegativeMoney) -> SignedMoney:
        return SignedMoney(self.amount + other.amount)

    def __str__(self) -> str:
        return format(self.amount, ".2f")


@dataclass(frozen=True, slots=True)
class NonNegativeMoney:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = _decimal(self.amount, MONEY_PLACES)
        if normalized < 0:
            raise ValueContractError("money amount cannot be negative")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    @classmethod
    def zero(cls) -> Self:
        return cls.parse("0")

    @classmethod
    def from_positive(cls, value: PositiveMoney) -> Self:
        return cls(value.amount)

    def subtract(self, other: PositiveMoney) -> NonNegativeMoney:
        return NonNegativeMoney(self.amount - other.amount)

    def as_signed(self) -> SignedMoney:
        return SignedMoney(self.amount)

    def __str__(self) -> str:
        return format(self.amount, ".2f")


@dataclass(frozen=True, slots=True)
class PositiveMoney:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = _decimal(self.amount, MONEY_PLACES)
        if normalized <= 0:
            raise ValueContractError("business money amount must be positive")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def as_non_negative(self) -> NonNegativeMoney:
        return NonNegativeMoney(self.amount)

    def __str__(self) -> str:
        return format(self.amount, ".2f")


@dataclass(frozen=True, slots=True)
class Quantity:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = _decimal(self.amount, Decimal("0.0001"))
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
        normalized = _decimal(self.amount, Decimal("0.0001"))
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
        normalized = _decimal(self.amount, Decimal("0.0001"))
        if normalized <= 0:
            raise ValueContractError("unit price must be positive")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def total(self, quantity: Quantity) -> PositiveMoney:
        return PositiveMoney(self.amount * quantity.amount)

    def __str__(self) -> str:
        return format(self.amount, ".4f")


@dataclass(frozen=True, slots=True)
class UnitCost:
    amount: Decimal

    def __post_init__(self) -> None:
        normalized = _decimal(self.amount, Decimal("0.000001"))
        if normalized <= 0:
            raise ValueContractError("unit cost must be positive")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, value: str | Decimal) -> Self:
        return cls(Decimal(value))

    def total(self, quantity: Quantity) -> NonNegativeMoney:
        return NonNegativeMoney(self.amount * quantity.amount)

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


@dataclass(frozen=True, slots=True)
class BusinessDate:
    value: date

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(date.fromisoformat(value))

    @property
    def period(self) -> str:
        return self.value.isoformat()[:7]

    def __str__(self) -> str:
        return self.value.isoformat()


@dataclass(frozen=True, slots=True)
class BusinessCalendar:
    timezone_name: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone_name)
        except KeyError as error:
            raise ValueContractError(f"unknown business timezone: {self.timezone_name}") from error

    def date_of(self, instant: Instant) -> BusinessDate:
        return BusinessDate(instant.value.astimezone(ZoneInfo(self.timezone_name)).date())


def deterministic_id(kind: str, *parts: object) -> DomainId:
    material = "|".join((kind, *(str(part) for part in parts)))
    return DomainId(str(uuid5(DOMAIN_NAMESPACE, material)))
