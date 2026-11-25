"""Ручной запуск Playwright против запущенного интерфейса на свежих демоданных."""

import os
import re
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    base = os.getenv("DEMO_URL", "http://127.0.0.1:5173").rstrip("/")
    executable = os.getenv("CHROMIUM_PATH")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(f"{base}/pvz", wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="Пункт выдачи")).to_be_visible()
        expect(page.get_by_text("Кроссовки беговые #1", exact=True)).to_be_visible()
        if screenshot := os.getenv("DEMO_SCREENSHOT"):
            page.screenshot(path=screenshot)

        # Начинаем с реальной приёмки в ПВЗ, затем проводим контрольный заказ.
        sku = next(item for item in page.request.get(f"{base}/api/skus").json() if item["size_class"] == "S")
        receipt = page.request.post(
            f"{base}/api/batches",
            headers={"Idempotency-Key": str(uuid4())},
            data={"sku_id": sku["id"], "pvz_id": 3, "qty": 1, "declared_class": "S"},
        )
        assert receipt.status == 201, receipt.text()

        page.get_by_role("tab", name="Заказы").click()
        page.get_by_role("button", name="Создать заказ", exact=True).click()
        page.get_by_role("button", name="Городской рейс").click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_text("95 ₽", exact=True)).to_be_visible()
        expect(dialog.get_by_text("109 ₽", exact=True)).to_be_visible()
        title = dialog.get_by_role("heading", name=re.compile("Решение по заказу")).inner_text()
        order_id = title.rsplit("#", 1)[1]
        dialog.get_by_role("button", name=re.compile("close|закрыть", re.I)).click()

        row = page.get_by_role("row").filter(has=page.get_by_role("cell", name=order_id, exact=True))
        row.get_by_role("button", name="Собрать").click()
        expect(row.get_by_text("Собран", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Рейсы").click()
        trip = page.get_by_role("row").filter(has_text="ПВЗ Мира → ПВЗ Компрос")
        trip.get_by_role("button", name="Отправить").click()
        trip.get_by_role("button", name="Прибыл", exact=True).click()
        expect(trip.get_by_text("Прибыл в ПВЗ", exact=True)).to_be_visible()

        page.get_by_role("tab", name="Заказы").click()
        row.get_by_role("button", name="Выдать").click()
        expect(row.get_by_text("Выдан", exact=True)).to_be_visible()
        row.get_by_role("button", name="Проводки").click()
        ledger = page.get_by_role("dialog")
        expect(ledger.get_by_text("Сумма проводок по заказу")).to_be_visible()
        expect(ledger.get_by_text("0 ₽", exact=True)).to_be_visible()
        ledger.get_by_role("button", name=re.compile("close|закрыть", re.I)).click()
        page.get_by_role("tab", name="Аналитика").click()
        expect(page.locator(".recharts-bar-rectangle path").first).to_be_visible()

        page.goto(f"{base}/model", wait_until="domcontentloaded")
        expect(page.get_by_text("Порог окупаемости рейса", exact=True)).to_be_visible()
        expect(page.locator(".recharts-line-curve")).to_be_visible()
        page.get_by_role("button", name="Пересчитать").click()
        expect(page.get_by_text("Чувствительность: ±20% к параметрам")).to_be_visible()
        page.goto(f"{base}/seller", wait_until="domcontentloaded")
        expect(page.get_by_text(re.compile("бизнес-модели v0.3"))).to_be_visible()
        expect(page.get_by_text("Чистая маржа")).to_be_visible()
        expect(page.get_by_role("columnheader", name="Налог")).to_be_visible()
        page.set_viewport_size({"width": 375, "height": 800})
        expect(page.get_by_role("navigation").get_by_role("button", name="ПВЗ")).to_be_visible()
        assert not errors, errors
        print(f"Browser smoke OK: #{order_id}, 95 ₽ против 109 ₽, выдача и баланс проводок.")


if __name__ == "__main__":
    main()
