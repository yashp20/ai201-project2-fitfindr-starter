# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. The agent searches mock thrift listings, suggests outfit combinations based on the user's wardrobe, and generates a shareable OOTD caption — all in one natural-language interaction.

---

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# or: .venv\Scripts\activate    # Windows CMD
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Open `http://localhost:7860` in your browser.

Run tests:

```bash
pytest tests/
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | `str` | Keywords describing the item (e.g., "vintage graphic tee") |
| `size` | `str \| None` | Size filter — case-insensitive substring match against listing size field. `None` skips size filtering. |
| `max_price` | `float \| None` | Maximum price inclusive. `None` skips price filtering. |

**Returns:** `list[dict]` — matching listing dicts sorted by keyword-overlap score (best match first). Each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` on no match — never raises.

**Purpose:** Filters the 40-item mock dataset and ranks results by relevance to the user's request.

---

### `suggest_outfit(new_item, wardrobe)`

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | `dict` | A listing dict — the item the user is considering buying |
| `wardrobe` | `dict` | A wardrobe dict with an `'items'` key (list of wardrobe item dicts). May be empty. |

**Returns:** `str` — 1–2 outfit suggestions from the Groq LLM. If the wardrobe is empty, returns general styling advice for the item type. Always a non-empty string.

**Purpose:** Gives the user concrete outfit ideas, either using their existing wardrobe or general styling guidance for new users.

---

### `create_fit_card(outfit, new_item)`

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | `str` | The outfit suggestion from `suggest_outfit`. Must be non-empty. |
| `new_item` | `dict` | The listing dict — used for title, price, and platform metadata |

**Returns:** `str` — A 2–4 sentence casual Instagram/TikTok OOTD caption. Mentions item name, price, and platform once each. Uses lowercase and 1–2 emojis. Called with LLM temperature=1.0 so output varies across calls. If `outfit` is empty, returns a descriptive error string instead.

**Purpose:** Generates a shareable social-media caption that captures the outfit vibe in the user's voice.

---

## Planning Loop

The agent's planning loop in `run_agent()` follows a strict conditional sequence — not a fixed pipeline. It decides what to do next based on what each tool returns:

```
Step 1  Parse query (regex) → description, size, max_price

Step 2  search_listings(description, size, max_price)
        → results == []?  YES → set session["error"], return early
                          NO  → session["selected_item"] = results[0]

Step 3  suggest_outfit(selected_item, wardrobe)
        → session["outfit_suggestion"] = <LLM string>

Step 4  create_fit_card(outfit_suggestion, selected_item)
        → session["fit_card"] = <caption>

Step 5  return session
```

The critical branch is at Step 2: if `search_listings` returns an empty list, the agent sets an error message and returns immediately — `suggest_outfit` and `create_fit_card` are never called with empty input. This is the only real decision point because Steps 3 and 4 receive their inputs from the session, not from the user.

Query parsing uses regex (not an extra LLM call) to extract size tokens (`size M`, `S/M`, standalone `XL`, etc.) and price phrases (`under $30`, `below 40`). The remainder becomes the description.

---

## State Management

A single `session` dict (initialized by `_new_session()`) is the shared state for the entire interaction. Each step reads from and writes to it:

| Session key | Written by | Read by |
|-------------|-----------|---------|
| `session["parsed"]` | `_parse_query()` | `run_agent()` for tool parameters |
| `session["search_results"]` | `search_listings` result | branch check, `selected_item` extraction |
| `session["selected_item"]` | planning loop (Step 4) | `suggest_outfit`, `create_fit_card`, `handle_query` |
| `session["wardrobe"]` | `_new_session()` | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` result | `create_fit_card`, `handle_query` |
| `session["fit_card"]` | `create_fit_card` result | `handle_query` |
| `session["error"]` | any failing step | `handle_query` (controls which panels show) |

No information is re-requested from the user between steps. The item found in Step 2 flows directly into Step 3, and the outfit from Step 3 flows directly into Step 4.

---

## Error Handling

### `search_listings` — no results

**Trigger:** Impossible or overly specific query (wrong size, price too low, niche item not in dataset).

**Agent response:** Sets `session["error"]` to:
> `No listings found for "designer ballgown" in size XXS under $5. Try broadening your search — remove the size filter, raise your price limit, or use different keywords.`

The error includes what was searched and specific suggestions for what to change. `suggest_outfit` and `create_fit_card` are never called.

**Tested with:**
```
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```

---

### `suggest_outfit` — empty wardrobe

**Trigger:** User selects "Empty wardrobe (new user)" or their `wardrobe['items']` list is empty.

**Agent response:** The tool switches to a different LLM prompt that asks for general styling advice (what types of pieces pair well, what vibe fits, how to style it) rather than wardrobe-specific combinations. Returns a useful, non-empty string.

**Tested with:**
```
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
r = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(r[0], get_empty_wardrobe()))
"
# Output: general styling advice string, no exception
```

---

### `create_fit_card` — empty outfit string

**Trigger:** `outfit` argument is `""` or whitespace only.

**Agent response:** Returns the string:
> `Cannot generate a fit card without an outfit suggestion. Please check the outfit step first.`

No LLM call is made. No exception is raised.

**Tested with:**
```
python -c "
from tools import search_listings, create_fit_card
r = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', r[0]))
"
# Output: error message string
```

---

## AI Usage

### Instance 1 — `search_listings` implementation

I gave Claude the Tool 1 spec from `planning.md` (inputs, return value including field list, failure mode) and the `load_listings()` signature from `data_loader.py`. I asked it to implement keyword scoring using word-level set intersection across title, description, style_tags, category, colors, and brand fields.

What Claude produced was mostly correct but scored listings by counting raw character matches rather than word tokens, which caused partial matches (e.g., "M" matching "maximum"). I overrode this with `re.sub(r"[^a-z0-9 ]", "", text).split()` tokenization before computing set intersection, which produced clean keyword matching.

I verified by running: `search_listings("vintage graphic tee", None, None)` and checking that only items with those words in their fields appeared in results.

### Instance 2 — `run_agent` planning loop

I gave Claude my architecture diagram from `planning.md` and the Planning Loop + State Management sections. I asked it to implement `run_agent()` following the numbered steps and the early-return branch on empty search results.

The generated code called all three tools unconditionally before checking results — the branch logic was at the end rather than in the middle. I restructured it to match the diagram: `if not results: session["error"] = ...; return session` immediately after the search, before calling `suggest_outfit`. I also added per-step try/except blocks so individual tool failures produce clear error messages rather than stack traces in the UI.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── tests/
│   └── test_tools.py          # Pytest tests for all three tools
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # Three FitFindr tools
├── agent.py                   # Planning loop and session state management
├── app.py                     # Gradio UI
├── planning.md                # Design spec and agent diagram
└── requirements.txt
```
