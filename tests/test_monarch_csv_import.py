"""Tests for Monarch CSV import support."""

from pathlib import Path

import pytest

from ynab_tui.config import MonarchConfig, PayeesConfig
from ynab_tui.db.database import Database
from ynab_tui.services.monarch_csv_import import MonarchCsvImportError, parse_monarch_csv
from ynab_tui.services.sync import SyncService


class DummyYNABClient:
    """Minimal YNAB client stub for import-only sync service tests."""

    def get_current_budget_id(self) -> str:
        return "budget-123"


def test_parse_monarch_csv_extracts_items_from_notes(tmp_path: Path):
    """Note fields should become itemized retail enrichment when available."""
    csv_path = tmp_path / "monarch.csv"
    csv_path.write_text(
        "Date,Merchant,Amount,Notes,Tags,Transaction Type,ID\n"
        "2026-03-01,Amazon Marketplace,-44.99,\"Items: Widget A\n- Widget B\",home,debit,txn-1\n"
    )

    orders, metadata = parse_monarch_csv(csv_path, PayeesConfig(), MonarchConfig())

    assert len(orders) == 1
    assert orders[0].source == "monarch_csv"
    assert orders[0].retailer == "amazon"
    assert orders[0].external_id == "txn-1"
    assert orders[0].item_names == ["Widget A", "Widget B"]
    assert metadata["retailers_detected"] == {"amazon": 1}


def test_parse_monarch_csv_falls_back_to_merchant_name(tmp_path: Path):
    """Rows without item detail should still import as weak merchant-level enrichment."""
    csv_path = tmp_path / "monarch.csv"
    csv_path.write_text(
        "Date,Merchant,Amount,Transaction Type\n"
        "2026-03-02,Target Store,-18.50,debit\n"
    )

    orders, _ = parse_monarch_csv(csv_path, PayeesConfig(), MonarchConfig())

    assert len(orders) == 1
    assert orders[0].retailer == "target"
    assert orders[0].item_names == ["Target Store"]


def test_parse_monarch_csv_rejects_missing_required_columns(tmp_path: Path):
    """A malformed CSV should surface a useful validation error."""
    csv_path = tmp_path / "broken.csv"
    csv_path.write_text("Date,Merchant\n2026-03-02,Amazon Marketplace\n")

    with pytest.raises(MonarchCsvImportError, match="amount column"):
        parse_monarch_csv(csv_path, PayeesConfig(), MonarchConfig())


def test_import_monarch_csv_replace_source_only_clears_monarch_csv(tmp_path: Path):
    """Replacing the CSV source should not remove orders from other retail sources."""
    db = Database(tmp_path / "test.db")
    db.cache_retail_order("amazon", "amazon", "amz-1", __import__("datetime").datetime(2026, 3, 1), 44.99)
    db.upsert_retail_order_items("amazon", "amz-1", [{"name": "Amazon Widget", "price": 44.99, "quantity": 1}])
    db.cache_retail_order("monarch_csv", "amazon", "csv-old", __import__("datetime").datetime(2026, 3, 2), 12.50)
    db.upsert_retail_order_items("monarch_csv", "csv-old", [{"name": "Old CSV", "price": 12.50, "quantity": 1}])

    csv_path = tmp_path / "monarch.csv"
    csv_path.write_text(
        "Date,Merchant,Amount,Notes,Transaction Type,ID\n"
        "2026-03-03,Amazon Marketplace,-20.00,Items: Fresh Widget,debit,txn-new\n"
    )

    sync_service = SyncService(db=db, ynab=DummyYNABClient())
    result = sync_service.import_monarch_csv(
        str(csv_path),
        payees_config=PayeesConfig(),
        monarch_config=MonarchConfig(),
        replace_source=True,
    )

    assert result.success is True
    assert db.get_order_count(source="amazon") == 1
    assert db.get_order_count(source="monarch_csv") == 1
    imported = db.get_cached_retail_order("monarch_csv", "txn-new")
    assert imported is not None
    assert db.get_cached_retail_order("monarch_csv", "csv-old") is None
    db.close()
