"""Ежедневное начисление хранения по модельным часам."""

from decimal import Decimal

from sqlalchemy import func, select

from api.db import SessionLocal
from api.models import LedgerEntry, Pvz
from tests.conftest import key


def _storage_entries(batch_id: int) -> list[LedgerEntry]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.idempotency_key.like(f"storage:{batch_id}:%"))
                .order_by(LedgerEntry.idempotency_key, LedgerEntry.line_no)
            ).all()
        )


def test_storage_accrues_daily_without_double_charge(client):
    sku = next(s for s in client.get("/skus").json() if s["size_class"] == "S")
    batch = client.post(
        "/batches",
        headers=key("accrual-batch"),
        json={"seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 5, "qty": 2, "declared_class": "S"},
    ).json()
    batch_id = batch["batch_id"]

    first = client.post("/api/time/advance", json={"days": 4}, headers=key("accrual-1"))
    assert first.status_code == 200
    entries = _storage_entries(batch_id)
    assert entries, "хранение должно начислиться при сдвиге времени"
    pvz_entries = [e for e in entries if e.entry_type == "STORAGE_PVZ" and e.account.startswith("pvz:")]
    assert pvz_entries and all(e.amount_kop > 0 for e in pvz_entries)
    assert sum(e.amount_kop for e in entries) == 0

    count_after_first = len({e.idempotency_key for e in entries})
    client.post("/api/time/advance", json={"days": 1}, headers=key("accrual-2"))
    entries = _storage_entries(batch_id)
    assert len({e.idempotency_key for e in entries}) == count_after_first + 1

    # повтор того же запроса не должен создать новые проводки
    client.post("/api/time/advance", json={"days": 1}, headers=key("accrual-2"))
    assert len({e.idempotency_key for e in _storage_entries(batch_id)}) == count_after_first + 1


def test_storage_payout_matches_um_days(client):
    sku = next(s for s in client.get("/skus").json() if s["size_class"] == "M")
    batch = client.post(
        "/batches",
        headers=key("accrual-m"),
        json={"seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 5, "qty": 1, "declared_class": "M"},
    ).json()
    client.post("/api/time/advance", json={"days": 1}, headers=key("accrual-m-time"))
    entries = _storage_entries(batch["batch_id"])
    payout = [e for e in entries if e.entry_type == "STORAGE_PVZ" and e.account.startswith("pvz:")]
    # M = 3 УМ × 3 ₽ × 1 день × 1 единица
    assert sum(e.amount_kop for e in payout) == 900


def test_global_ledger_balances(client):
    client.post("/api/time/advance", json={"days": 5}, headers=key("accrual-global"))
    with SessionLocal() as db:
        total = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_kop), 0)))
    assert Decimal(int(total)) == 0


def test_stale_stock_is_removed_after_alert_day(client):
    sku = next(s for s in client.get("/skus").json() if s["size_class"] == "S")
    batch = client.post(
        "/batches",
        headers=key("removal-batch"),
        json={"seller_id": sku["seller_id"], "sku_id": sku["id"], "pvz_id": 5, "qty": 2, "declared_class": "S"},
    ).json()
    batch_id = batch["batch_id"]

    client.post("/api/time/advance", json={"days": 15}, headers=key("removal-15"))
    alerts = client.get("/pvz/5/stock").json()["alerts"]
    assert any(row["batch_id"] == batch_id and row["type"] == "REMOVAL_D15" for row in alerts)

    client.post("/api/time/advance", json={"days": 1}, headers=key("removal-16"))
    stock = client.get("/pvz/5/stock").json()
    row = next(item for item in stock["batches"] if item["batch_id"] == batch_id)
    assert row["qty"] == 0 and row["qty_free"] == 0

    with SessionLocal() as db:
        entries = list(db.scalars(
            select(LedgerEntry).where(LedgerEntry.idempotency_key == f"removal:{batch_id}")
        ).all())
    assert {e.entry_type for e in entries} == {"REMOVAL_FEE"}
    assert sum(e.amount_kop for e in entries) == 0
    seller_line = next(e for e in entries if e.account.startswith("seller:"))
    assert seller_line.amount_kop == -35 * 100 * 2  # 35 ₽ за единицу, 2 единицы
