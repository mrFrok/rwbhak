"""Аналитика и модель."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core import parameters as P
from core.breakeven import summary
from core.economics import breakeven_orders, hub_cost, order_cost_mesh, pilot_summary
from core.simulation import build_flow, compare as compare_flow, plan_trips, sensitivity
from ..db import get_db
from ..money import plain, rub
from ..schemas import SimulateIn
from ..services import clock
from ..services.analytics import pvz_analytics, seller_analytics

router = APIRouter(tags=["analytics"])


@router.get("/analytics/pvz/{pvz_id}")
def pvz_report(pvz_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return pvz_analytics(db, pvz_id)


@router.get("/analytics/seller/{seller_id}")
def seller_report(seller_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return seller_analytics(db, seller_id, clock.now(db))


def _compare_payload(
    orders: int, seed: int, kind: str, days: int, *, with_sensitivity: bool = False
) -> dict[str, object]:
    flow = build_flow(orders, seed)
    result = compare_flow(flow, kind, days)
    trips = plan_trips(flow, kind)
    result["trip_sizes"] = [len(trip) for trip in trips]
    result["thresholds"] = summary()["thresholds"]
    result["pilot"] = pilot_summary()
    if with_sensitivity:
        result["sensitivity"] = sensitivity(flow, kind, days)
    return plain(result)


@router.get("/compare")
def compare(
    days: int = Query(P.DEMO_DAYS, ge=1, le=365),
    kind: Literal["DEDICATED", "ALONG"] = P.TRIP_KIND_DEDICATED,
) -> dict[str, object]:
    return _compare_payload(P.DEMO_ORDERS, P.SEED, kind, days)


@router.post("/simulate")
def simulate(body: SimulateIn) -> dict[str, object]:
    result = _compare_payload(body.orders, body.seed, body.kind, body.days, with_sensitivity=True)
    result["params"] = {"orders": body.orders, "seed": body.seed, "kind": body.kind, "days": body.days}
    return result


@router.get("/threshold")
def threshold() -> dict[str, object]:
    """График порога: себестоимость заказа от числа заказов в рейсе."""
    threshold_orders = breakeven_orders(["S"], P.TRIP_KIND_DEDICATED)
    points = []
    for n in sorted({*range(5, 151, 5), threshold_orders}):
        mesh = order_cost_mesh("S", P.TRIP_KIND_DEDICATED, n)
        points.append(
            {
                "orders": n,
                "mesh": float(mesh),
                "hub": float(hub_cost("S")),
                "load_um": n,
            }
        )
    return {
        "class": "S",
        "trip_kind": P.TRIP_KIND_DEDICATED,
        "trip_cost": rub(int(P.TRIP_COST_DEDICATED * 100)),
        "threshold": threshold_orders,
        "points": points,
    }
