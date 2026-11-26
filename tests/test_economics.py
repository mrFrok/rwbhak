"""Контрольные числа из docs/mvp-spec.md (раздел 9)."""

from decimal import Decimal

from core import economics as E
from core import parameters as P

D = Decimal
S_ONLY = ["S"]
MIXED = ["S"] * 7 + ["M"] * 3


def test_hub_cost_matches_document():
    assert E.hub_cost("S") == D("109.00")
    assert E.hub_cost("M") == D("172.00")
    assert E.hub_cost("L") == D("304.50")


def test_mesh_cost_without_trip_matches_document():
    assert E.mesh_variable_cost("S") == D("50.00")
    assert E.mesh_variable_cost("M") == D("80.30")
    assert E.mesh_variable_cost("L") == D("145.80")


def test_saving_per_order():
    assert E.mesh_saving("S") == D("59.00")
    assert E.mesh_saving("M") == D("91.70")
    assert E.mesh_saving("L") == D("158.70")


def test_saving_per_um_falls_with_size():
    assert E.saving_per_um("S") == D("59.00")
    assert round(float(E.saving_per_um("M"))) == 31
    assert round(float(E.saving_per_um("L"))) == 20


def test_breakeven_thresholds():
    assert E.breakeven_orders(S_ONLY, P.TRIP_KIND_DEDICATED) == 77
    assert E.breakeven_orders(S_ONLY, P.TRIP_KIND_ALONG) == 13
    assert E.breakeven_orders(MIXED, P.TRIP_KIND_DEDICATED) == 66
    assert E.breakeven_orders(MIXED, P.TRIP_KIND_ALONG) == 11


def test_trip_cost_per_order_table():
    assert E.order_cost_mesh("S", P.TRIP_KIND_DEDICATED, 30) == D("200.00")
    assert E.order_cost_mesh("S", P.TRIP_KIND_DEDICATED, 60) == D("125.00")
    assert E.order_cost_mesh("S", P.TRIP_KIND_DEDICATED, 77) == D("108.44")
    assert E.order_cost_mesh("S", P.TRIP_KIND_DEDICATED, 100) == D("95.00")
    assert E.order_cost_mesh("S", P.TRIP_KIND_DEDICATED, 150) == D("80.00")


def test_pvz_revenue_and_contribution():
    assert E.pvz_revenue("S") == D("40.00")
    assert E.pvz_revenue("M") == D("67.30")
    assert E.pvz_revenue("L") == D("127.80")

    assert E.pvz_contribution("S") == D("15.00")
    assert E.pvz_contribution("M") == D("25.63")
    assert E.pvz_contribution("L") == D("47.80")


def test_mode_a_costs_both_bonuses():
    # v0.3: режим A платит и бонус SLA, и бонус «со своей полки»: 40 + 4 + 6 + 2
    assert E.mesh_variable_cost("S", shelf_sale=True) == D("52.00")
    assert E.mesh_variable_cost("M", shelf_sale=True) == D("83.67")
    assert E.mesh_saving("S", shelf_sale=True) == D("57.00")
    assert E.mesh_saving("M", shelf_sale=True) == D("88.33")


def test_seller_margin_uses_agreed_logistics_tariff():
    # чек 1500 ₽, себестоимость 600 ₽, класс S, продажа на 3-й день
    breakdown = E.seller_margin("S", D("1500"), D("600"), days=3)
    assert breakdown["commission"] == D("225.00")
    assert breakdown["acquiring"] == D("22.50")
    assert breakdown["logistics"] == D("60.00")
    assert breakdown["storage"] == D("0")
    assert breakdown["returns"] == D("5.50")
    assert breakdown["tax"] == D("90.00")
    assert breakdown["margin"] == D("497.00")
    assert E.seller_logistics_fee("M") == D("90.00")


def test_seller_margin_sixth_day_storage():
    breakdown = E.seller_margin("S", D("1500"), D("600"), days=6)
    assert breakdown["storage"] == D("9.00")
    assert breakdown["margin"] == D("488.00")


def test_pilot_economics_v03():
    assert E.mix_avg_saving() == D("68.81")
    assert E.pilot_breakeven_orders(P.TRIP_KIND_DEDICATED) == 116
    assert E.pilot_breakeven_orders(P.TRIP_KIND_ALONG) == 62
    summary = E.pilot_summary()
    assert E.pilot_month_effect(116, P.TRIP_KIND_DEDICATED) >= P.PILOT_FIXED_COST_MONTH
    assert E.pilot_month_effect(115, P.TRIP_KIND_DEDICATED) < P.PILOT_FIXED_COST_MONTH
    assert summary["breakeven_along"] == 62


def test_long_storage_14_days():
    # продавец: дни 4-7 по 3 ₽, дни 8-14 по 6 ₽ за УМ
    assert E.seller_storage_fee("S", 14) == D("54.00")
    # ПВЗ получает с первого дня: 14 дней × 3 ₽ × 1 УМ
    assert E.pvz_storage_payout("S", 14) == D("42.00")


def test_free_storage_first_three_days():
    assert E.seller_storage_fee("S", 3) == D("0")
    assert E.pvz_storage_payout("S", 3) == D("9.00")


def test_registry_is_complete_enough():
    codes = {item["code"] for item in P.registry()}
    assert {"hub.s", "trip.dedicated", "pvz.storage"} <= codes
    assert all("source" in item for item in P.registry())
