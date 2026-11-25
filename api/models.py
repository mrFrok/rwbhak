"""Модель данных MVP. Деньги — целые копейки."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class City(Base):
    __tablename__ = "city"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class Zone(Base):
    """Коридор между городами: зона плотности и расстояние."""

    __tablename__ = "zone"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_city_id: Mapped[int] = mapped_column(ForeignKey("city.id"))
    to_city_id: Mapped[int] = mapped_column(ForeignKey("city.id"))
    distance_km: Mapped[int] = mapped_column(Integer)
    lambda_per_day: Mapped[int] = mapped_column(Integer)
    class_: Mapped[str] = mapped_column("class", String(10), default="GREEN")

    from_city: Mapped[City] = relationship(foreign_keys=[from_city_id])
    to_city: Mapped[City] = relationship(foreign_keys=[to_city_id])


class Pvz(Base):
    __tablename__ = "pvz"
    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("city.id"))
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(200), default="")
    capacity_um: Mapped[int] = mapped_column(Integer, default=200)
    reserve_pct: Mapped[int] = mapped_column(Integer, default=15)
    quiet_windows: Mapped[str] = mapped_column(String(120), default="09:00-13:00, 20:00-22:00")

    city: Mapped[City] = relationship()

    @property
    def available_um(self) -> int:
        return int(self.capacity_um * (100 - self.reserve_pct) / 100)


class Seller(Base):
    __tablename__ = "seller"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str] = mapped_column(String(120), default="")


class Sku(Base):
    __tablename__ = "sku"
    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"))
    name: Mapped[str] = mapped_column(String(160))
    price_kop: Mapped[int] = mapped_column(Integer)
    unit_cost_kop: Mapped[int] = mapped_column(Integer)
    size_class: Mapped[str] = mapped_column(String(10))
    um: Mapped[int] = mapped_column(Integer)
    special: Mapped[bool] = mapped_column(Boolean, default=False)

    seller: Mapped[Seller] = relationship()


class Batch(Base):
    __tablename__ = "batch"
    __table_args__ = (CheckConstraint("qty_free >= 0 AND qty_free <= qty", name="ck_batch_inventory"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("sku.id"))
    pvz_id: Mapped[int] = mapped_column(ForeignKey("pvz.id"))
    qty: Mapped[int] = mapped_column(Integer)
    qty_free: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    declared_class: Mapped[str] = mapped_column(String(10))
    actual_class: Mapped[str] = mapped_column(String(10))

    sku: Mapped[Sku] = relationship()
    pvz: Mapped[Pvz] = relationship()

    @property
    def used_um(self) -> int:
        return (self.qty - self.qty_free) * self.sku.um

    @property
    def free_um(self) -> int:
        return self.qty_free * self.sku.um


class Trip(Base):
    __tablename__ = "trip"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_pvz_id: Mapped[int] = mapped_column(ForeignKey("pvz.id"))
    to_pvz_id: Mapped[int] = mapped_column(ForeignKey("pvz.id"))
    kind: Mapped[str] = mapped_column(String(20), default="DEDICATED")
    departs_at: Mapped[datetime] = mapped_column(DateTime)
    cost_kop: Mapped[int] = mapped_column(Integer)
    capacity_um: Mapped[int] = mapped_column(Integer, default=300)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")

    from_pvz: Mapped[Pvz] = relationship(foreign_keys=[from_pvz_id])
    to_pvz: Mapped[Pvz] = relationship(foreign_keys=[to_pvz_id])
    orders: Mapped[list[Order]] = relationship(back_populates="trip")

    @property
    def used_um(self) -> int:
        return sum(order.um for order in self.orders if order.status not in ("CANCELLED",))

    @property
    def free_um(self) -> int:
        return self.capacity_um - self.used_um


class Order(Base):
    __tablename__ = "order"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("sku.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.id"))
    source_pvz_id: Mapped[int] = mapped_column(ForeignKey("pvz.id"))
    buyer_pvz_id: Mapped[int] = mapped_column(ForeignKey("pvz.id"))
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trip.id"), nullable=True)
    um: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="CREATED")
    mode: Mapped[str] = mapped_column(String(2), default="C")
    eta_mesh_h: Mapped[float | None] = mapped_column(nullable=True)
    eta_hub_h: Mapped[int] = mapped_column(Integer, default=48)
    cost_mesh_kop: Mapped[int] = mapped_column(Integer, default=0)
    cost_hub_kop: Mapped[int] = mapped_column(Integer, default=0)
    decision_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sku: Mapped[Sku] = relationship()
    batch: Mapped[Batch] = relationship()
    seller: Mapped[Seller] = relationship()
    source_pvz: Mapped[Pvz] = relationship(foreign_keys=[source_pvz_id])
    buyer_pvz: Mapped[Pvz] = relationship(foreign_keys=[buyer_pvz_id])
    trip: Mapped[Trip | None] = relationship(back_populates="orders")


class LedgerEntry(Base):
    __tablename__ = "ledger_entry"
    __table_args__ = (UniqueConstraint("idempotency_key", "line_no", "entry_type", name="uq_ledger_line"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("order.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(40))
    amount_kop: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    line_no: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class EventLog(Base):
    __tablename__ = "event_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Clock(Base):
    __tablename__ = "clock"
    id: Mapped[int] = mapped_column(primary_key=True)
    now: Mapped[datetime] = mapped_column(DateTime)


class Alert(Base):
    __tablename__ = "alert"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    type: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)
