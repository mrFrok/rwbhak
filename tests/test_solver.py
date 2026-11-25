"""Решатель: режимы A/B/C и причины отказа."""

from decimal import Decimal

from core import parameters as P
from core.solver import OrderRequest, TripLoad, decide


def trip(existing: int, kind: str = P.TRIP_KIND_DEDICATED, free_um: int = 300, wait: float = 30.0) -> TripLoad:
    return TripLoad(kind=kind, free_um=free_um, existing_sizes=("S",) * existing, wait_hours=wait)


def test_mode_b_when_all_filters_pass():
    result = decide(OrderRequest(size_class="S", trip=trip(76)))
    assert result["mode"] == "B"
    assert result["trip_orders"] == 77
    assert result["cost_hub"] == Decimal("109.00")
    assert all(f["ok"] for f in result["filters"])


def test_mode_b_cost_at_full_trip():
    # 99 уже в рейсе → 100-й заказ получает себестоимость 95 ₽
    result = decide(OrderRequest(size_class="S", trip=trip(99)))
    assert result["mode"] == "B"
    assert result["cost_mesh"] == Decimal("95.00")
    assert result["saving"] == Decimal("14.00")


def test_mode_c_when_trip_does_not_pay_off():
    result = decide(OrderRequest(size_class="S", trip=trip(60)))
    assert result["mode"] == "C"
    assert "trip" in result["blocked_by"]


def test_mode_c_for_large_size():
    result = decide(OrderRequest(size_class="L", trip=trip(99)))
    assert result["mode"] == "C"
    assert "size" in result["blocked_by"]


def test_mode_c_for_red_zone():
    result = decide(OrderRequest(size_class="S", zone_class=P.ZONE_RED, trip=trip(99)))
    assert result["mode"] == "C"
    assert "zone" in result["blocked_by"]


def test_yellow_zone_only_with_along_trip():
    dedicated = decide(OrderRequest(size_class="S", zone_class=P.ZONE_YELLOW, trip=trip(99)))
    along = decide(
        OrderRequest(size_class="S", zone_class=P.ZONE_YELLOW, trip=trip(99, kind=P.TRIP_KIND_ALONG))
    )
    assert dedicated["mode"] == "C"
    assert along["mode"] == "B"


def test_mode_c_when_eta_worse_than_hub():
    result = decide(OrderRequest(size_class="S", trip=trip(99, wait=44)))
    assert result["mode"] == "C"
    assert "time" in result["blocked_by"]


def test_mode_c_when_no_space():
    result = decide(OrderRequest(size_class="M", trip=trip(99, free_um=2)))
    assert result["mode"] == "C"
    assert "space" in result["blocked_by"]


def test_mode_c_for_far_order():
    result = decide(OrderRequest(size_class="S", distance_km=900, trip=trip(99)))
    assert result["mode"] == "C"
    assert "distance" in result["blocked_by"]


def test_mode_a_when_stock_in_buyer_pvz():
    result = decide(OrderRequest(size_class="S", same_pvz_stock=2))
    assert result["mode"] == "A"
    assert result["eta_mesh_h"] == P.MESH_ETA_SHELF_H
    # v0.3: 52 ₽ — SLA-бонус и бонус полки суммируются
    assert result["cost_mesh"] == Decimal("52.00")
    assert result["saving"] == Decimal("57.00")


def test_special_goods_always_hub():
    result = decide(OrderRequest(size_class="S", special=True, trip=trip(99)))
    assert result["mode"] == "C"
    assert "size" in result["blocked_by"]
