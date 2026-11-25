"""Рейсы."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import Trip
from ..schemas import TripIn
from ..services import clock, idempotency
from ..services import trips as service

router = APIRouter(tags=["trips"])


@router.get("/trips")
def list_trips(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    trips = db.scalars(
        select(Trip)
        .options(joinedload(Trip.from_pvz), joinedload(Trip.to_pvz), joinedload(Trip.orders))
        .order_by(Trip.departs_at.desc())
    ).unique().all()
    return [service.trip_payload(trip) for trip in trips]


@router.post("/trips/plan", status_code=201)
def plan(
    body: TripIn,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    fp = idempotency.fingerprint("POST", "/trips/plan", body.model_dump())
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached
    at = clock.now(db)
    result = service.plan(
        db,
        from_pvz_id=body.from_pvz_id,
        to_pvz_id=body.to_pvz_id,
        kind=body.kind,
        departs_at=at + timedelta(hours=body.departs_in_hours),
    )
    idempotency.remember(db, key, fp, "trip_planned", result, at)
    db.commit()
    return result


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return service.trip_payload(service._get_trip(db, trip_id), full=True)


@router.post("/trips/{trip_id}/depart")
def depart(
    trip_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    fp = idempotency.fingerprint("POST", f"/trips/{trip_id}/depart", {})
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached
    at = clock.now(db)
    result = service.depart(db, trip_id, key, at)
    idempotency.remember(db, key, fp, "trip_departed", result, at)
    db.commit()
    return result


@router.post("/trips/{trip_id}/arrive")
def arrive(
    trip_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    fp = idempotency.fingerprint("POST", f"/trips/{trip_id}/arrive", {})
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached
    at = clock.now(db)
    result = service.arrive(db, trip_id, at)
    idempotency.remember(db, key, fp, "trip_arrived", result, at)
    db.commit()
    return result


@router.post("/trips/{trip_id}/fail")
def fail(
    trip_id: int,
    db: Session = Depends(get_db),
    key: str = Depends(idempotency.require_key),
) -> dict[str, object]:
    fp = idempotency.fingerprint("POST", f"/trips/{trip_id}/fail", {})
    cached = idempotency.replay(db, key, fp)
    if cached is not None:
        return cached
    at = clock.now(db)
    result = service.fail(db, trip_id, at)
    idempotency.remember(db, key, fp, "trip_failed", result, at)
    db.commit()
    return result
