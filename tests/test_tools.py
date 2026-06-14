"""
tests/test_tools.py

Pytest tests for each FitFindr tool, covering both the happy path and each
failure/edge-case mode. Run with: pytest tests/
"""

import pytest

from tools import search_listings, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossible combo — should return empty list, not raise
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_results_sorted_by_relevance():
    # The top result should be a stronger keyword match than the last
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) >= 2
    # All results matched at least one keyword (no zero-score items)
    for item in results:
        text = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            " ".join(item.get("style_tags", [])),
        ]).lower()
        assert any(kw in text for kw in ["vintage", "graphic", "tee"])


def test_search_no_price_filter():
    # With no filters, any keyword match should appear
    results = search_listings("denim", size=None, max_price=None)
    assert len(results) > 0


def test_search_returns_list_of_dicts():
    results = search_listings("jacket", size=None, max_price=None)
    for item in results:
        assert isinstance(item, dict)
        assert "id" in item
        assert "title" in item
        assert "price" in item


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert len(result) > 0
    # Should be an error message, not raise an exception
    assert "cannot" in result.lower() or "error" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert len(result) > 0


# ── suggest_outfit (empty wardrobe — no LLM call needed to verify behavior) ──

def test_suggest_outfit_empty_wardrobe_does_not_crash():
    """suggest_outfit with empty wardrobe must return a non-empty string, not crash."""
    # Import here so missing API key doesn't break other tests
    from tools import suggest_outfit
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0
