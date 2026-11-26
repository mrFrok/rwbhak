"""Проводки ledger. Чистые функции: на вход событие, на выход двойные записи.

Сумма проводок по событию всегда 0. Идемпотентность обеспечивает слой API:
здесь только состав проводок.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import parameters as P
from .economics import (
    on_time_bonus,
    pvz_storage_payout,
    seller_storage_fee,
    shelf_sale_bonus,
)
from .parameters import q

MARKETPLACE = "marketplace"


def pvz_account(pvz_id: int) -> str:
    return f"pvz:{pvz_id}"


def seller_account(seller_id: int) -> str:
    return f"seller:{seller_id}"


@dataclass(frozen=True)
class Entry:
    account: str
    amount: Decimal
    kind: str
    line_no: int


def _pair(debit: str, credit: str, amount: Decimal, kind: str) -> list[Entry]:
    if amount <= 0:
        return []
    return [Entry(debit, -amount, kind, 0), Entry(credit, amount, kind, 1)]


def acceptance(size_code: str, pvz_id: int, qty: int = 1) -> list[Entry]:
    size = P.get_size(size_code)
    amount = q(P.MESH_ACCEPTANCE * size.ops_factor * qty)
    return _pair(MARKETPLACE, pvz_account(pvz_id), amount, "ACCEPTANCE")


def storage(size_code: str, pvz_id: int, seller_id: int, days: int) -> list[Entry]:
    """ПВЗ получает за место с первого дня; продавец платит по прогрессивному тарифу."""
    payout = pvz_storage_payout(size_code, days)
    fee = seller_storage_fee(size_code, days)
    entries = _pair(MARKETPLACE, pvz_account(pvz_id), payout, "STORAGE_PVZ")
    entries += _pair(seller_account(seller_id), MARKETPLACE, fee, "STORAGE_SELLER")
    return entries


def picking(size_code: str, pvz_id: int) -> list[Entry]:
    size = P.get_size(size_code)
    return _pair(MARKETPLACE, pvz_account(pvz_id), q(P.MESH_PICKING * size.ops_factor), "PICKING")


def issue(size_code: str, pvz_id: int, mode: str, storage_days: int = P.MESH_STORAGE_DAYS) -> list[Entry]:
    """Бонусы ПВЗ при выдаче: SLA за срок, режим A — дополнительно «со своей полки»."""
    if mode not in ("A", "B"):
        return []
    entries = _pair(
        MARKETPLACE,
        pvz_account(pvz_id),
        on_time_bonus(size_code, storage_days),
        "ON_TIME_BONUS",
    )
    if mode == "A":
        entries += _pair(
            MARKETPLACE,
            pvz_account(pvz_id),
            shelf_sale_bonus(size_code, storage_days),
            "SHELF_BONUS",
        )
    return entries


def hub_route(size_code: str, *, cost: Decimal | None = None) -> list[Entry]:
    """Режим C: услуги хаба — внутренние затраты маркетплейса.

    Показываем одной проводкой «маркетплейс → хаб», чтобы в аналитике было видно
    себестоимость заказа через хаб. Счёт хаба — служебный.
    """
    from .economics import hub_cost

    amount = hub_cost(size_code) if cost is None else cost
    return _pair(MARKETPLACE, "hub", amount, "HUB_ROUTE")


def return_event(
    size_code: str,
    pvz_id: int,
    seller_id: int,
    *,
    reverse_picking: bool = True,
    reverse_bonus: bool = True,
    storage_days: int = P.MESH_STORAGE_DAYS,
) -> list[Entry]:
    """Возврат по бизнес-модели v0.3 (раздел 12.2).

    Бонус за выдачу не начисляется — сторнируем его; сборка сторнируется, если
    была оплачена; продавец платит обратную логистику 50 ₽. Хранение продолжает
    считаться по обычным тарифам, отдельной проводки не требуется.
    """
    size = P.get_size(size_code)
    entries: list[Entry] = []
    if reverse_picking:
        entries += _pair(
            pvz_account(pvz_id), MARKETPLACE, q(P.MESH_PICKING * size.ops_factor), "RETURN_PICKING_REVERSAL"
        )
    if reverse_bonus:
        entries += _pair(
            pvz_account(pvz_id),
            MARKETPLACE,
            on_time_bonus(size_code, storage_days),
            "RETURN_BONUS_REVERSAL",
        )
    entries += _pair(
        seller_account(seller_id), MARKETPLACE, P.RETURN_LOGISTICS_FEE, "RETURN_LOGISTICS"
    )
    return entries


def balance(entries: list[Entry]) -> Decimal:
    return sum((entry.amount for entry in entries), Decimal("0"))
