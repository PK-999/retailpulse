from __future__ import annotations

import csv
import json
from pathlib import Path


def prepare_uci(source: Path, output: Path) -> dict[str, int]:
    """Split a UCI Online Retail CSV export into normalized logical JSONL datasets."""
    output.mkdir(parents=True, exist_ok=True)
    customers: dict[str, dict[str, str]] = {}
    products: dict[str, dict[str, str]] = {}
    orders: dict[str, dict[str, str | None]] = {}
    items: list[dict[str, str]] = []
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            invoice = row.get("InvoiceNo", "").strip()
            stock = row.get("StockCode", "").strip()
            customer = row.get("CustomerID", "").strip()
            if not invoice or not stock:
                continue
            if customer:
                customers[customer] = {"customer_id": customer, "country": row.get("Country", "")}
            products[stock] = {
                "product_id": stock,
                "description": row.get("Description", "").strip(),
                "unit_price": row.get("UnitPrice", "0"),
            }
            orders[invoice] = {
                "order_id": invoice,
                "customer_id": customer or None,
                "order_timestamp": row.get("InvoiceDate", ""),
                "country": row.get("Country", ""),
                "is_cancelled": str(invoice.startswith("C")).lower(),
            }
            items.append(
                {
                    "order_id": invoice,
                    "product_id": stock,
                    "quantity": row.get("Quantity", "0"),
                    "unit_price": row.get("UnitPrice", "0"),
                }
            )
    datasets = {
        "customers": list(customers.values()),
        "products": list(products.values()),
        "orders": list(orders.values()),
        "order_items": items,
    }
    for name, records in datasets.items():
        with (output / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return {name: len(records) for name, records in datasets.items()}
