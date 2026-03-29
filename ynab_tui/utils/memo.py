"""Helpers for working with YNAB memo fields."""

from __future__ import annotations

YNAB_MEMO_MAX_LENGTH = 500


def normalize_memo(memo: str | None) -> str | None:
    """Clamp a memo to YNAB's maximum supported length."""
    if memo is None:
        return None
    return memo[:YNAB_MEMO_MAX_LENGTH]
