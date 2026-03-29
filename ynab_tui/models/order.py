"""Retail order models for YNAB Categorizer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..utils import truncate_list_display


@dataclass
class OrderItem:
    """A single item from a retail order."""

    name: str
    price: Optional[float] = None
    quantity: int = 1
    asin: Optional[str] = None  # Preserved for Amazon compatibility

    @property
    def display_name(self) -> str:
        """Truncated name for display."""
        max_len = 50
        if len(self.name) <= max_len:
            return self.name
        return self.name[: max_len - 3] + "..."


@dataclass
class RetailOrder:
    """Represents a retailer order enriched from an external source."""

    external_id: str
    order_date: datetime
    total: float  # Total order amount
    items: list[OrderItem] = field(default_factory=list)
    source: str = "amazon"  # amazon, monarch
    retailer: str = "amazon"  # amazon, target, ...
    source_metadata: Optional[dict] = None

    # Metadata
    status: str = "unknown"  # delivered, shipped, processing, etc.
    shipment_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None

    # Cache info
    from_cache: bool = False
    fetched_at: Optional[datetime] = None

    @property
    def item_names(self) -> list[str]:
        """Get just the item names."""
        return [item.name for item in self.items]

    @property
    def order_id(self) -> str:
        """Compatibility alias for legacy Amazon-centric code."""
        return self.external_id

    @property
    def item_count(self) -> int:
        """Total number of items."""
        return sum(item.quantity for item in self.items)

    @property
    def display_items(self) -> str:
        """Format items for display."""
        names = [item.display_name for item in self.items]
        return truncate_list_display(names)

    @property
    def display_date(self) -> str:
        """Format date for display."""
        return self.order_date.strftime("%Y-%m-%d")


@dataclass
class OrderMatch:
    """Result of matching a transaction to an Amazon order."""

    transaction_id: str
    order: RetailOrder

    # Match details
    amount_diff: float  # Difference between transaction and order total
    days_diff: int  # Days between transaction and order date

    @property
    def is_exact_amount(self) -> bool:
        """Check if amounts match exactly."""
        return abs(self.amount_diff) < 0.01

    @property
    def is_same_day(self) -> bool:
        """Check if dates match."""
        return self.days_diff == 0


class AmazonOrder(RetailOrder):
    """Compatibility wrapper for legacy Amazon-centric construction."""

    def __init__(
        self,
        order_id: Optional[str] = None,
        *,
        external_id: Optional[str] = None,
        order_date: datetime,
        total: float,
        items: Optional[list[OrderItem]] = None,
        source: str = "amazon",
        retailer: str = "amazon",
        source_metadata: Optional[dict] = None,
        status: str = "unknown",
        shipment_date: Optional[datetime] = None,
        delivery_date: Optional[datetime] = None,
        from_cache: bool = False,
        fetched_at: Optional[datetime] = None,
    ) -> None:
        super().__init__(
            external_id=external_id or order_id or "",
            order_date=order_date,
            total=total,
            items=items or [],
            source=source,
            retailer=retailer,
            source_metadata=source_metadata,
            status=status,
            shipment_date=shipment_date,
            delivery_date=delivery_date,
            from_cache=from_cache,
            fetched_at=fetched_at,
        )
