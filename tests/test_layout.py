"""Tests for layout column width calculations."""

from ynab_tui.tui.layout import (
    SplitColumnWidths,
    calculate_split_column_widths,
)


class TestSplitColumnWidths:
    """Tests for SplitColumnWidths dataclass."""

    def test_default_values(self) -> None:
        """Default widths should be reasonable."""
        w = SplitColumnWidths()
        assert w.status == 3
        assert w.quantity == 3
        assert w.price == 8
        assert w.item_name == 40
        assert w.category == 20

    def test_fixed_width(self) -> None:
        """Fixed width should sum fixed columns + spacing."""
        w = SplitColumnWidths()
        # status(3) + quantity(3) + price(8) + 4 gaps * spacing(2) = 22
        assert w.fixed_width == 22


class TestCalculateSplitColumnWidths:
    """Tests for calculate_split_column_widths."""

    def test_wide_terminal_expands_name(self) -> None:
        """Wide terminal should give more space to item name."""
        w = calculate_split_column_widths(160)
        assert w.item_name > 40

    def test_narrow_terminal_uses_minimums(self) -> None:
        """Very narrow terminal should use minimum widths."""
        w = calculate_split_column_widths(40)
        assert w.item_name == 20
        assert w.category == 12

    def test_standard_terminal(self) -> None:
        """Standard 120-char terminal should have reasonable widths."""
        w = calculate_split_column_widths(120)
        assert w.item_name >= 40
        assert w.category >= 20

    def test_item_name_gets_majority(self) -> None:
        """Item name should get ~70% of extra dynamic space."""
        narrow = calculate_split_column_widths(100)
        wide = calculate_split_column_widths(200)
        name_growth = wide.item_name - narrow.item_name
        cat_growth = wide.category - narrow.category
        # name should grow more than category
        assert name_growth > cat_growth
