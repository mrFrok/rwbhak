from dataclasses import replace

from analytic.parameters import Params
from analytic.simulation import simulate, generate_orders, classify_zone
from analytic import economics as E

p = Params()


def test_reproducible_with_seed():
    assert simulate(p, 1)["saving_month"] == simulate(p, 1)["saving_month"]
    a = generate_orders(p, 7)
    b = generate_orders(p, 7)
    assert [(o.t, o.size, o.nearby) for o in a] == [(o.t, o.size, o.nearby) for o in b]


def test_same_orders_for_both_schemes():
    r = simulate(p, 1)
    assert r["orders"] > 0
    assert r["base_total"] > 0


def test_funnel_sums_to_orders():
    r = simulate(p, 1)
    f = r["funnel"]
    total = sum(f[k] for k in ("distance", "size", "zone", "capacity", "time", "trip_cost",
                               "unprofitable", "mode_A", "mode_B_dedicated", "mode_B_along"))
    assert total == r["orders"]


def test_large_sizes_never_go_mesh():
    r = simulate(replace(p, share_S=0.0, share_M=0.0, share_L=0.6, share_KGT=0.4), 1)
    assert r["mesh_orders"] == 0
    assert r["saving_month"] == 0


def test_no_mesh_when_all_orders_far():
    r = simulate(replace(p, nearby_share=0.0), 1)
    assert r["mesh_orders"] == 0


def test_low_density_is_red_zone_and_hub_only():
    r = simulate(replace(p, orders_per_day=3), 1)
    assert r["zone"] == "RED"
    assert r["mesh_orders"] == 0


def test_time_filter_blocks_slow_mesh():
    r = simulate(replace(p, eta_hub_h=6.0), 1)    # хаб «быстрее» любого рейса
    assert r["funnel"]["mode_B_dedicated"] + r["funnel"]["mode_B_along"] == 0


def test_mesh_never_worse_than_hub_on_total_cost():
    for seed in (1, 2, 3):
        assert simulate(p, seed)["saving_month"] >= 0


def test_buyer_never_slower():
    r = simulate(p, 1)
    assert r["eta_mesh_h"] <= r["eta_base_h"]


def test_zone_thresholds_follow_breakeven():
    ms = E.mixed_saving(p)
    assert classify_zone(p, 38.0, ms) == "GREEN"
    assert classify_zone(p, 20.0, ms) == "YELLOW"
    assert classify_zone(p, 3.0, ms) == "RED"
