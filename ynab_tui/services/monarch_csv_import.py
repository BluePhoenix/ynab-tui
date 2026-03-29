"""Helpers for importing Monarch transaction CSV exports."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import MonarchConfig, PayeesConfig
from ..models import OrderItem, RetailOrder


class MonarchCsvImportError(Exception):
    """Raised when a Monarch CSV import cannot be parsed."""


_LINE_END_PRICE_RE = re.compile(r"^(?P<name>.+?)\s*-\s*\$(?P<price>\d+(?:\.\d{1,2})?)\s*$")


def parse_monarch_csv(
    csv_path: str | Path,
    payees_config: PayeesConfig,
    monarch_config: MonarchConfig | None = None,
) -> tuple[list[RetailOrder], dict[str, Any]]:
    """Parse a Monarch transaction CSV into normalized retail orders."""
    path = Path(csv_path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise MonarchCsvImportError("CSV appears to be empty or missing a header row")

        headers = {_normalize_key(name): name for name in reader.fieldnames if name}
        _validate_headers(headers)

        allowed_retailers = set((monarch_config.retailers if monarch_config else ["amazon", "target"]))
        orders: list[RetailOrder] = []
        retailer_counts: Counter[str] = Counter()
        rows_seen = 0
        rows_skipped = 0

        for raw_row in reader:
            rows_seen += 1
            normalized = {_normalize_key(k): (v or "").strip() for k, v in raw_row.items() if k}

            order = _row_to_order(normalized, raw_row, payees_config, allowed_retailers)
            if order is None:
                rows_skipped += 1
                continue

            orders.append(order)
            retailer_counts[order.retailer] += 1

    return orders, {
        "rows_seen": rows_seen,
        "rows_skipped": rows_skipped,
        "retailers_detected": dict(retailer_counts),
    }


def _validate_headers(headers: dict[str, str]) -> None:
    if not any(key in headers for key in ("date", "transaction_date")):
        raise MonarchCsvImportError("CSV is missing a date column")
    if "amount" not in headers:
        raise MonarchCsvImportError("CSV is missing an amount column")
    if not any(
        key in headers
        for key in ("merchant", "merchant_name", "name", "payee", "original_statement")
    ):
        raise MonarchCsvImportError("CSV is missing a merchant/payee column")


def _row_to_order(
    row: dict[str, str],
    raw_row: dict[str, str],
    payees_config: PayeesConfig,
    allowed_retailers: set[str],
) -> RetailOrder | None:
    merchant = _first_value(
        row,
        "merchant",
        "merchant_name",
        "name",
        "payee",
        "original_statement",
    )
    original_statement = _first_value(row, "original_statement", "statement", "description")
    search_text = " ".join(filter(None, [merchant, original_statement]))
    retailer = _infer_retailer(search_text, payees_config)
    if retailer is None or retailer not in allowed_retailers:
        return None

    txn_date = _parse_date(_first_value(row, "date", "transaction_date"))
    if txn_date is None:
        return None

    amount = _parse_amount(_first_value(row, "amount"))
    if amount is None or not _is_purchase(row, amount):
        return None

    external_id = _first_value(row, "id", "transaction_id", "transactionid")
    if not external_id:
        external_id = _derive_external_id(txn_date, amount, merchant, retailer, row)

    items = _extract_items(row, merchant)

    return RetailOrder(
        external_id=external_id,
        order_date=txn_date,
        total=abs(amount),
        items=items,
        source="monarch_csv",
        retailer=retailer,
        source_metadata={k: v for k, v in raw_row.items() if k},
    )


def _extract_items(row: dict[str, str], merchant: str) -> list[OrderItem]:
    items: list[OrderItem] = []

    note_like = _first_value(row, "notes", "note", "memo")
    if note_like:
        parts = re.split(r"[\n;|]+", note_like)
        for part in parts:
            parsed = _parse_item_line(part)
            if parsed:
                items.append(parsed)

    if not items:
        tags = _first_value(row, "tags", "tag")
        if tags:
            for part in tags.split(","):
                parsed = _parse_item_line(part)
                if parsed:
                    items.append(parsed)

    if not items and merchant:
        items.append(OrderItem(name=merchant))

    return items


def _clean_item_text(value: str) -> str:
    cleaned = value.strip(" -*\t")
    if ":" in cleaned and cleaned.lower().startswith(("items", "item", "order")):
        _, cleaned = cleaned.split(":", 1)
    return cleaned.strip()


def _parse_item_line(value: str) -> OrderItem | None:
    cleaned = _clean_item_text(value)
    if not cleaned:
        return None

    price = None
    match = _LINE_END_PRICE_RE.match(cleaned)
    if match:
        cleaned = match.group("name").strip()
        try:
            price = float(match.group("price"))
        except ValueError:
            price = None

    quantity = 1
    qty_match = re.match(r"^(?P<qty>\d+)\s*x\s+(?P<rest>.+)$", cleaned, re.IGNORECASE)
    if qty_match:
        quantity = int(qty_match.group("qty"))
        cleaned = qty_match.group("rest").strip()

    if not cleaned:
        return None

    return OrderItem(name=cleaned, price=price, quantity=quantity)


def _infer_retailer(text: str, payees_config: PayeesConfig) -> str | None:
    upper = text.upper()
    for pattern in payees_config.amazon_patterns:
        if pattern.upper() in upper:
            return "amazon"
    for pattern in payees_config.target_patterns:
        if pattern.upper() in upper:
            return "target"
    return None


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    candidates = [text]
    if len(text) >= 10:
        candidates.append(text[:10])
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        for candidate in candidates:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_amount(value: str) -> float | None:
    if not value:
        return None
    text = value.strip().replace("$", "").replace(",", "")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    try:
        amount = float(text)
    except ValueError:
        return None
    return -abs(amount) if negative else amount


def _is_purchase(row: dict[str, str], amount: float) -> bool:
    txn_type = _first_value(row, "transaction_type", "type").lower()
    if txn_type:
        if any(token in txn_type for token in ("credit", "refund", "income", "deposit", "transfer")):
            return False
        if any(token in txn_type for token in ("debit", "expense", "purchase")):
            return True
    return amount < 0


def _derive_external_id(
    txn_date: datetime,
    amount: float,
    merchant: str,
    retailer: str,
    row: dict[str, str],
) -> str:
    material = "|".join(
        [
            retailer,
            txn_date.strftime("%Y-%m-%d"),
            f"{abs(amount):.2f}",
            merchant,
            _first_value(row, "notes", "note", "memo"),
            _first_value(row, "tags", "tag"),
        ]
    )
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]
    return f"monarch-csv-{digest}"


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key, "")
        if value:
            return value
    return ""
