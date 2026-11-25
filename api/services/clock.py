"""Модельные часы: демо не зависит от реального времени."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Clock

DEFAULT_START = datetime(2026, 11, 25, 9, 0)


def _row(db: Session) -> Clock:
    row = db.get(Clock, 1)
    if row is None:
        row = Clock(id=1, now=DEFAULT_START)
        db.add(row)
        db.flush()
    return row


def now(db: Session) -> datetime:
    return _row(db).now


def advance(db: Session, days: int = 0, hours: int = 0) -> datetime:
    row = _row(db)
    row.now = row.now + timedelta(days=days, hours=hours)
    db.flush()
    return row.now
