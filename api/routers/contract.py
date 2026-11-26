"""Внешний контракт стадии 2. Прежние маршруты /api остаются для старого UI."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session


from ..db import get_db
from ..errors import DomainError
from ..models import EventLog, LedgerEntry, Order
from ..money import plain, rub
from ..schemas import BatchIn, OrderIn, TimeIn
from ..services import clock, idempotency
from ..services import orders as order_service
from ..services import trips as trip_service
from . import catalog, orders, stock, trips

RESULTS_PATH = Path(__file__).resolve().parent.parent.parent / "reports" / "results.json"

router = APIRouter()


class Assumption(BaseModel):
    id: str
    name: str
    value: float | int | bool | str | list[int]
    unit: str
    note: str
    kind: str = "допущение команды"


class ClockView(BaseModel):
    now_h: float
    now_iso: str


class ReceiveIn(BatchIn):
    model_config = ConfigDict(extra="forbid")
    seller_id: int = Field(gt=0)


class Posting(BaseModel):
    account: str
    type: str
    amount: float


class Receipt(BaseModel):
    batch_id: int
    status: Literal["ACCEPTED"] = "ACCEPTED"
    qty: int
    um_occupied: int
    free_um_after: int
    ledger: list[Posting]


class OrderCreateIn(OrderIn):
    model_config = ConfigDict(extra="forbid")
    qty: Literal[1] = 1


class FilterView(BaseModel):
    name: str
    ok: bool
    value: str


class OrderView(BaseModel):
    order_id: int
    status: str
    mode: Literal["A", "B", "C"]
    eta_mesh_h: float | None
    eta_hub_h: float
    cost_mesh: float
    cost_hub: float
    filters: list[FilterView]


class StatusPoint(BaseModel):
    status: str
    t_h: float


class OrderDetail(OrderView):
    trip_id: int | None
    timeline: list[StatusPoint]


class OrderAction(BaseModel):
    order_id: int
    status: str
    ledger: list[Posting]


class LedgerLine(Posting):
    id: int
    order_id: int
    idempotency_key: str


def _model_hour(at: datetime) -> float:
    return (at - clock.DEFAULT_START).total_seconds() / 3600


def _postings(db: Session, *, key: str | None = None, order_id: int | None = None):
    query = select(LedgerEntry).order_by(LedgerEntry.id)
    if key is not None:
        query = query.where(LedgerEntry.idempotency_key == key)
    if order_id is not None:
        query = query.where(LedgerEntry.order_id == order_id)
    return db.scalars(query).all()


def _posting(entry: LedgerEntry) -> Posting:
    return Posting(
        account=entry.account,
        type={"ACCEPTANCE": "RECEIVE", "PICKING": "ASSEMBLE"}.get(entry.entry_type, entry.entry_type),
        amount=rub(entry.amount_kop),
    )


def _order_view(payload: dict) -> OrderView:
    filters = [
        FilterView(
            name=item["code"], ok=item["ok"], value=f'{item["actual"]}; условие: {item["limit"]}',
        )
        for item in payload["decision"].get("filters", [])
    ]
    return OrderView(
        order_id=payload["id"], status=payload["status"], mode=payload["mode"],
        eta_mesh_h=payload["eta_mesh_h"], eta_hub_h=payload["eta_hub_h"],
        cost_mesh=payload["cost_mesh"], cost_hub=payload["cost_hub"], filters=filters,
    )


def _timeline(db: Session, order: Order) -> list[StatusPoint]:
    events = db.scalars(select(EventLog).where(
        EventLog.event_type.like("orders%") | EventLog.event_type.in_(("trip_departed", "trip_arrived")),
    ).order_by(EventLog.created_at, EventLog.id))
    points: list[tuple[datetime, str]] = []
    for event in events:
        response = event.response_json
        if event.event_type.startswith("orders"):
            records = [response]
        else:
            records = response.get("order_list", [])
        points.extend((event.created_at, row["status"]) for row in records if row.get("id") == order.id)
    baseline = "ROUTED_HUB" if order.mode == "C" else "RESERVED"
    if baseline not in {status for _, status in points}:
        points.insert(0, (order.created_at, baseline))
    for at, status in ((order.picked_at, "PICKED"), (order.issued_at, "ISSUED")):
        if at is not None and (at, status) not in points:
            points.append((at, status))
    points.sort(key=lambda point: point[0])
    return [StatusPoint(status=status, t_h=_model_hour(at)) for at, status in points]


@router.get("/params", tags=["contract: catalog"])
def assumptions() -> list[Assumption]:
    from analytic.parameters import registry

    return [Assumption(**row) for row in registry()]


router.add_api_route("/pvz", catalog.list_pvz, methods=["GET"], tags=["contract: catalog"])
router.add_api_route("/skus", catalog.list_skus, methods=["GET"], tags=["contract: catalog"])
router.add_api_route("/sellers", catalog.list_sellers, methods=["GET"], tags=["contract: catalog"])


@router.post("/time/advance", tags=["contract: catalog"])
def advance_time(
    body: TimeIn, db: Session = Depends(get_db), key: str = Depends(idempotency.require_key),
) -> ClockView:
    result = catalog.advance_time(body, db, key)
    return ClockView(now_h=_model_hour(datetime.fromisoformat(result["now"])), now_iso=result["now"])


@router.post("/batches", status_code=201, tags=["contract: stock"])
def receive_batch(
    body: ReceiveIn, db: Session = Depends(get_db), key: str = Depends(idempotency.require_key),
) -> Receipt:
    result = stock.receive_batch(body, db, key)
    return Receipt(
        batch_id=result["id"], qty=result["qty"], um_occupied=result["um_total"],
        free_um_after=result["space_free_after_um"],
        ledger=[_posting(row) for row in _postings(db, key=key)],
    )


@router.get("/pvz/{pvz_id}/stock", tags=["contract: stock"])
def pvz_stock(pvz_id: int, db: Session = Depends(get_db)) -> dict:
    result = order_service.pvz_stock(db, pvz_id)
    at = clock.now(db)
    alerts = [
        {"batch_id": item["batch_id"], "type": item["type"], "days_stored": item["age_days"]}
        for item in stock.alerts(pvz_id, db)
    ]
    alerts_by_batch = {item["batch_id"]: item["type"] for item in alerts}
    batches = [
        {
            "batch_id": row["id"], "sku_id": row["sku_id"], "seller_id": row["seller_id"],
            "size_class": row["size_class"], "um": row["um"], "qty": row["qty"], "qty_free": row["qty_free"],
            "days_stored": max(0, (at - datetime.fromisoformat(row["received_at"])).days),
            "alert": alerts_by_batch.get(row["id"]),
        }
        for row in result["batches"]
    ]
    available = result["pvz"]["available_um"]
    occupied = result["used_um"] + result["incoming_um"]
    return {
        "pvz_id": pvz_id, "capacity_um": result["pvz"]["capacity_um"], "available_um": available,
        "occupied_um": occupied, "free_um": result["space_free_um"],
        "load_pct": round(occupied / available * 100, 1) if available else 0,
        "batches": batches, "alerts": alerts,
    }


@router.get("/analytics/pvz/{pvz_id}", tags=["contract: analytics"])
def pvz_analytics_report(
    pvz_id: int, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
) -> dict:
    from ..services.analytics import pvz_analytics

    legacy = pvz_analytics(db, pvz_id)
    revenue = legacy["revenue"]
    contribution = legacy["contribution"]
    by_day = []
    for index, row in enumerate(legacy["days"], 1):
        share = row["revenue"] / revenue if revenue else 0.0
        by_day.append(
            {"day": index, "revenue": row["revenue"], "contribution": round(contribution * share, 2)}
        )
    return {
        "pvz_id": pvz_id,
        "period_days": days,
        "revenue": revenue,
        "costs": {"labor": legacy["labor"], "space": legacy["overhead"]},
        "contribution": contribution,
        "contribution_per_um_day": legacy["contribution_per_um_day"],
        "load_pct": legacy["stock"]["load_pct"],
        "by_day": by_day,
        "before_after": {"before": 0.0, "after": contribution},
    }


@router.get("/analytics/seller/{seller_id}", tags=["contract: analytics"])
def seller_analytics_report(
    seller_id: int, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
) -> dict:
    """Маржа продавца строго по формуле контракта API."""
    from core.economics import seller_logistics_fee, seller_storage_fee

    from ..models import Seller
    from ..services.analytics import seller_analytics as seller_analytics_legacy

    seller = db.get(Seller, seller_id)
    if seller is None:
        raise DomainError(404, "NOT_FOUND", "Продавец не найден")
    legacy = seller_analytics_legacy(db, seller_id, clock.now(db))

    orders = []
    for row in legacy["orders"]:
        storage = seller_storage_fee(row["size_class"], row["storage_days"])
        logistics = seller_logistics_fee(row["size_class"])
        return_cost = 50.0 if row["status"] == "RETURNED" else 0.0
        margin = row["price"] - row["unit_cost"] - row["commission"] - float(logistics) - float(storage) - return_cost
        orders.append(
            {
                "order_id": row["order_id"],
                "price": row["price"],
                "unit_cost": row["unit_cost"],
                "commission": row["commission"],
                "logistics_fee": float(logistics),
                "storage_fee": float(storage),
                "return_cost": return_cost,
                "margin": round(margin, 2),
            }
        )
    revenue = sum(row["price"] for row in orders)
    total_margin = sum(row["margin"] for row in orders)
    storage_total = sum(row["storage_fee"] for row in orders)
    avg_days = (
        sum(row["storage_days"] for row in legacy["orders"]) / len(legacy["orders"])
        if legacy["orders"] else 0.0
    )
    return {
        "seller_id": seller_id,
        "orders": orders,
        "totals": {
            "revenue": round(revenue, 2),
            "margin": round(total_margin, 2),
            "storage_fee": round(storage_total, 2),
            "avg_storage_days": round(avg_days, 2),
        },
    }


@router.post("/orders", status_code=201, tags=["contract: orders"])
def create_order(
    body: OrderCreateIn, db: Session = Depends(get_db), key: str = Depends(idempotency.require_key),
) -> OrderView:
    # qty=1 is validated by the public schema; the legacy service reserves one unit.
    payload = OrderIn.model_validate(body.model_dump(exclude={"qty"}))
    return _order_view(orders.create_order(payload, db, key))


@router.get("/orders/{order_id}", tags=["contract: orders"])
def get_order(order_id: int, db: Session = Depends(get_db)) -> OrderDetail:
    order = order_service._get_order(db, order_id)
    view = _order_view(order_service.order_payload(order))
    return OrderDetail(**view.model_dump(), trip_id=order.trip_id, timeline=_timeline(db, order))


@router.post("/orders/{order_id}/{action}", tags=["contract: orders"])
def order_action(
    order_id: int, action: Literal["pick", "issue", "return"],
    db: Session = Depends(get_db), key: str = Depends(idempotency.require_key),
) -> OrderAction:
    handler = {"pick": orders.pick, "issue": orders.issue, "return": orders.return_request}[action]
    return _order_action_view(db, handler(order_id, db, key), key)


@router.post("/orders/{order_id}/return/{action}", tags=["contract: orders"])
def return_action(
    order_id: int, action: Literal["transit", "accept"],
    db: Session = Depends(get_db), key: str = Depends(idempotency.require_key),
) -> OrderAction:
    handler = {"transit": orders.return_transit, "accept": orders.return_accept}[action]
    return _order_action_view(db, handler(order_id, db, key), key)


def _order_action_view(db: Session, result: dict, key: str) -> OrderAction:
    return OrderAction(
        order_id=result["id"], status=result["status"],
        ledger=[_posting(row) for row in _postings(db, key=key, order_id=result["id"])],
    )


@router.get("/ledger", tags=["contract: orders"])
def order_ledger(order_id: int = Query(gt=0), db: Session = Depends(get_db)) -> list[LedgerLine]:
    order_service._get_order(db, order_id)
    return [
        LedgerLine(**_posting(row).model_dump(), id=row.id, order_id=order_id, idempotency_key=row.idempotency_key)
        for row in _postings(db, order_id=order_id)
    ]


router.add_api_route("/trips/{trip_id}/depart", trips.depart, methods=["POST"], tags=["contract: trips"])
router.add_api_route("/trips/{trip_id}/arrive", trips.arrive, methods=["POST"], tags=["contract: trips"])
router.add_api_route("/trips/{trip_id}/fail", trips.fail, methods=["POST"], tags=["contract: trips"])


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    departure_h: float = Field(ge=0, le=24 * 30)


class ReroutedOrder(BaseModel):
    order_id: int
    reason: Literal["TRIP_NOT_PAYING", "TIME", "CAPACITY", "SIZE"]
    mode: Literal["C"] = "C"


class PlannedTrip(BaseModel):
    trip_id: int
    kind: Literal["DEDICATED", "ALONG"]
    order_ids: list[int]
    um: int
    cost: float
    saving: float
    net: float


class PlanResult(BaseModel):
    trips: list[PlannedTrip]
    rerouted: list[ReroutedOrder]


@router.post("/trips/plan", tags=["contract: trips"])
def plan_trips(
    body: PlanIn, db: Session = Depends(get_db), key: str = Depends(idempotency.require_key),
) -> PlanResult:
    fp = idempotency.fingerprint("POST", "/trips/plan", body.model_dump())
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return PlanResult(**cached)
    now_value = clock.now(db)
    departs_at = now_value + timedelta(hours=body.departure_h)
    result = trip_service.plan(db, departs_at=departs_at)
    idempotency.remember(db, key, fp, "trips_planned", result, now_value)
    db.commit()
    return PlanResult(**result)


def _model_results(section: str):
    if not RESULTS_PATH.is_file():
        raise DomainError(
            503, "MODEL_UNAVAILABLE",
            "Результаты модели ещё не опубликованы: ожидается reports/results.json",
            section=section,
        )
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    if section not in data:
        raise DomainError(503, "MODEL_UNAVAILABLE", f"В results.json нет раздела {section}", section=section)
    return data[section]


@router.get("/compare", tags=["contract: model"])
def compare() -> object:
    return _model_results("comparison")


@router.get("/model/sensitivity", tags=["contract: model"])
def sensitivity() -> object:
    return _model_results("tornado_marketplace")


@router.get("/model/scenarios", tags=["contract: model"])
def scenarios() -> object:
    return _model_results("scenarios")


@router.get("/model/map", tags=["contract: model"])
def mutual_map() -> object:
    return _model_results("mutual_map")


class SimulateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: dict[str, float | int | bool] = Field(default_factory=dict)


@router.post("/simulate", tags=["contract: model"])
def simulate(body: SimulateIn) -> dict:
    from dataclasses import fields, replace

    from analytic.analysis import run_avg
    from analytic.parameters import Params

    base = Params()
    known = {item.name for item in fields(Params)}
    unknown = sorted(key for key in body.overrides if key not in known)
    if unknown:
        raise DomainError(
            422, "VALIDATION_ERROR", "Неизвестные параметры пересчёта",
            fields=unknown, allowed=sorted(known),
        )
    converted = {}
    for key, value in body.overrides.items():
        current = getattr(base, key)
        if isinstance(current, bool):
            converted[key] = bool(value)
        elif isinstance(current, tuple):
            converted[key] = tuple(value) if isinstance(value, (list, tuple)) else current
        elif isinstance(current, int):
            converted[key] = int(value)
        else:
            converted[key] = float(value)
    result = run_avg(replace(base, **converted))
    return plain(result)


# Алиасы под префиксом /api: наш UI ходит только по /api/*, а контракт живёт в корне.
router.add_api_route("/api/model/compare", compare, methods=["GET"], tags=["contract: model"])
router.add_api_route("/api/model/scenarios", scenarios, methods=["GET"], tags=["contract: model"])
router.add_api_route("/api/model/sensitivity", sensitivity, methods=["GET"], tags=["contract: model"])
router.add_api_route("/api/model/map", mutual_map, methods=["GET"], tags=["contract: model"])
router.add_api_route("/api/model/params", assumptions, methods=["GET"], tags=["contract: model"])
router.add_api_route("/api/model/simulate", simulate, methods=["POST"], tags=["contract: model"])
