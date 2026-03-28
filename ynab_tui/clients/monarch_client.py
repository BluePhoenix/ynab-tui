"""Monarch Money client for retail enrichment data."""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..config import MonarchConfig
from ..models import AmazonOrder, OrderItem

logger = logging.getLogger(__name__)


class MonarchClientError(Exception):
    """Error communicating with Monarch."""

    pass


class MonarchClient:
    """Client for reading retail enrichment data from Monarch."""

    def __init__(
        self,
        config: MonarchConfig,
        api_client: Any | None = None,
        client_factory: Any | None = None,
    ) -> None:
        self._config = config
        self._api_client = api_client
        self._client_factory = client_factory

    def _run(self, maybe_awaitable: Any) -> Any:
        """Run a coroutine if needed, otherwise return the value."""
        if inspect.isawaitable(maybe_awaitable):
            return asyncio.run(maybe_awaitable)
        return maybe_awaitable

    def _build_client(self) -> Any:
        """Create a Monarch API client."""
        if self._api_client is not None:
            return self._api_client

        if self._client_factory is not None:
            return self._client_factory()

        try:
            from monarchmoney import MonarchMoney
        except ImportError as exc:
            raise MonarchClientError(
                "Monarch support requires the 'monarchmoney' package to be installed"
            ) from exc

        return MonarchMoney()

    def _load_session(self, client: Any) -> None:
        """Load a session or token into the Monarch client."""
        if not self._config.session_file and not self._config.session_token:
            raise MonarchClientError(
                "Monarch session not configured. Set MONARCH_SESSION_FILE or MONARCH_SESSION_TOKEN."
            )

        load_session = getattr(client, "load_session", None)
        if load_session is None:
            raise MonarchClientError("Configured Monarch client does not support session loading")

        try:
            if self._config.session_file:
                session_path = str(Path(self._config.session_file).expanduser())
                try:
                    self._run(load_session(session_path))
                    return
                except TypeError:
                    # Some client versions use a no-argument load_session() that reads
                    # a default session path. Fall through to other auth options.
                    pass

            if self._config.session_token:
                self._run(load_session(self._config.session_token))
                return

            self._run(load_session())
        except Exception as exc:
            raise MonarchClientError(f"Failed to load Monarch session: {exc}") from exc

    def _ensure_client(self) -> Any:
        """Return an authenticated Monarch client."""
        client = self._build_client()
        if self._api_client is None:
            self._load_session(client)
            self._api_client = client
        return client

    def test_connection(self) -> dict[str, Any]:
        """Validate the configured Monarch session."""
        try:
            client = self._ensure_client()
            get_accounts = getattr(client, "get_accounts", None)
            if get_accounts is None:
                raise MonarchClientError("Configured Monarch client does not support get_accounts()")
            accounts = self._run(get_accounts())
            return {"success": True, "account_count": len(accounts or [])}
        except Exception as exc:
            if isinstance(exc, MonarchClientError):
                return {"success": False, "error": str(exc)}
            return {"success": False, "error": f"{exc}"}

    def get_recent_orders(self, days: Optional[int] = None) -> list[AmazonOrder]:
        """Fetch recent Monarch retail transactions normalized as retail orders."""
        lookback_days = days or self._config.sync_lookback_days
        since_date = datetime.now() - timedelta(days=lookback_days)
        return self.get_orders_since(since_date)

    def get_orders_since(self, since_date: datetime) -> list[AmazonOrder]:
        """Fetch Monarch transactions since the given date."""
        client = self._ensure_client()

        get_transactions = getattr(client, "get_transactions", None)
        if get_transactions is None:
            raise MonarchClientError("Configured Monarch client does not support get_transactions()")

        try:
            transactions = self._run(get_transactions(start_date=since_date.date().isoformat()))
        except TypeError:
            transactions = self._run(get_transactions())

        orders: list[AmazonOrder] = []
        for txn in transactions or []:
            order = self._normalize_transaction(client, txn, since_date)
            if order is not None:
                orders.append(order)

        return orders

    def _normalize_transaction(
        self,
        client: Any,
        txn: Any,
        since_date: datetime,
    ) -> Optional[AmazonOrder]:
        """Convert a Monarch transaction into a normalized retail order."""
        raw = self._to_dict(txn)

        txn_date = self._parse_datetime(raw.get("date") or raw.get("transactionDate"))
        if txn_date is None or txn_date < since_date:
            return None

        retailer = self._detect_retailer(raw)
        if retailer not in self._config.retailers:
            return None

        order_id = str(raw.get("id") or raw.get("transaction_id") or "")
        if not order_id:
            return None

        amount = abs(self._coerce_float(raw.get("amount") or raw.get("display_amount")))
        detail = self._get_transaction_detail(client, order_id)
        items = self._extract_items(detail or raw)

        if not items:
            return None

        return AmazonOrder(
            external_id=order_id,
            order_date=txn_date,
            total=amount,
            items=items,
            source="monarch",
            retailer=retailer,
            from_cache=False,
            fetched_at=datetime.now(),
            source_metadata=detail or raw,
        )

    def _get_transaction_detail(self, client: Any, transaction_id: str) -> dict[str, Any] | None:
        """Fetch a richer transaction detail payload when supported."""
        get_detail = getattr(client, "get_transaction_details", None)
        if get_detail is None:
            return None

        try:
            detail = self._run(get_detail(transaction_id))
            return self._to_dict(detail)
        except Exception as exc:
            logger.debug("Failed to fetch Monarch transaction detail for %s: %s", transaction_id, exc)
            return None

    def _extract_items(self, payload: dict[str, Any]) -> list[OrderItem]:
        """Extract itemized retail data from a Monarch transaction payload."""
        item_candidates = (
            payload.get("items")
            or payload.get("line_items")
            or payload.get("split_items")
            or payload.get("splits")
            or []
        )

        items: list[OrderItem] = []
        for item in item_candidates:
            row = self._to_dict(item)
            name = (
                row.get("name")
                or row.get("title")
                or row.get("description")
                or row.get("merchant")
                or row.get("memo")
            )
            if not name:
                continue
            price = row.get("price")
            amount = row.get("amount")
            quantity = row.get("quantity") or 1
            parsed_price = None
            for candidate in (price, amount):
                if candidate is None:
                    continue
                parsed_price = abs(self._coerce_float(candidate))
                if parsed_price != 0:
                    break
            items.append(
                OrderItem(
                    name=str(name),
                    price=parsed_price,
                    quantity=int(quantity) if str(quantity).isdigit() else 1,
                )
            )

        if items:
            return items

        notes = payload.get("notes") or payload.get("note") or payload.get("memo") or ""
        parsed_notes = self._extract_items_from_notes(str(notes))
        if parsed_notes:
            return parsed_notes

        merchant = (
            payload.get("merchantName")
            or payload.get("merchant_name")
            or payload.get("merchant")
            or payload.get("name")
        )
        return [OrderItem(name=str(merchant))] if merchant else []

    def _extract_items_from_notes(self, notes: str) -> list[OrderItem]:
        """Parse lightweight item annotations from notes."""
        items: list[OrderItem] = []
        for line in notes.splitlines():
            stripped = line.strip(" -*\t")
            if not stripped:
                continue
            if ":" in stripped and stripped.lower().startswith(("items", "item", "order")):
                _, value = stripped.split(":", 1)
                stripped = value.strip()
            if stripped:
                items.append(OrderItem(name=stripped))
        return items

    def _detect_retailer(self, payload: dict[str, Any]) -> str:
        """Infer the retailer from Monarch transaction fields."""
        joined = " ".join(
            str(payload.get(key, "") or "")
            for key in ["merchantName", "merchant_name", "merchant", "name", "notes", "note", "memo"]
        ).upper()

        if "TARGET" in joined:
            return "target"
        return "amazon"

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse common Monarch date representations."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value)
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text[: len(fmt.replace("%f", "000000"))], fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert supported object styles to a dictionary."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "dict"):
            return value.dict()
        if hasattr(value, "__dict__"):
            return {
                key: val
                for key, val in vars(value).items()
                if not key.startswith("_") and not callable(val)
            }
        return {}

    def _coerce_float(self, value: Any) -> float:
        """Parse loose numeric representations used by unofficial clients."""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace("$", "").replace(",", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = f"-{text[1:-1]}"
        try:
            return float(text)
        except ValueError:
            return 0.0
