"""Пересборка отчёта по модели: reports/results.json и reports/model_report.md.

Запуск: `make report` (или `python -m scripts.build_report`).
Все числа считаются core/model.py и core/analysis.py — вручную ничего не правится.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from core.analysis import compare_schemes, mutual_map, scenarios, tornado
from core.model import ModelParams, metrics, run_avg, simulate

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fmt(value: object) -> str:
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ").replace(".", ",")
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return str(value)


def build() -> dict[str, object]:
    params = ModelParams()
    comparison = compare_schemes(params)
    scenario_rows = scenarios(params)
    tornado_rows = tornado(params)
    map_rows = mutual_map(params)
    base = run_avg(params)
    spread = []
    for seed in (1, 2, 3, 4, 5):
        result = metrics(params, simulate(params, seed))
        spread.append(
            {
                "seed": seed,
                "orders": result["orders"],
                "saving_month": result["saving_month"],
                "saving_pct": result["saving_pct"],
                "mesh_share": result["mesh_share"],
                "after_fixed_month": result["after_fixed_month"],
            }
        )
    return {
        "params": _plain(asdict(params)),
        "comparison": _plain(comparison),
        "scenarios": _plain(scenario_rows),
        "tornado_marketplace": _plain(tornado_rows),
        "mutual_map": _plain(map_rows),
        "funnel": _plain(base["funnel"]),
        "run_spread": _plain(spread),
        "base": _plain(base),
    }


def _report_md(data: dict[str, object]) -> str:
    comparison = data["comparison"]
    hub, dedicated, along = comparison["hub"], comparison["dedicated"], comparison["along"]
    base = data["base"]
    params = data["params"]
    lines = [
        "# Отчёт по модели: хаб против mesh на синтетических данных",
        "",
        "> Все входные числа — **допущения команды** (`core/model.py`), а не тарифы RWB.",
        "> Файл создаётся скриптом `scripts/build_report.py`; после смены допущений пересчитывается целиком.",
        "",
        "## 1. Что и на чём считали",
        "",
        "| Параметр | Значение |",
        "| --- | --- |",
        f"| Заказов в прогоне | {_fmt(base['orders'])} (≈ {_fmt(base['orders_per_day'])} в день) |",
        f"| Горизонт | {params['days']} дней, рейсы по дням {params['trip_days']} в {params['dep_hour']}:00 |",
        "| Поток | S 60% · M 27% · L 8% · КГТ 5%; ближних 85% |",
        "| Сеть | 1 коридор, 2 города (120 км), 4 ПВЗ, 1 хаб |",
        "| Сравнение | одни и те же заказы через хаб и mesh с четырьмя фильтрами |",
        "| Повторяемость | средние по 5 seed |",
        "",
        "## 2. Сравнение схем",
        "",
        "| Показатель | Хаб (база) | Mesh: только выделенные | Mesh: + попутная загрузка |",
        "| --- | ---: | ---: | ---: |",
        f"| Себестоимость заказа по потоку, ₽ | {_fmt(hub['cost_per_order'])} | {_fmt(dedicated['cost_per_order'])} | {_fmt(along['cost_per_order'])} |",
        f"| Экономия маркетплейса, ₽/мес | — | {_fmt(dedicated['saving_month'])} | {_fmt(along['saving_month'])} |",
        f"| Экономия, % к базе | — | {_fmt(dedicated['saving_pct'])}% | {_fmt(along['saving_pct'])}% |",
        f"| После постоянных расходов пилота ({_fmt(params['fixed_cost_month'])} ₽/мес) | — | {_fmt(dedicated['after_fixed_month'])} | {_fmt(along['after_fixed_month'])} |",
        f"| Доля заказов через mesh | 0% | {_fmt(dedicated['mesh_share'])}% | {_fmt(along['mesh_share'])}% |",
        f"| Срок ближнего заказа, ч | {_fmt(params['eta_hub_h'])} | {_fmt(dedicated['near_eta_h'])} | {_fmt(along['near_eta_h'])} |",
        "| Цена доставки для покупателя | без изменений | без изменений | без изменений |",
        f"| Доп. вклад ПВЗ, ₽/мес на точку | 0 | {_fmt(dedicated['pvz_contribution_month'])} | {_fmt(along['pvz_contribution_month'])} |",
        f"| Замороженный капитал продавца, ₽/мес | — | {_fmt(dedicated['capital_effect_month'])} | {_fmt(along['capital_effect_month'])} |",
        f"| Рейсов в месяц: выделенных / попутных | — | {_fmt(dedicated['trips_dedicated'])} / {_fmt(dedicated['trips_along'])} | {_fmt(along['trips_dedicated'])} / {_fmt(along['trips_along'])} |",
        "",
        "## 3. Куда уходят заказы",
        "",
        "| Причина | Доля потока, % |",
        "| --- | ---: |",
        f"| Выдача с полки (режим A) | {_fmt(base['funnel']['A'])} |",
        f"| Рейс попутный (режим B) | {_fmt(base['funnel']['ALONG'])} |",
        f"| Рейс выделенный (режим B) | {_fmt(base['funnel']['DEDICATED'])} |",
        f"| Хаб: дальний заказ | {_fmt(base['funnel']['FAR'])} |",
        f"| Хаб: габарит L / КГТ | {_fmt(base['funnel']['SIZE'])} |",
        f"| Хаб: срок mesh хуже срока хаба | {_fmt(base['funnel']['TIME'])} |",
        f"| Хаб: рейс не окупается или не хватило места | {_fmt(base['funnel']['TRIP'])} |",
        "",
        "## 4. Три сценария",
        "",
        "| Сценарий | Зона | Экономия, ₽/мес | % к базе | После пост. расходов | Вклад ПВЗ на точку | Срок, ч |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in data["scenarios"]:
        lines.append(
            f"| {row['title']} | {row['zone']} | {_fmt(row['saving_month'])} | {_fmt(row['saving_pct'])}% | "
            f"{_fmt(row['after_fixed_month'])} | {_fmt(row['pvz_contribution_month'])} | {_fmt(row['near_eta_h'])} |"
        )
    lines += [
        "",
        f"Пессимистичный: рейс +25%, затраты хаба −15%, заказов −25%, ближних −10%, ставки ПВЗ +15%, доля режима A вдвое меньше. "
        f"Оптимистичный: зеркально.",
        "",
        "## 5. Чувствительность (±25%)",
        "",
        "| Параметр | −25%, ₽/мес | +25%, ₽/мес | Размах |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in data["tornado_marketplace"]["rows"]:
        lines.append(
            f"| {row['parameter']} | {_fmt(row['minus'])} | {_fmt(row['plus'])} | {_fmt(row['range'])} |"
        )
    lines += [
        "",
        f"База: {_fmt(data['tornado_marketplace']['base_saving_month'])} ₽/мес.",
        "",
        "## 6. Зона взаимной выгоды",
        "",
        f"Сетка {len(data['mutual_map']['orders_grid'])} × {len(data['mutual_map']['fee_grid'])}: "
        f"{data['mutual_map']['mutual_cells']} ячеек «выигрывают все», "
        f"из них {data['mutual_map']['covered_cells']} покрывают постоянные расходы пилота.",
        "Ось X — ставки ПВЗ относительно базовых, ось Y — заказов в день по коридору.",
        "",
        "## 7. Разброс между прогонами",
        "",
        "| Прогон (seed) | Заказов | Экономия, ₽/мес | % к базе | Доля mesh | После пост. расходов |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in data["run_spread"]:
        lines.append(
            f"| {row['seed']} | {_fmt(row['orders'])} | {_fmt(row['saving_month'])} | "
            f"{_fmt(row['saving_pct'])}% | {_fmt(row['mesh_share'])}% | {_fmt(row['after_fixed_month'])} |"
        )
    lines += [
        "",
        "## 8. Что модель не учитывает",
        "",
        "- Эффект конверсии и снижения возвратов у продавца (нет данных): выгода продавца занижена.",
        "- Бонусы и штрафы ПВЗ (+10% за срок, +5% за продажу с полки) в симуляции выключены.",
        "- Возвраты, неликвид и вечерний пик в потоке не моделируются (они в сценариях MVP).",
        "- Один коридор и статичная зона на весь период; ёмкость ПВЗ учтена агрегатно.",
        "- Стоимость хранения на хабе принята равной ставке ПВЗ (допущение).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    data = build()
    (REPORTS / "results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORTS / "model_report.md").write_text(_report_md(data), encoding="utf-8")
    base = data["base"]
    print(
        f"Отчёт готов: {base['orders']} заказов, экономия {_fmt(base['saving_month'])} ₽/мес "
        f"({_fmt(base['saving_pct'])}%), после постоянных расходов {_fmt(base['after_fixed_month'])} ₽/мес"
    )
    print("reports/results.json и reports/model_report.md обновлены")


if __name__ == "__main__":
    main()
