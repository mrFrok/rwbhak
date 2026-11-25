"""Синтетические данные для демо и симулятора. seed = 42, без персональных данных.

Запуск: `python -m data.seed`. Существующие данные очищаются только с `--reset`.
"""

from __future__ import annotations

import argparse
import random
from datetime import timedelta

from sqlalchemy.orm import Session

from api.db import Base, SessionLocal, init_db
from api.models import Batch, City, Clock, Order, Pvz, Seller, Sku, Trip, Zone
from api.money import plain, to_kop
from api.services import clock, ledger_store
from core import ledger as L
from core import parameters as P
from core.economics import hub_cost, order_cost_mesh
from core.solver import OrderRequest, TripLoad, decide

CITY_NAMES = ("Пермь", "Соликамск", "Москва")
PVZ_DATA = (
    (1, "ПВЗ Компрос", "Комсомольский пр-т, 42", 1),
    (2, "ПВЗ Ленина", "ул. Ленина, 58", 1),
    (3, "ПВЗ Мира", "пр-т Мира, 12", 2),
    (4, "ПВЗ Набережная", "ул. Набережная, 7", 2),
    (5, "ПВЗ Тверская", "ул. Тверская, 9", 3),
)
SELLER_NAMES = (
    "ООО «Спорт Шоп»",
    "ИП Ковалёв",
    "ООО «Дом Товаров»",
    "ИП Смирнова",
    "ООО «ТехноЛайн»",
    "ИП Гарипов",
    "ООО «Красота»",
    "ИП Орлова",
    "ООО «Игрушки Плюс»",
    "ИП Белов",
)
SKU_NAMES = (
    "Кроссовки беговые",
    "Футболка хлопковая",
    "Рюкзак городской",
    "Бутылка спортивная",
    "Наушники TWS",
    "Крем для рук",
    "Шампунь",
    "Маска для лица",
    "Набор носков",
    "Конструктор",
    "Книга детская",
    "Термокружка",
)


def _rng() -> random.Random:
    return random.Random(P.SEED)


def seed(db: Session, reset: bool = False) -> dict[str, int]:
    if reset:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
    if db.get(Clock, 1) is not None:
        return {}
    rng = _rng()
    now = clock.now(db)

    cities = [City(name=name) for name in CITY_NAMES]
    db.add_all(cities)
    db.flush()
    perm, solikamsk, moscow = cities

    db.add_all(
        [
            Zone(from_city_id=perm.id, to_city_id=solikamsk.id, distance_km=120, lambda_per_day=40, class_="GREEN"),
            Zone(from_city_id=perm.id, to_city_id=moscow.id, distance_km=1400, lambda_per_day=2, class_="RED"),
        ]
    )

    pvz_by_id = {}
    for pvz_id, name, address, city_id in PVZ_DATA:
        pvz = Pvz(id=pvz_id, city_id=cities[city_id - 1].id, name=name, address=address)
        db.add(pvz)
        pvz_by_id[pvz_id] = pvz

    sellers = [Seller(name=name, contact=f"contact-{i}@example.test") for i, name in enumerate(SELLER_NAMES, 1)]
    db.add_all(sellers)
    db.flush()

    skus: list[Sku] = []
    for index in range(40):
        seller = sellers[index % len(sellers)]
        size = "S" if index % 10 < 7 else "M"
        special = False
        if index == 37:
            size, special = "L", True
        elif index == 38:
            size = "L"
        elif index == 39:
            size = "L"
        price = rng.randint(900, 12000)
        skus.append(
            Sku(
                seller_id=seller.id,
                name=f"{SKU_NAMES[index % len(SKU_NAMES)]} #{index + 1}",
                price_kop=price * 100,
                unit_cost_kop=int(price * 100 * rng.uniform(0.35, 0.65)),
                size_class=size,
                um=P.SIZE_CLASSES[size].um,
                special=special,
            )
        )
    db.add_all(skus)
    db.flush()

    # Партии: по 8 SKU в каждом городе-коридоре.
    def add_batch(sku: Sku, pvz: Pvz, qty: int, days_ago: int) -> Batch:
        batch = Batch(
            sku_id=sku.id,
            pvz_id=pvz.id,
            qty=qty,
            qty_free=qty,
            received_at=now - timedelta(days=days_ago),
            declared_class=sku.size_class,
            actual_class=sku.size_class,
        )
        db.add(batch)
        db.flush()
        ledger_store.post(db, L.acceptance(sku.size_class, pvz.id, qty), f"seed:accept:{batch.id}", batch.received_at)
        return batch

    batches: dict[tuple[int, int], Batch] = {}
    for pvz in pvz_by_id.values():
        if pvz.city_id == moscow.id:
            selected = [sku for sku in skus if sku.size_class == "S"][:4]
            for sku in selected:
                batches[(sku.id, pvz.id)] = add_batch(sku, pvz, 20, 2)
            continue
        selected = [sku for sku in skus if sku.size_class in ("S", "M")][:10]
        for index, sku in enumerate(selected):
            qty = 40 if pvz.id == 3 and index < 3 else (5 if sku.size_class == "S" else 2)
            batches[(sku.id, pvz.id)] = add_batch(sku, pvz, qty, 3)

    # Рейс 1: Соликамск → Пермь, выделенный, 99 заказов. Следующий даст ровно 100.
    trip1 = Trip(
        from_pvz_id=3,
        to_pvz_id=1,
        kind=P.TRIP_KIND_DEDICATED,
        departs_at=now + timedelta(hours=6),
        cost_kop=int(P.TRIP_COST_DEDICATED * 100),
        capacity_um=P.TRIP_CAPACITY_UM,
        status="PLANNED",
    )
    # Рейс 2: Соликамск → Пермь, попутный, 10 заказов — ниже порога окупаемости.
    trip2 = Trip(
        from_pvz_id=4,
        to_pvz_id=2,
        kind=P.TRIP_KIND_ALONG,
        departs_at=now + timedelta(hours=30),
        cost_kop=int(P.TRIP_COST_ALONG * 100),
        capacity_um=P.TRIP_CAPACITY_UM,
        status="PLANNED",
    )
    db.add_all([trip1, trip2])
    db.flush()

    s_skus = [sku for sku in skus if sku.size_class == "S"]

    def add_trip_order(trip: Trip, index: int, buyer_id: int, source_id: int) -> None:
        sku = s_skus[index % 3]
        batch = batches[(sku.id, source_id)]
        if batch.qty_free <= 0:
            return
        batch.qty_free -= 1
        count = 99 if trip.kind == P.TRIP_KIND_DEDICATED else 10
        wait = 6 if trip.kind == P.TRIP_KIND_DEDICATED else 30
        decision = decide(OrderRequest(
            size_class="S",
            trip=TripLoad(kind=trip.kind, free_um=300 - count + 1, existing_sizes=("S",) * (count - 1), wait_hours=wait),
        ))
        if trip.kind == P.TRIP_KIND_ALONG:
            # Черновая загрузка попутного рейса задана вручную для показа порога.
            decision["mode"] = "B"
            decision["reason"] = "Демо: предварительная загрузка, рейс пока не окупается"
        db.add(
            Order(
                sku_id=sku.id,
                batch_id=batch.id,
                seller_id=sku.seller_id,
                source_pvz_id=source_id,
                buyer_pvz_id=buyer_id,
                trip_id=trip.id,
                um=sku.um,
                status="RESERVED",
                mode="B",
                eta_mesh_h=decision["eta_mesh_h"],
                eta_hub_h=P.HUB_ETA_H,
                cost_mesh_kop=to_kop(decision["cost_mesh"]),
                cost_hub_kop=int(hub_cost("S") * 100),
                decision_json=plain(decision),
                created_at=now - timedelta(hours=rng.randint(1, 20)),
            )
        )

    for index in range(99):
        add_trip_order(trip1, index, buyer_id=1, source_id=3)
    for index in range(10):
        add_trip_order(trip2, index, buyer_id=2, source_id=4)
    db.flush()

    # История: выданные заказы для аналитики ПВЗ и продавца.
    def add_issued(sku: Sku, source_id: int, buyer_id: int, days_ago: int, mode: str = "B") -> None:
        batch = batches.get((sku.id, source_id))
        if batch is None or batch.qty_free <= 0:
            return
        batch.qty_free -= 1
        batch.qty -= 1
        created = now - timedelta(days=days_ago)
        order = Order(
            sku_id=sku.id,
            batch_id=batch.id,
            seller_id=sku.seller_id,
            source_pvz_id=source_id,
            buyer_pvz_id=buyer_id,
            um=sku.um,
            status="ISSUED",
            mode=mode,
            eta_mesh_h=35,
            eta_hub_h=P.HUB_ETA_H,
            cost_mesh_kop=to_kop(order_cost_mesh(sku.size_class, P.TRIP_KIND_DEDICATED, 100)),
            cost_hub_kop=int(hub_cost(sku.size_class) * 100),
            decision_json={"mode": mode, "reason": "исторический заказ демо-данных",
                           "eta_mesh_h": 35, "eta_hub_h": P.HUB_ETA_H,
                           "cost_mesh": float(order_cost_mesh(sku.size_class, P.TRIP_KIND_DEDICATED, 100)),
                           "cost_hub": float(hub_cost(sku.size_class)), "saving": 0},
            created_at=created,
            picked_at=created,
            issued_at=created + timedelta(hours=5),
        )
        db.add(order)
        db.flush()
        days = max(0, (order.issued_at - batch.received_at).days)
        key = f"seed:history:{order.id}"
        ledger_store.post(db, L.storage(sku.size_class, source_id, sku.seller_id, days), key, order.issued_at, order.id)
        ledger_store.post(db, L.picking(sku.size_class, source_id), key, order.issued_at, order.id)
        if mode == "B":
            ledger_store.post(db, L.issue(sku.size_class, source_id, "B", days), key, order.issued_at, order.id)
        else:
            ledger_store.post(db, L.hub_route(sku.size_class), key, order.issued_at, order.id)

    for day in range(1, 4):
        for index in range(6):
            add_issued(s_skus[index % len(s_skus)], source_id=1, buyer_id=2, days_ago=day)
            add_issued(s_skus[(index + 3) % len(s_skus)], source_id=3, buyer_id=1, days_ago=day)
    add_issued([sku for sku in skus if sku.size_class == "M"][0], source_id=1, buyer_id=2, days_ago=2)
    add_issued(s_skus[0], source_id=3, buyer_id=5, days_ago=2, mode="C")

    db.commit()
    return {
        "cities": len(cities),
        "pvz": len(PVZ_DATA),
        "sellers": len(sellers),
        "skus": len(skus),
        "batches": len(batches),
        "trips": 2,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Заполнить БД демо-данными")
    parser.add_argument("--reset", action="store_true", help="очистить БД демо и загрузить данные заново")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        stats = seed(db, reset=args.reset)
    if not stats:
        print("Демо-данные уже загружены; изменений нет.")
        return
    print("Демо-данные загружены:", stats)
    print("Проверка: новый S-заказ из ПВЗ 3 в ПВЗ 1 даёт режим B и 95 ₽ против 109 ₽.")


if __name__ == "__main__":
    main()
