"""Pydantic-схемы запросов."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BatchIn(BaseModel):
    seller_id: int | None = None
    sku_id: int
    pvz_id: int
    qty: int = Field(default=1, gt=0, le=500)
    declared_class: str = "S"
    actual_class: str | None = None


class OrderIn(BaseModel):
    sku_id: int
    buyer_pvz_id: int
    source_pvz_id: int | None = None
    batch_id: int | None = None


class TripIn(BaseModel):
    from_pvz_id: int
    to_pvz_id: int
    kind: str = Field(default="DEDICATED", pattern="^(DEDICATED|ALONG)$")
    departs_in_hours: int = Field(default=24, ge=0, le=240)


class TimeIn(BaseModel):
    days: int = Field(default=0, ge=0, le=365)
    hours: int = Field(default=0, ge=0, le=365 * 24)

    @property
    def empty(self) -> bool:
        return self.days == 0 and self.hours == 0


class SimulateIn(BaseModel):
    orders: int = Field(default=3000, ge=10, le=10000)
    seed: int = 42
    kind: str = Field(default="DEDICATED", pattern="^(DEDICATED|ALONG)$")
    days: int = Field(default=30, ge=1, le=365)
