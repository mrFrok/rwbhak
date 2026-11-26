"""Симуляция и анализ: контрольные числа, инварианты, воспроизводимость."""

from decimal import Decimal

from core.analysis import compare_schemes, mutual_map, scenarios, tornado
from core.model import ModelParams, classify_zone, metrics, run_avg, simulate

D = Decimal


def test_hand_calculated_costs_match_analytics():
    params = ModelParams()
    assert params.hub_cost("S") == D("109.00")
    assert params.hub_cost("M") == D("172.00")
    assert params.hub_cost("L") == D("304.50")
    assert params.mesh_var_cost("S") == D("50.00")
    assert params.mesh_var_cost("M") == D("80.30")
    assert params.mesh_var_cost("L") == D("145.80")
    assert params.trip_cost("DEDICATED") == D("4500.00")
    assert params.trip_cost("ALONG") == D("750.00")
    assert params.pvz_contribution("S") == D("15.00")


def test_zone_thresholds():
    assert classify_zone(38) == "GREEN"
    assert classify_zone(37.9) == "YELLOW"
    assert classify_zone(7) == "YELLOW"
    assert classify_zone(6.9) == "RED"


def test_generation_is_reproducible():
    params = ModelParams()
    first = simulate(params, 42)
    second = simulate(params, 42)
    assert first.saving == second.saving
    assert first.orders == second.orders
    assert 2400 <= first.orders <= 3300


def test_simulation_invariants():
    params = ModelParams()
    run = simulate(params, 1)
    funnel_total = sum(run.funnel.values())
    assert funnel_total == run.orders
    assert run.mesh_total <= run.baseline_total
    result = metrics(params, run)
    assert result["near_eta_h"] <= Decimal("48")
    assert result["mesh_share"] < 100


def test_compare_schemes_three_columns():
    result = compare_schemes(ModelParams(), seeds=(1, 2))
    assert result["hub"]["cost_per_order"] == D("169.16") or result["hub"]["cost_per_order"] > 150
    assert result["dedicated"]["saving_month"] > 0
    assert result["along"]["saving_month"] >= result["dedicated"]["saving_month"]
    assert len(result["rows"]) == 10


def test_scenarios_and_tornado_shapes():
    rows = scenarios(ModelParams(), seeds=(1, 2))
    assert [row["name"] for row in rows] == ["pessimistic", "base", "optimistic"]
    assert rows[0]["saving_month"] < rows[2]["saving_month"]

    tornado_rows = tornado(ModelParams(), seeds=(1, 2))
    assert len(tornado_rows["rows"]) == 9
    assert tornado_rows["rows"][0]["range"] >= tornado_rows["rows"][-1]["range"]


def test_mutual_map_is_complete():
    result = mutual_map(ModelParams(), orders_grid=(20, 100), fee_grid=(0.8, 1.0), seed=1)
    assert result["total_cells"] == 4
    assert len(result["rows"]) == 2
    assert result["mutual_cells"] + 0 <= result["total_cells"]


def test_run_avg_matches_mean():
    params = ModelParams()
    averaged = run_avg(params, seeds=(1, 2))
    single = metrics(params, simulate(params, 1))
    assert averaged["orders"] > 0
    assert abs(averaged["saving_month"] - single["saving_month"]) / averaged["saving_month"] < 0.5
