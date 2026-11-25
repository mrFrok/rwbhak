"""Ledger: двойная запись и отсутствие дублей на уровне формул."""

from decimal import Decimal

from core import ledger as L


def test_every_event_balances_to_zero():
    events = [
        L.acceptance("S", 1),
        L.acceptance("M", 1, qty=3),
        L.storage("S", 1, 2, 3),
        L.storage("M", 1, 2, 14),
        L.picking("S", 1),
        L.issue("S", 1, "B"),
        L.issue("S", 1, "A"),
        L.issue("S", 1, "C"),
    ]
    for entries in events:
        assert L.balance(entries) == Decimal("0")


def test_return_event_balances_with_all_reversals():
    for entries in (
        L.return_event("S", 1, 2),
        L.return_event("S", 1, 2, reverse_picking=False),
        L.return_event("M", 1, 2, reverse_bonus=False),
    ):
        assert L.balance(entries) == Decimal("0")


def test_acceptance_pays_pvz():
    entries = L.acceptance("M", 7)
    pvz = [e for e in entries if e.account == "pvz:7"]
    assert len(pvz) == 1
    assert pvz[0].amount == Decimal("13.00")


def test_on_time_bonus_is_ten_percent():
    entries = L.issue("S", 1, "B")
    pvz = [e for e in entries if e.account == "pvz:1"][0]
    assert pvz.amount == Decimal("4.00")


def test_mode_a_pays_both_bonuses():
    # v0.3: режим A — SLA-бонус 4 ₽ и бонус полки 2 ₽ отдельными проводками
    entries = L.issue("S", 1, "A")
    pvz_total = sum(e.amount for e in entries if e.account == "pvz:1")
    assert pvz_total == Decimal("6.00")
    assert {e.kind for e in entries} == {"ON_TIME_BONUS", "SHELF_BONUS"}


def test_return_reverses_bonus_and_charges_logistics():
    entries = L.return_event("S", 1, 2)
    pvz = sum(e.amount for e in entries if e.account == "pvz:1")
    seller = [e for e in entries if e.account == "seller:2"]
    assert pvz == Decimal("-25.00")  # сторно сборки 21 и бонуса 4
    assert seller[0].amount == Decimal("-50.00")  # обратная логистика
    assert {e.kind for e in entries} == {"RETURN_PICKING_REVERSAL", "RETURN_BONUS_REVERSAL", "RETURN_LOGISTICS"}
