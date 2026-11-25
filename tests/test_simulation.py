from decimal import Decimal

from core.parameters import TRIP_KIND_ALONG, TRIP_KIND_DEDICATED, ZONE_GREEN, ZONE_YELLOW
from core.simulation import FlowOrder, compare, sensitivity


def test_yellow_orders_can_only_use_along_trip():
    flow = [FlowOrder("S", 120, ZONE_YELLOW)] * 100
    assert compare(flow, TRIP_KIND_ALONG)["mesh"]["orders"] == 100
    assert compare(flow, TRIP_KIND_DEDICATED)["mesh"]["orders"] == 0


def test_trip_sensitivity_can_change_admission():
    flow = [FlowOrder("S", 120, ZONE_GREEN)] * 70
    base = compare(flow, TRIP_KIND_DEDICATED)
    assert base["mesh"]["orders"] == 0
    low = next(
        row for row in sensitivity(flow, TRIP_KIND_DEDICATED, 1)
        if row["parameter"] == "Стоимость рейса" and row["delta_pct"] == -20
    )
    assert low["cost_per_order"] == Decimal("101.43")
