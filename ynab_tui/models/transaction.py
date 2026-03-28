"""Transaction models for YNAB Categorizer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..utils import truncate_list_display

# Payees that represent balance adjustments (don't need categories)
BALANCE_ADJUSTMENT_PAYEES = frozenset(
    {
        "Reconciliation Balance Adjustment",
        "Manual Balance Adjustment",
        "Starting Balance",
    }
)


@dataclass
class SubTransaction:
    """Represents a YNAB split transaction component.

    When a YNAB transaction is split into multiple categories, each split
    is represented as a SubTransaction. The parent transaction will have
    category_name="Split" and category_id=None.
    """

    id: str  # YNAB subtransaction ID
    transaction_id: str  # Parent transaction ID
    amount: float  # In dollars (negative for outflows)
    payee_id: Optional[str] = None
    payee_name: Optional[str] = None
    memo: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None

    @property
    def is_uncategorized(self) -> bool:
        """Check if subtransaction needs categorization."""
        return self.category_id is None or self.category_name is None

    @property
    def display_amount(self) -> str:
        """Format amount for display."""
        sign = "" if self.amount >= 0 else "-"
        return f"{sign}${abs(self.amount):,.2f}"


@dataclass(init=False)
class Transaction:
    """Represents a YNAB transaction for categorization.

    This is our internal representation that combines YNAB transaction data
    with enrichment from Amazon orders.
    """

    # YNAB fields
    id: str  # YNAB transaction ID
    date: datetime
    amount: float  # In dollars (negative for outflows)
    payee_name: str
    payee_id: Optional[str] = None
    memo: Optional[str] = None
    account_name: Optional[str] = None
    account_id: Optional[str] = None

    # Current category (may be None if uncategorized)
    category_id: Optional[str] = None
    category_name: Optional[str] = None

    # Approval status
    approved: bool = False
    cleared: str = "uncleared"  # cleared, uncleared, reconciled

    # Split transaction support
    is_split: bool = False  # True if this transaction has subtransactions
    subtransactions: list[SubTransaction] = field(default_factory=list)

    # Sync status for local changes
    sync_status: str = "synced"  # 'synced', 'pending_push', 'conflict'

    # Transfer fields (transfers don't need categories)
    transfer_account_id: Optional[str] = None  # If set, this is a transfer
    transfer_account_name: Optional[str] = None  # Target account name for display
    debt_transaction_type: Optional[str] = None  # 'payment', 'refund', 'fee', 'interest'

    # Enrichment fields (populated by our services)
    is_retail: bool = False
    retail_items: list[str] = field(default_factory=list)
    retail_order_id: Optional[str] = None
    retail_source: Optional[str] = None
    retailer: Optional[str] = None

    # Historical context
    payee_history_summary: Optional[str] = None  # e.g., "85% Groceries"

    def __init__(
        self,
        id: str,
        date: datetime,
        amount: float,
        payee_name: str,
        payee_id: Optional[str] = None,
        memo: Optional[str] = None,
        account_name: Optional[str] = None,
        account_id: Optional[str] = None,
        category_id: Optional[str] = None,
        category_name: Optional[str] = None,
        approved: bool = False,
        cleared: str = "uncleared",
        is_split: bool = False,
        subtransactions: Optional[list[SubTransaction]] = None,
        sync_status: str = "synced",
        transfer_account_id: Optional[str] = None,
        transfer_account_name: Optional[str] = None,
        debt_transaction_type: Optional[str] = None,
        is_retail: bool = False,
        retail_items: Optional[list] = None,
        retail_order_id: Optional[str] = None,
        retail_source: Optional[str] = None,
        retailer: Optional[str] = None,
        payee_history_summary: Optional[str] = None,
        is_amazon: Optional[bool] = None,
        amazon_items: Optional[list] = None,
        amazon_order_id: Optional[str] = None,
    ):
        self.id = id
        self.date = date
        self.amount = amount
        self.payee_name = payee_name
        self.payee_id = payee_id
        self.memo = memo
        self.account_name = account_name
        self.account_id = account_id
        self.category_id = category_id
        self.category_name = category_name
        self.approved = approved
        self.cleared = cleared
        self.is_split = is_split
        self.subtransactions = subtransactions or []
        self.sync_status = sync_status
        self.transfer_account_id = transfer_account_id
        self.transfer_account_name = transfer_account_name
        self.debt_transaction_type = debt_transaction_type
        self.is_retail = is_retail
        self.retail_items = list(retail_items or amazon_items or [])
        self.retail_order_id = retail_order_id or amazon_order_id
        self.retail_source = retail_source
        self.retailer = retailer
        self.payee_history_summary = payee_history_summary

        if is_amazon is True:
            self.is_retail = True
            if not self.retailer:
                self.retailer = "amazon"

    @property
    def is_transfer(self) -> bool:
        """Check if transaction is a transfer (doesn't need category)."""
        return self.transfer_account_id is not None

    @property
    def is_balance_adjustment(self) -> bool:
        """Check if transaction is a balance adjustment (doesn't need category)."""
        return self.payee_name in BALANCE_ADJUSTMENT_PAYEES

    @property
    def is_uncategorized(self) -> bool:
        """Check if transaction needs categorization.

        Transfers and balance adjustments don't need categories.
        """
        if self.is_transfer:
            return False
        if self.is_balance_adjustment:
            return False
        return self.category_id is None or self.category_name is None

    @property
    def is_unapproved(self) -> bool:
        """Check if transaction needs approval."""
        return not self.approved

    @property
    def needs_push(self) -> bool:
        """Check if transaction has local changes to push to YNAB."""
        return self.sync_status == "pending_push"

    @property
    def has_conflict(self) -> bool:
        """Check if transaction has a sync conflict."""
        return self.sync_status == "conflict"

    @property
    def display_amount(self) -> str:
        """Format amount for display."""
        sign = "" if self.amount >= 0 else "-"
        return f"{sign}${abs(self.amount):,.2f}"

    @property
    def display_date(self) -> str:
        """Format date for display."""
        return self.date.strftime("%Y-%m-%d")

    @property
    def enrichment_summary(self) -> str:
        """Summary of enrichment data for display."""
        if self.is_retail and self.retail_items:
            return truncate_list_display(self.retail_items)
        elif self.payee_history_summary:
            return f"Historical: {self.payee_history_summary}"
        return ""

    @property
    def is_amazon(self) -> bool:
        """Compatibility alias for Amazon-specific UI flows."""
        return self.is_retail and self.retailer == "amazon"

    @is_amazon.setter
    def is_amazon(self, value: bool) -> None:
        if value:
            self.is_retail = True
            if not self.retailer:
                self.retailer = "amazon"
        elif self.retailer == "amazon":
            self.is_retail = False
            self.retailer = None

    @property
    def amazon_items(self) -> list[str]:
        """Compatibility alias for legacy Amazon item enrichment."""
        return self.retail_items

    @amazon_items.setter
    def amazon_items(self, value: list[str]) -> None:
        self.retail_items = value

    @property
    def amazon_order_id(self) -> Optional[str]:
        """Compatibility alias for legacy Amazon order IDs."""
        return self.retail_order_id

    @amazon_order_id.setter
    def amazon_order_id(self, value: Optional[str]) -> None:
        self.retail_order_id = value


@dataclass
class TransactionBatch:
    """A batch of transactions for processing."""

    transactions: list[Transaction] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of transactions."""
        return len(self.transactions)

    @property
    def amazon_count(self) -> int:
        """Number of Amazon transactions."""
        return sum(1 for t in self.transactions if t.is_amazon)

    @property
    def other_count(self) -> int:
        """Number of non-Amazon transactions."""
        return self.total_count - self.amazon_count

    def filter_amazon(self) -> list[Transaction]:
        """Get only Amazon transactions."""
        return [t for t in self.transactions if t.is_amazon]

    def filter_other(self) -> list[Transaction]:
        """Get only non-Amazon transactions."""
        return [t for t in self.transactions if not t.is_amazon]
