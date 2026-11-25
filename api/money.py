"""Перевод денег между Decimal-рублями ядра и копейками в БД."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def to_kop(value: Decimal | int | float | str) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_kop(value: int) -> Decimal:
    return (Decimal(value) / 100).quantize(Decimal("0.01"))


def rub(value: int) -> float:
    return float(from_kop(value))


def plain(value: object) -> object:
    """JSON-безопасное представление Decimal/datetime вложенных структур."""
    from datetime import date, datetime

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value
