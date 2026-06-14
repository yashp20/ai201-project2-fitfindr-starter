# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items that match a keyword description, optional size filter, and optional maximum price. Returns a scored, ranked list of matches — best match first.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g., "vintage graphic tee"). Matched against title, description, style_tags, category, colors, and brand fields using word-level overlap scoring.
- `size` (str | None): Size string to filter by (e.g., "M", "S/M", "W30"). Matching is case-insensitive substring match so "M" matches "S/M". Pass None to skip size filtering.
- `max_price` (float | None): Maximum acceptable price (inclusive). Pass None to skip price filtering.

**What it returns:**
A list of listing dicts, each containing: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Sorted by keyword-overlap score descending. Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
If the returned list is empty, the agent sets `session["error"]` to a message like: "No listings found for '[description]'[size/price context]. Try broadening your search — remove the size filter or increase your price range." The agent returns early without calling suggest_outfit or create_fit_card.

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific thrifted item and the user's wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations. If the wardrobe is empty, offers general styling advice instead of outfit combos.

**Input parameters:**
- `new_item` (dict): A listing dict (the item the user is considering buying). Used for its title, price, platform, size, colors, and style_tags.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key containing a list of wardrobe item dicts (each with name, category, colors, style_tags, notes). May have an empty `'items'` list.

**What it returns:**
A non-empty string with outfit suggestions from the LLM. If the wardrobe has items, the suggestions reference specific named pieces from the wardrobe. If the wardrobe is empty, the suggestions describe general styling directions and what types of pieces pair well with the new item.

**What happens if it fails or returns nothing:**
If the wardrobe is empty, the function does NOT crash — it switches to a general-styling prompt and still returns useful advice. If the LLM call fails (network error, etc.), the exception propagates up to `run_agent`, which catches it and stores an error message in `session["error"]`.

---

### Tool 3: create_fit_card

**What it does:**
Generates a 2–4 sentence casual social-media caption (Instagram/TikTok OOTD style) for the discovered thrifted outfit. Each call should produce a distinct result — the LLM is called with temperature=1.0.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from suggest_outfit(). Must be non-empty.
- `new_item` (dict): The listing dict for the thrifted item. Used for title, price, and platform.

**What it returns:**
A 2–4 sentence string in lowercase, casual tone, mentioning the item name, price, and platform once each, no hashtags, with 1–2 emojis. Sounds like a real OOTD post, not a product description.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the function returns the error string: "Cannot generate a fit card without an outfit suggestion. Please check the outfit step first." — no exception raised.

---

### Additional Tools (if any)

<!-- None — three required tools only -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` follows a strict conditional sequence based on what each tool returns:

1. **Parse the query** using regex to extract `description`, `size`, and `max_price`. Store result in `session["parsed"]`.

2. **Call search_listings(description, size, max_price)**.
   - Store result in `session["search_results"]`.
   - **Branch check:** `if len(session["search_results"]) == 0` → set `session["error"]` to a descriptive message and `return session` immediately. Do NOT proceed to step 3.
   - Otherwise: set `session["selected_item"] = session["search_results"][0]` (top result).

3. **Call suggest_outfit(session["selected_item"], session["wardrobe"])**.
   - Store result in `session["outfit_suggestion"]`.
   - If an exception occurs, set `session["error"]` and return early.

4. **Call create_fit_card(session["outfit_suggestion"], session["selected_item"])**.
   - Store result in `session["fit_card"]`.

5. **Return session.**

The agent's behavior is therefore contingent on search results: an empty search result ends the loop immediately, preventing downstream tools from receiving empty input.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (initialized by `_new_session()`) is the shared state for the entire interaction. It is passed by reference through the planning loop:

- After `search_listings` runs, its results are stored in `session["search_results"]`. The top result is pulled out and stored in `session["selected_item"]`.
- `suggest_outfit` receives `session["selected_item"]` (already a full listing dict) and `session["wardrobe"]` (passed into `run_agent` as a parameter). Its output goes into `session["outfit_suggestion"]`.
- `create_fit_card` receives `session["outfit_suggestion"]` (a string) and `session["selected_item"]` (for item metadata). Its output goes into `session["fit_card"]`.
- If any step sets `session["error"]`, the loop returns early — downstream fields remain `None`.
- At the end, `handle_query()` in `app.py` reads `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` to populate the three Gradio output panels.

No re-prompting of the user is needed between steps because all state is stored in the session.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (empty list returned) | Sets `session["error"]` to: "No listings found for '[description]'. Try removing the size filter or raising your price limit." Returns session early — suggest_outfit and create_fit_card are never called. |
| suggest_outfit | Wardrobe is empty (`wardrobe['items'] == []`) | Switches prompt to request general styling advice for the item type, rather than wardrobe-specific combos. Still returns a useful string — does not crash or return empty. |
| create_fit_card | `outfit` argument is empty or whitespace-only | Returns the error string "Cannot generate a fit card without an outfit suggestion. Please check the outfit step first." without calling the LLM or raising an exception. |

---

## Architecture

```
User query (natural language)
        │
        ▼
   _parse_query()  ──────────────────────────────────────────────────────────┐
   extracts description, size, max_price                                     │
        │                                                                    │
        ▼                                                                    │
Planning Loop (run_agent)                                                    │
        │                                                                    │
        ├─► search_listings(description, size, max_price)                    │
        │       │                                                            │
        │       │  results == []                                             │
        │       ├──► session["error"] = "No listings found..." ──► return ──┤
        │       │                                                            │
        │       │  results = [item, ...]                                     │
        │       ▼                                                            │
        │   session["search_results"] = results                             │
        │   session["selected_item"]  = results[0]                          │
        │       │                                                            │
        ├─► suggest_outfit(selected_item, wardrobe)                         │
        │       │                                                            │
        │       │  wardrobe["items"] == []                                  │
        │       ├──► LLM: general styling advice for item type              │
        │       │                                                            │
        │       │  wardrobe["items"] has entries                            │
        │       ├──► LLM: specific outfit combos using named wardrobe items │
        │       │                                                            │
        │       ▼                                                            │
        │   session["outfit_suggestion"] = <LLM string>                     │
        │       │                                                            │
        ├─► create_fit_card(outfit_suggestion, selected_item)               │
        │       │                                                            │
        │       │  outfit == ""                                              │
        │       ├──► return error string (no LLM call) ───────────────────►─┘
        │       │                                                            │
        │       │  outfit is valid                                           │
        │       └──► LLM (temperature=1.0): casual OOTD caption             │
        │               │                                                    │
        │           session["fit_card"] = <caption string>                  │
        │               │                                                    │
        └───────────────▼                                                    │
                  return session  ◄─────────────────────────────────────────┘
                        │
                        ▼
              handle_query() in app.py
              formats session fields into
              three Gradio output panel strings
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings**: Gave Claude the Tool 1 spec (inputs, return value, failure mode) and the load_listings() signature from data_loader.py. Asked it to implement keyword scoring using word-level set intersection between the description and listing text fields. Verified the output handles None parameters, returns `[]` on no match, and sorts by score. Tested with 3 queries: "vintage graphic tee" (should return results), "designer ballgown size XXS under $5" (should return []), and "jacket under $10" (tests price filter).

- **suggest_outfit**: Gave Claude the Tool 2 spec and wardrobe_schema.json structure. Asked it to call Groq llama-3.3-70b-versatile, with two distinct prompt branches based on whether `wardrobe['items']` is empty. Verified the generated code formats wardrobe items clearly for the LLM and handles the empty case without crashing.

- **create_fit_card**: Gave Claude the Tool 3 spec and style guidelines. Asked it to use temperature=1.0 to ensure caption variation, guard against empty outfit strings, and return only the caption text (no preamble). Ran it 3 times on the same input and confirmed outputs differed.

**Milestone 4 — Planning loop and state management:**

Gave Claude the Architecture diagram above and the Planning Loop + State Management sections. Asked it to implement `run_agent()` following the step-by-step logic in the diagram — specifically the `if len(results) == 0: return early` branch. Verified the generated code: (a) uses `_new_session()`, (b) stores each result in the correct session key, (c) does not call suggest_outfit when search returns empty, (d) uses `_parse_query()` for parameter extraction. Tested the happy path and the no-results path using the `if __name__ == "__main__"` block in agent.py.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** `_parse_query()` extracts `description="vintage graphic tee"`, `size=None`, `max_price=30.0`. Stored in `session["parsed"]`.

**Step 2:** `search_listings("vintage graphic tee", size=None, max_price=30.0)` is called. The function filters listings to price ≤ $30, then scores each by keyword overlap with "vintage graphic tee". The top result is something like `"Graphic Tee — 2003 Tour Bootleg Style" ($24, depop)` which scores 3 (matches "graphic", "tee", "vintage"). Results stored in `session["search_results"]`. `session["selected_item"]` set to the top result.

**Step 3:** Since `session["search_results"]` is non-empty (no early return), `suggest_outfit(selected_item, wardrobe)` is called. The wardrobe has 10 items including "Baggy straight-leg jeans, dark wash" and "Chunky white sneakers". The LLM returns something like: "Pair this faded bootleg tee with your baggy dark-wash jeans and chunky white sneakers for an easy 90s streetwear look. Tuck the front corner of the tee slightly and leave the back out for shape. You could also layer your black cropped zip hoodie on top on colder days for that athletic-grunge crossover vibe." Stored in `session["outfit_suggestion"]`.

**Step 4:** `create_fit_card(outfit_suggestion, selected_item)` is called with the outfit string and the item dict. The LLM produces: "found this 2003 tour bootleg tee on depop for $24 and it was made for my jeans 🖤 styled it half-tucked with my chunky sneakers and it's giving everything i wanted. full look incoming." Stored in `session["fit_card"]`.

**Final output to user:** Three panels populate in the Gradio UI:
- **Top listing found**: Title, price ($24.00), platform (Depop), condition, size, colors, style tags, and description of the tee.
- **Outfit idea**: The multi-sentence LLM suggestion referencing specific wardrobe pieces.
- **Your fit card**: The casual OOTD caption ready to copy-paste.
