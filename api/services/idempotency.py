"""Идемпотентность изменяющих запросов."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from fastapi import Header, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import EventLog


def require_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key or not 8 <= len(idempotency_key) <= 80:
        raise HTTPException(
            status_code=400,
            detail="Заголовок Idempotency-Key обязателен (от 8 до 80 символов)",
        )
    return idempotency_key


def fingerprint(method: str, path: str, payload: object) -> str:
    raw = f"{method}:{path}:{json.dumps(payload, sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def replay(db: Session, key: str, fp: str) -> dict | None:
    # В однопользовательском демо сериализуем запись: повтор запроса, место и
    # остаток всегда проверяются после завершения предыдущей команды.
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(727229)"))
    elif dialect == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    row = db.scalar(select(EventLog).where(EventLog.idempotency_key == key))
    if row is None:
        return None
    if row.fingerprint != fp:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key уже использован с другим телом запроса",
        )
    return row.response_json


def remember(db: Session, key: str, fp: str, event_type: str, response: dict, at: datetime) -> None:
    db.add(
        EventLog(
            event_type=event_type,
            idempotency_key=key,
            fingerprint=fp,
            response_json=response,
            created_at=at,
        )
    )
    db.flush()
