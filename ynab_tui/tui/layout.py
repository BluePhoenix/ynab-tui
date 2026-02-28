"""Centralized layout constants for column widths.

This module provides a single source of truth for column dimensions
used across transaction lists, headers, and modals.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnWidths:
    """Column widths for transaction display.

    Fixed columns have constant widths, dynamic columns expand based on
    available terminal width.
    """

    # Fixed-width columns
    date: int = 10
    amount: int = 12
    status: int = 6

    # Dynamic-width columns (calculated based on terminal width)
    payee: int = 22
    category: int = 20
    account: int = 16

    # Spacing between columns
    col_spacing: int = 2

    @property
    def fixed_width(self) -> int:
        """Total width of fixed columns plus spacing."""
        # 5 gaps between 6 columns
        return self.date + self.amount + self.status + (5 * self.col_spacing)

    @property
    def dynamic_width(self) -> int:
        """Total width of dynamic columns."""
        return self.payee + self.category + self.account

    @property
    def total_width(self) -> int:
        """Total width of all columns including spacing."""
        return self.fixed_width + self.dynamic_width


# Default column widths (for standard 120+ char terminals)
DEFAULT_WIDTHS = ColumnWidths()

# Minimum widths for dynamic columns
MIN_PAYEE = 15
MIN_CATEGORY = 12
MIN_ACCOUNT = 10


def calculate_column_widths(terminal_width: int) -> ColumnWidths:
    """Calculate optimal column widths based on terminal width.

    Args:
        terminal_width: Available terminal width in characters.

    Returns:
        ColumnWidths with dimensions optimized for the terminal.
    """
    # Account for border/padding (2 chars on each side)
    available = terminal_width - 4

    # Calculate remaining space for dynamic columns
    fixed = DEFAULT_WIDTHS.fixed_width
    remaining = available - fixed

    if remaining <= 0:
        # Terminal too narrow, use minimums
        return ColumnWidths(
            payee=MIN_PAYEE,
            category=MIN_CATEGORY,
            account=MIN_ACCOUNT,
        )

    # Current default dynamic width
    default_dynamic = DEFAULT_WIDTHS.dynamic_width

    if remaining >= default_dynamic:
        # Enough space - distribute extra proportionally
        extra = remaining - default_dynamic
        # Ratio: payee 35%, category 35%, account 30%
        payee_extra = int(extra * 0.35)
        category_extra = int(extra * 0.35)
        account_extra = extra - payee_extra - category_extra

        return ColumnWidths(
            payee=DEFAULT_WIDTHS.payee + payee_extra,
            category=DEFAULT_WIDTHS.category + category_extra,
            account=DEFAULT_WIDTHS.account + account_extra,
        )
    else:
        # Need to shrink - distribute proportionally but respect minimums
        ratio = remaining / default_dynamic
        payee = max(MIN_PAYEE, int(DEFAULT_WIDTHS.payee * ratio))
        category = max(MIN_CATEGORY, int(DEFAULT_WIDTHS.category * ratio))
        account = max(MIN_ACCOUNT, int(DEFAULT_WIDTHS.account * ratio))

        return ColumnWidths(
            payee=payee,
            category=category,
            account=account,
        )


def format_header_row(widths: ColumnWidths) -> str:
    """Format the column header row.

    Args:
        widths: Column widths to use.

    Returns:
        Formatted header string.
    """
    sp = " " * widths.col_spacing
    # Align headers with data columns:
    # - Data has tag (2 chars) + amazon indicator (2 chars) before payee text
    # - Add 4 spaces before "Payee" to match, taking from payee column width
    payee_padding = 4  # tag + amazon indicators
    payee_col = (" " * payee_padding + "Payee").ljust(widths.payee)
    return (
        f"{'Date':<{widths.date}}{sp}"
        f"{payee_col}{sp}"
        f"{'Amount':>{widths.amount}}{sp}"
        f"{'Category':<{widths.category}}{sp}"
        f"{'Account':<{widths.account}}{sp}"
        f"{'Status':<{widths.status}}"
    )


@dataclass(frozen=True)
class SplitColumnWidths:
    """Column widths for split modal item display.

    Fixed columns have constant widths, dynamic columns expand based on
    available terminal width.
    """

    # Fixed-width columns
    status: int = 3  # [ ] or [✓]
    quantity: int = 3  # x2 or spaces
    price: int = 8  # $1,234.56

    # Dynamic-width columns
    item_name: int = 40
    category: int = 20

    # Spacing between columns
    col_spacing: int = 2

    @property
    def fixed_width(self) -> int:
        """Total width of fixed columns plus spacing."""
        # 4 gaps between 5 columns
        return self.status + self.quantity + self.price + (4 * self.col_spacing)


# Minimum widths for split dynamic columns
MIN_ITEM_NAME = 20
MIN_SPLIT_CATEGORY = 12

DEFAULT_SPLIT_WIDTHS = SplitColumnWidths()


def calculate_split_column_widths(terminal_width: int) -> SplitColumnWidths:
    """Calculate optimal column widths for split modal.

    Args:
        terminal_width: Available terminal width in characters.

    Returns:
        SplitColumnWidths with dimensions optimized for the terminal.
    """
    # Account for border/padding (2 chars each side + 1 char ListView padding each side)
    available = terminal_width - 6

    fixed = DEFAULT_SPLIT_WIDTHS.fixed_width
    remaining = available - fixed

    if remaining <= 0:
        return SplitColumnWidths(
            item_name=MIN_ITEM_NAME,
            category=MIN_SPLIT_CATEGORY,
        )

    default_dynamic = DEFAULT_SPLIT_WIDTHS.item_name + DEFAULT_SPLIT_WIDTHS.category

    if remaining >= default_dynamic:
        extra = remaining - default_dynamic
        # Item name gets 70%, category gets 30%
        name_extra = int(extra * 0.70)
        cat_extra = extra - name_extra
        return SplitColumnWidths(
            item_name=DEFAULT_SPLIT_WIDTHS.item_name + name_extra,
            category=DEFAULT_SPLIT_WIDTHS.category + cat_extra,
        )
    else:
        ratio = remaining / default_dynamic
        item_name = max(MIN_ITEM_NAME, int(DEFAULT_SPLIT_WIDTHS.item_name * ratio))
        category = max(MIN_SPLIT_CATEGORY, int(DEFAULT_SPLIT_WIDTHS.category * ratio))
        return SplitColumnWidths(
            item_name=item_name,
            category=category,
        )
