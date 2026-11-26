"""Пересчитывает модель и собирает reports/: графики, results.json, model_report.md.

Запуск: python -m scripts.build_report
После смены допущений в core/parameters.py отчёт и графики обновятся сами.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from analytic.parameters import Params
from analytic import analysis as A

OUT = Path("reports")
IMG = OUT / "img"
IMG.mkdir(parents=True, exist_ok=True)
p = Params()
plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.25})


def money(x): return f"{x:,.0f}".replace(",", " ").replace("-", "−")


def tornado_plot(t, title, fname, unit):
    rows = list(reversed(t["rows"]))
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    base = t["base"]
    for i, r in enumerate(rows):
        lo, hi = r["low"], r["high"]
        ax.barh(i, lo - base, left=base, color="#4c78a8", label="−25%" if i == 0 else None)
        ax.barh(i, hi - base, left=base, color="#f58518", label="+25%" if i == 0 else None)
    ax.axvline(base, color="#222", lw=1.5)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["label"] for r in rows])
    ax.set_xlabel(unit)
    ax.set_title(title)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(IMG / fname)
    plt.close(fig)


# ---------- расчёты ----------
cmp_ = A.compare_schemes(p)
mesh = cmp_["mesh_with_along"]
ded = cmp_["mesh_dedicated_only"]
sc = A.scenarios(p)
tor_m = A.tornado(p, "saving_month")
tor_p = A.tornado(p, "pvz_per_pvz_month")
orders_grid = list(range(20, 161, 10))
fee_grid = [round(0.5 + 0.1 * i, 1) for i in range(13)]
grid = A.mutual_map(p, orders_grid, fee_grid)

results = {"params": {k: v for k, v in p.__dict__.items()},
           "comparison": cmp_, "scenarios": sc,
           "tornado_marketplace": tor_m, "tornado_pvz": tor_p,
           "mutual_map": {"orders_per_day": orders_grid, "pvz_fee_scale": fee_grid, "grid": grid}}
(OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

# ---------- графики ----------
tornado_plot(tor_m, "Что сильнее всего двигает экономию маркетплейса (±25%)",
             "tornado_marketplace.png", "Экономия маркетплейса, ₽/мес")
tornado_plot(tor_p, "Что сильнее всего двигает вклад ПВЗ (±25%)",
             "tornado_pvz.png", "Вклад на один ПВЗ, ₽/мес")

fig, axs = plt.subplots(1, 3, figsize=(12, 4), dpi=150)
labels = ["Хаб", "Mesh\n(выделенные)", "Mesh\n(+ попутные)"]
cols = ["#7f7f7f", "#d9534f", "#2e8b57"]
axs[0].bar(labels, [mesh["base_per_order"], ded["mesh_per_order"], mesh["mesh_per_order"]], color=cols)
axs[0].set_title("Себестоимость заказа по потоку, ₽")
axs[1].bar(labels, [mesh["eta_base_h"], ded["eta_mesh_h"], mesh["eta_mesh_h"]], color=cols)
axs[1].set_title("Срок ближнего заказа, ч")
axs[2].bar(labels, [0, ded["pvz_per_pvz_month"], mesh["pvz_per_pvz_month"]], color=cols)
axs[2].set_title("Доп. вклад ПВЗ, ₽/мес на точку")
for a in axs:
    for c in a.patches:
        a.annotate(f"{c.get_height():,.0f}".replace(",", " "), (c.get_x() + c.get_width() / 2, c.get_height()),
                   ha="center", va="bottom", fontsize=9)
fig.tight_layout(); fig.savefig(IMG / "comparison.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
names = list(sc.keys())
sav = [sc[n]["saving_month"] for n in names]
net = [sc[n]["net_after_fixed_month"] for n in names]
x = range(len(names))
ax.bar([i - 0.2 for i in x], sav, 0.4, label="Экономия", color="#2e8b57")
ax.bar([i + 0.2 for i in x], net, 0.4, label="После постоянных расходов", color="#4c78a8")
ax.axhline(0, color="#222", lw=1)
ax.set_xticks(list(x)); ax.set_xticklabels(names)
ax.set_ylabel("₽/мес"); ax.set_title("Три сценария модели"); ax.legend()
fig.tight_layout(); fig.savefig(IMG / "scenarios.png"); plt.close(fig)

cmap = ListedColormap(["#d9d9d9", "#f6d155", "#9fd49f", "#2e8b57"])
fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
ax.imshow(grid, origin="lower", aspect="auto", cmap=cmap, vmin=0, vmax=3)
ax.set_xticks(range(len(fee_grid))); ax.set_xticklabels([f"{int(f*100)}%" for f in fee_grid])
ax.set_yticks(range(len(orders_grid))); ax.set_yticklabels(orders_grid)
ax.set_xlabel("Ставки ПВЗ, % от базовых"); ax.set_ylabel("Заказов в день по коридору")
ax.set_title("Зона взаимной выгоды: плотность × ставка ПВЗ")
bi, bj = orders_grid.index(100), fee_grid.index(1.0)
ax.scatter([bj], [bi], marker="*", s=220, color="black", zorder=5)
ax.grid(False)
ax.legend(handles=[Patch(color="#d9d9d9", label="mesh не включается / не выгоден"),
                   Patch(color="#f6d155", label="ПВЗ ниже минимума"),
                   Patch(color="#9fd49f", label="выигрывают все (операционно)"),
                   Patch(color="#2e8b57", label="выигрывают все и покрыты расходы пилота")],
          loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8)
fig.tight_layout(); fig.savefig(IMG / "mutual_map.png"); plt.close(fig)

fn = mesh["funnel"]
tot = mesh["orders"]
parts = [("Выдача с полки (A)", fn["mode_A"], "#2e8b57"),
         ("Рейс: попутный (B)", fn["mode_B_along"], "#6dbb8a"),
         ("Рейс: выделенный (B)", fn["mode_B_dedicated"], "#9fd49f"),
         ("Хаб: рейс не окупается", fn["trip_cost"], "#f6d155"),
         ("Хаб: срок хуже", fn["time"], "#f0a35e"),
         ("Хаб: габарит L/КГТ", fn["size"], "#d9534f"),
         ("Хаб: дальний заказ", fn["distance"], "#7f7f7f"),
         ("Хаб: нет места", fn["capacity"], "#999999"),
         ("Хаб: зона RED", fn["zone"], "#bbbbbb")]
parts = [x for x in parts if x[1] > 0.5]
fig, ax = plt.subplots(figsize=(9, 4), dpi=150)
for i, (lbl, v, c) in enumerate(reversed(parts)):
    ax.barh(i, 100 * v / tot, color=c)
    ax.text(100 * v / tot + 0.5, i, f"{100 * v / tot:.1f}%", va="center", fontsize=9)
ax.set_yticks(range(len(parts))); ax.set_yticklabels([x[0] for x in reversed(parts)])
ax.set_xlabel("% всех заказов"); ax.set_title("Куда уходят заказы и почему")
fig.tight_layout(); fig.savefig(IMG / "funnel.png"); plt.close(fig)

# ---------- отчёт ----------
def pct(v): return f"{100 * v / tot:.1f}%"
top = tor_m["rows"][0]
top2 = tor_m["rows"][1]
zero = [r for r in tor_m["rows"] if r["swing"] < 1][0]["label"] if any(r["swing"] < 1 for r in tor_m["rows"]) else None
pess, opt = sc["Пессимистичный"], sc["Оптимистичный"]
green_cells = sum(c >= 2 for row in grid for c in row)
dark_cells = sum(c == 3 for row in grid for c in row)

md = f"""# Отчёт по модели: хаб против mesh на синтетических данных

> [!IMPORTANT]
> Все входные числа — **допущения команды** (`core/parameters.py`), а не тарифы RWB.
> Отчёт создаётся скриптом `python -m scripts.build_report`; после смены допущений он пересчитывается целиком.

## 1. Что и на чём считали

| Параметр | Значение |
| --- | --- |
| Данные | Синтетические заказы, `seed` 1–5 (усреднение), без персональных данных |
| Период | {p.days} дней, около {mesh['orders']:.0f} заказов (≈ {p.orders_per_day:.0f} в день) |
| Сеть | 1 коридор, 2 города (120 км), {p.pvz_count} ПВЗ, 1 хаб, {len(p.trip_days)} рейса в неделю |
| Состав потока | S {p.share_S:.0%} · M {p.share_M:.0%} · L {p.share_L:.0%} · КГТ {p.share_KGT:.0%}; ближних заказов {p.nearby_share:.0%} |
| Режим A | {p.shelf_hit_rate:.0%} ближних заказов лежат в ПВЗ покупателя заранее |
| Сравнение | Один и тот же набор заказов проходит базовую схему (все через хаб) и mesh с четырьмя фильтрами |

Модель сравнивает **устранимые** затраты: статьи, одинаковые в обеих схемах (выдача, упаковка, комиссия),
не входят. Дальние заказы идут через хаб в обеих схемах (магистраль — заглушка {p.trunk_stub:.0f} ₽).

## 2. Сравнение схем

| Показатель | Хаб (база) | Mesh: только выделенные рейсы | Mesh: + попутная загрузка |
| --- | ---: | ---: | ---: |
| Себестоимость заказа по потоку, ₽ | {mesh['base_per_order']:.1f} | {ded['mesh_per_order']:.1f} | {mesh['mesh_per_order']:.1f} |
| Экономия маркетплейса, ₽/мес | — | {money(ded['saving_month'])} | {money(mesh['saving_month'])} |
| Экономия, % к базе | — | {ded['saving_pct']:.1f}% | {mesh['saving_pct']:.1f}% |
| После постоянных расходов пилота ({money(p.fixed_cost_month)} ₽/мес) | — | {money(ded['net_after_fixed_month'])} | {money(mesh['net_after_fixed_month'])} |
| Доля заказов через mesh | 0% | {ded['mesh_share_pct']:.1f}% | {mesh['mesh_share_pct']:.1f}% |
| Срок ближнего заказа, ч | {mesh['eta_base_h']:.0f} | {ded['eta_mesh_h']:.1f} | {mesh['eta_mesh_h']:.1f} |
| Цена доставки для покупателя | без изменений | без изменений | без изменений |
| Доп. вклад ПВЗ, ₽/мес на точку | 0 | {money(ded['pvz_per_pvz_month'])} | {money(mesh['pvz_per_pvz_month'])} |
| Замороженный капитал продавца, ₽/мес (только эффект скорости) | — | {money(ded['seller_capital_gain_month'])} | {money(mesh['seller_capital_gain_month'])} |
| Рейсов в месяц: выделенных / попутных | — | {ded['trips_dedicated']:.0f} / 0 | {mesh['trips_dedicated']:.0f} / {mesh['trips_along']:.0f} |
| Заказов в выделенном рейсе (среднее) | — | {ded['avg_orders_per_dedicated']:.0f} | {mesh['avg_orders_per_dedicated']:.0f} |

![Сравнение](img/comparison.png)

**Читать так.** Маркетплейс экономит около {mesh['saving_pct']:.0f}% на всём потоке (на ближнем потоке
экономия выше, но он составляет лишь часть заказов). Покупатель получает ближний заказ в среднем на
{mesh['eta_base_h'] - mesh['eta_mesh_h']:.0f} ч быстрее без изменения цены. ПВЗ получает дополнительный вклад.
Продавцу по тарифам добавляется **ноль** (в первые 3 дня он платит как в базе), его выгода только в скорости:
эффект конверсии не моделируется (нет данных), поэтому оценка для продавца занижена.

## 3. Куда уходят заказы и почему

![Воронка](img/funnel.png)

| Причина | Заказов, % потока |
| --- | ---: |
| Выдача с полки (режим A) | {pct(fn['mode_A'])} |
| Рейс попутный / выделенный (режим B) | {pct(fn['mode_B_along'])} / {pct(fn['mode_B_dedicated'])} |
| Хаб: дальний заказ | {pct(fn['distance'])} |
| Хаб: габарит L / КГТ | {pct(fn['size'])} |
| Хаб: срок mesh хуже срока хаба | {pct(fn['time'])} |
| Хаб: рейс не окупается | {pct(fn['trip_cost'])} |

Фильтры работают как задумано: примерно половина потока остаётся на хабе, потому что для неё mesh
не выгоден. Именно это показывает границы применимости схемы.

## 4. Три сценария

| Сценарий | Зона | Экономия, ₽/мес | % к базе | После пост. расходов | Вклад ПВЗ на точку | Срок, ч |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
""" + "\n".join(f"| {n} | {v['zone']} | {money(v['saving_month'])} | {v['saving_pct']:.1f}% | "
                f"{money(v['net_after_fixed_month'])} | {money(v['pvz_per_pvz_month'])} | {v['eta_mesh_h']:.1f} |"
                for n, v in sc.items()) + f"""

![Сценарии](img/scenarios.png)

Пессимистичный: рейс +25%, затраты хаба −15%, заказов −25%, ближних −10%, ставки ПВЗ +15%, доля режима A вдвое меньше.
Оптимистичный: зеркально. Диапазон помогает показать, **где** схема работает, а не обещать один результат.

## 5. Чувствительность (±25%)

![Tornado: маркетплейс](img/tornado_marketplace.png)

| Параметр | −25%, ₽/мес | +25%, ₽/мес | Размах |
| --- | ---: | ---: | ---: |
""" + "\n".join(f"| {r['label']} | {money(r['low'])} | {money(r['high'])} | {money(r['swing'])} |"
                for r in tor_m["rows"]) + f"""

База: {money(tor_m['base'])} ₽/мес. Сильнее всего результат зависит от параметра «{top['label']}»
(размах {money(top['swing'])} ₽), затем «{top2['label']}» ({money(top2['swing'])} ₽).

![Tornado: ПВЗ](img/tornado_pvz.png)

""" + (f"Параметр «{zero}» на экономию маркетплейса не влияет: хранение оплачивается одинаково в обеих схемах, "
       "но он меняет вклад ПВЗ. " if zero else "") + f"""

## 6. Зона взаимной выгоды

![Карта](img/mutual_map.png)

Ось X — ставки ПВЗ относительно базовых, ось Y — число заказов в день по коридору. Звезда — базовая точка.
«Выигрывают все» значит: экономия маркетплейса положительна, вклад ПВЗ не ниже {money(p.pvz_min_month)} ₽/мес,
цена и срок покупателя не хуже, продавец не платит больше. Таких ячеек {green_cells} из {len(orders_grid) * len(fee_grid)},
из них {dark_cells} покрывают и постоянные расходы пилота.

## 7. Выводы

1. Mesh даёт **{mesh['saving_pct']:.1f}%** экономии по потоку и ускоряет ближний заказ на {mesh['eta_base_h'] - mesh['eta_mesh_h']:.0f} ч при прежней цене.
2. Результат после постоянных расходов пилота: выделенные рейсы — {money(ded['net_after_fixed_month'])} ₽/мес, с попутной загрузкой — {money(mesh['net_after_fixed_month'])} ₽/мес. {"Выделенные рейсы сами пилот не окупают, попутная загрузка переводит результат в плюс: это граница применимости." if ded['net_after_fixed_month'] < 0 <= mesh['net_after_fixed_month'] else ""}
3. Пессимистичный сценарий: зона {pess['zone']}, результат {money(pess['net_after_fixed_month'])} ₽/мес. Оптимистичный: экономия {opt['saving_pct']:.0f}%, результат {money(opt['net_after_fixed_month'])} ₽/мес. Диапазон широкий, поэтому запуск начинается с проверки реальных затрат.
4. **Главная неопределённость — параметр «{top['label']}»** (размах {money(top['swing'])} ₽/мес). Его нужно заменить реальными данными в первую очередь.
5. ПВЗ получает около {money(mesh['pvz_per_pvz_month'])} ₽/мес на точку дополнительно. Это выше принятого минимума, но не «золотая жила».

> Почему при попутной загрузке доля mesh-заказов ниже, чем при одних выделенных рейсах: решатель максимизирует экономию, а не охват.
> Часть заказов остаётся на хабе, потому что их выгода не покрывает отдельную машину, а места на попутном рейсе ограничено.

## 8. Что модель не учитывает

- Эффект конверсии и снижения возвратов у продавца (нет данных): выгода продавца занижена.
- Бонусы и штрафы ПВЗ (бонус за срок +10%, 5% за продажу с полки): в симуляции выключены; на маркетплейс это добавит расходы.
- Неликвид, возвраты и вечерний пик: описаны в бизнес-модели и покрываются сценариями MVP, но не входят в расчёт потока.
- Один коридор и статичная зона на весь период; нет динамики спроса по SKU.
- Ёмкость подсобки учтена агрегатно (общий коэффициент), а не по каждому ПВЗ и дню.
- Стоимость хранения на хабе принята равной ставке ПВЗ (допущение).
"""
(OUT / "model_report.md").write_text(md, encoding="utf-8")
print("OK", {k: round(mesh[k], 1) for k in ("saving_month", "saving_pct", "net_after_fixed_month")})
