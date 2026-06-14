"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex — no extra LLM call needed.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    # Extract size — "size M", "size S/M", or standalone size tokens
    size = None
    size_match = re.search(r"\bsize\s+([A-Z0-9/]+)\b", query, re.IGNORECASE)
    if size_match:
        size = size_match.group(1).upper()
    else:
        standalone = re.search(r"\b(XS|S/M|S|M|L|XL|XXL|2XL)\b", query)
        if standalone:
            size = standalone.group(1).upper()

    # Extract max_price — "under $30", "below 40", "max $25", "up to $50"
    max_price = None
    price_match = re.search(
        r"(?:under|below|max|up\s+to|at\s+most|for)\s*\$?\s*(\d+(?:\.\d{1,2})?)",
        query,
        re.IGNORECASE,
    )
    if price_match:
        max_price = float(price_match.group(1))
    else:
        # bare dollar sign: "$30"
        dollar_match = re.search(r"\$(\d+(?:\.\d{1,2})?)", query)
        if dollar_match:
            max_price = float(dollar_match.group(1))

    # Build description: strip price phrases and size phrases, keep the rest
    desc = query
    desc = re.sub(
        r"(?:under|below|max|up\s+to|at\s+most|for)\s*\$?\s*\d+(?:\.\d{1,2})?",
        "",
        desc,
        flags=re.IGNORECASE,
    )
    desc = re.sub(r"\$\d+(?:\.\d{1,2})?", "", desc)
    desc = re.sub(r"\bsize\s+[A-Z0-9/]+\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\b(XS|S/M|S|M|L|XL|XXL|2XL)\b", "", desc)
    desc = re.sub(r"\s+", " ", desc).strip(" ,.-")

    return {
        "description": desc if desc else query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and outfit_suggestion
        and fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into structured parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search for listings
    try:
        results = search_listings(description, size=size, max_price=max_price)
    except Exception as exc:
        session["error"] = f"Search failed unexpectedly: {exc}"
        return session

    session["search_results"] = results

    # Branch: no results → communicate clearly and stop
    if not results:
        parts = [f'No listings found for "{description}"']
        if size:
            parts.append(f"in size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.0f}")
        parts.append(
            ". Try broadening your search — remove the size filter, raise your price limit, "
            "or use different keywords."
        )
        session["error"] = " ".join(parts)
        return session

    # Step 4: Select the top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit combinations
    try:
        outfit = suggest_outfit(session["selected_item"], wardrobe)
    except Exception as exc:
        session["error"] = f"Outfit suggestion failed: {exc}"
        return session

    session["outfit_suggestion"] = outfit

    # Step 6: Generate fit card caption
    try:
        fit_card = create_fit_card(outfit, session["selected_item"])
    except Exception as exc:
        session["error"] = f"Fit card generation failed: {exc}"
        return session

    session["fit_card"] = fit_card

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

    print("\n\n=== Empty wardrobe path ===\n")
    session3 = run_agent(
        query="vintage graphic tee under $30",
        wardrobe=get_empty_wardrobe(),
    )
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"Found: {session3['selected_item']['title']}")
        print(f"\nOutfit (empty wardrobe): {session3['outfit_suggestion']}")
        print(f"\nFit card: {session3['fit_card']}")
