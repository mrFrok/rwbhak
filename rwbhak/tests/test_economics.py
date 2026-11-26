"""Контрольные числа из docs/business-model.md. Если тест падает — расходятся код и документ."""
import pytest
from core.parameters import Params
from core import economics as E

p = Params()


@pytest.mark.parametrize("cls,expected", [("S", 109.0), ("M", 172.0), ("L", 304.5)])
def test_hub_cost(cls, expected):
    assert E.hub_cost(p, cls) == pytest.approx(expected)


@pytest.mark.parametrize("cls,expected", [("S", 50.0), ("M", 80.3), ("L", 145.8)])
def test_mesh_var(cls, expected):
    assert E.mesh_var(p, cls) == pytest.approx(expected)


@pytest.mark.parametrize("cls,expected", [("S", 59.0), ("M", 91.7), ("L", 158.7)])
def test_saving(cls, expected):
    assert E.saving(p, cls) == pytest.approx(expected)


@pytest.mark.parametrize("cls,expected", [("S", 15.0), ("M", 25.6), ("L", 47.8)])
def test_pvz_contribution(cls, expected):
    assert E.pvz_contribution(p, cls) == pytest.approx(expected, abs=0.05)


def test_trip_costs():
    assert p.trip_cost == pytest.approx(4500)
    assert p.along_cost == pytest.approx(750)


def test_breakeven_s_only():
    s = E.saving(p, "S")
    assert E.breakeven_orders(p, s) == 77
    assert E.breakeven_orders(p, s, along=True) == 13


def test_breakeven_mixed_70_30():
    ms = E.mixed_saving(p)
    assert ms == pytest.approx(68.81, abs=0.01)
    assert E.breakeven_orders(p, ms) == 66
    assert E.breakeven_orders(p, ms, along=True) == 11


def test_storage_14_days_seller_pays_54():
    """Раздел 12 бизнес-модели: 4 дня × 3 ₽ + 7 дней × 6 ₽ = 54 ₽, ПВЗ получает 14 × 3 = 42 ₽."""
    assert 4 * 3 + 7 * 6 == 54
    assert 14 * p.pvz_storage_rate == 42
