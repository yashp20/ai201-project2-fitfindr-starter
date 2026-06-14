"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Filter by price ceiling
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Filter by size — case-insensitive substring match
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Score each listing by keyword overlap with the description
    keywords = set(re.sub(r"[^a-z0-9 ]", "", description.lower()).split())

    def _score(listing: dict) -> int:
        searchable = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            " ".join(listing.get("style_tags", [])),
            listing.get("category", ""),
            " ".join(listing.get("colors", [])),
            listing.get("brand", "") or "",
        ]).lower()
        tokens = set(re.sub(r"[^a-z0-9 ]", "", searchable).split())
        return len(keywords & tokens)

    scored = [(s, l) for l in listings if (s := _score(l)) > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handled gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, returns general styling advice for the item.
    """
    client = _get_groq_client()

    item_desc = (
        f"{new_item.get('title', 'item')} — ${new_item.get('price', '?')}, "
        f"{new_item.get('platform', '?')}, {new_item.get('condition', '?')} condition. "
        f"Size: {new_item.get('size', '?')}. "
        f"Colors: {', '.join(new_item.get('colors', []))}. "
        f"Style tags: {', '.join(new_item.get('style_tags', []))}."
    )

    if not wardrobe.get("items"):
        prompt = (
            f"I just found this secondhand piece: {item_desc}\n\n"
            "I haven't set up my wardrobe yet. Give me 1–2 general outfit ideas — "
            "describe what types of pieces pair well with this item, what vibe it suits, "
            "and one specific styling tip. Keep it conversational and concrete."
        )
    else:
        wardrobe_lines = []
        for w in wardrobe["items"]:
            line = (
                f"- {w['name']} "
                f"(colors: {', '.join(w['colors'])}, style: {', '.join(w['style_tags'])})"
            )
            if w.get("notes"):
                line += f" — {w['notes']}"
            wardrobe_lines.append(line)

        prompt = (
            f"I just found this secondhand piece: {item_desc}\n\n"
            f"My current wardrobe:\n" + "\n".join(wardrobe_lines) + "\n\n"
            "Suggest 1–2 complete outfit combinations using this new piece with items "
            "from my wardrobe above. Name the specific pieces you're combining, describe "
            "the overall vibe, and give one styling tip. Keep it conversational."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a thrift-savvy personal stylist. Give specific, wearable "
                    "outfit suggestions that sound like advice from a knowledgeable friend, "
                    "not a fashion magazine."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=400,
    )

    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string.
    """
    if not outfit or not outfit.strip():
        return (
            "Cannot generate a fit card without an outfit suggestion. "
            "Please check the outfit step first."
        )

    client = _get_groq_client()

    item_name = new_item.get("title", "thrifted piece")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift platform")

    prompt = (
        f"Thrifted item: {item_name} — ${price} from {platform}.\n\n"
        f"Outfit context: {outfit}\n\n"
        "Write a 2–4 sentence Instagram/TikTok caption for this OOTD. Rules:\n"
        "- Casual, lowercase, authentic — sounds like a real person, not a brand\n"
        "- Mention the item name, price, and platform naturally (each exactly once)\n"
        "- Capture the specific vibe of this outfit in concrete terms\n"
        "- Use 1–2 emojis max, no hashtags\n"
        "Return ONLY the caption text, nothing else."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You write authentic, casual fashion social media captions.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
        max_tokens=150,
    )

    return response.choices[0].message.content.strip()
