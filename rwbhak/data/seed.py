"""Генератор синтетических данных (seed = 42). Реальных персональных данных нет.

python -m data.seed  →  data/orders.csv, data/entities.json
Backend расширяет этот файл до загрузки в БД (продавцы, SKU, партии, ПВЗ).
"""
import csv
import json
import random
from pathlib import Path

from core.parameters import Params, UM
from core.simulation import generate_orders

OUT = Path(__file__).parent


def build(seed: int = 42) -> dict:
    p = Params()
    rng = random.Random(seed)
    cities = [{"id": 1, "name": "Город А"}, {"id": 2, "name": "Город Б"}]
    pvz = [{"id": i + 1, "city_id": 1 + i // 2, "capacity_um": p.pvz_capacity_um,
            "name": f"ПВЗ-{i + 1}"} for i in range(p.pvz_count)]
    sellers = [{"id": i + 1, "name": f"Продавец-{i + 1}"} for i in range(10)]
    sku = []
    for i in range(40):
        cls = rng.choices(["S", "M", "L", "KGT"], [p.share_S, p.share_M, p.share_L, p.share_KGT])[0]
        price = round(rng.uniform(300, 3000), -1)
        sku.append({"id": i + 1, "seller_id": sellers[i % 10]["id"], "size_class": cls,
                    "um": UM[cls], "price": price, "unit_cost": round(price * rng.uniform(0.4, 0.7), 0)})
    orders = []
    for o in generate_orders(p, seed):
        s = rng.choice([x for x in sku if x["size_class"] == o.size] or sku)
        orders.append({"id": o.id, "t_hours": round(o.t, 2), "size_class": o.size,
                       "nearby": int(o.nearby), "sku_id": s["id"],
                       "buyer_pvz_id": rng.choice(pvz)["id"]})
    return {"cities": cities, "pvz": pvz, "sellers": sellers, "sku": sku, "orders": orders}


if __name__ == "__main__":
    data = build()
    orders = data.pop("orders")
    (OUT / "entities.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT / "orders.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(orders[0].keys()))
        w.writeheader()
        w.writerows(orders)
    print(f"orders: {len(orders)}, pvz: {len(data['pvz'])}, sku: {len(data['sku'])}")
