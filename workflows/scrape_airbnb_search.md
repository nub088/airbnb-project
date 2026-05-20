# Workflow: Scrape Airbnb Search Results

## Objective
Given an Airbnb search-results URL, return the top N listings (URL, title, category-and-area, price blob, rating, beds/baths).

## Inputs
- `search_url` — e.g. `https://www.airbnb.ca/s/Valencia--Spain/homes`
- `top_n` (default 10) — first N cards from the first page (v1 does not paginate)

## Tools Used
- Playwright MCP (`browser_navigate`, `browser_evaluate`)

## Procedure

### 1. Navigate
```
browser_navigate(search_url)
```
First page typically renders ~18 unique cards (Airbnb's "20 stays" minus a few inline modules). If `top_n > 18` we need pagination — out of scope for v1.

### 2. Force lazy-load + extract cards
Run one `browser_evaluate` that scrolls once to the bottom, back to top, then walks every card.

```js
async (topN) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  window.scrollTo(0, document.body.scrollHeight); await sleep(800);
  window.scrollTo(0, 0); await sleep(400);

  const cards = Array.from(document.querySelectorAll('[data-testid="card-container"]'));
  const seen = new Set();
  const out = [];
  for (const card of cards) {
    const a = card.querySelector('a[href*="/rooms/"]');
    if (!a) continue;
    const m = a.getAttribute('href').match(/\/rooms\/(\d+)/);
    if (!m) continue;
    const id = m[1];
    if (seen.has(id)) continue;
    seen.add(id);

    const title = card.querySelector('[data-testid="listing-card-title"]')?.textContent.trim() || null;
    const name  = card.querySelector('[data-testid="listing-card-name"]')?.textContent.trim() || null;
    const price = card.querySelector('[data-testid="price-availability-row"]')?.textContent.trim() || null;
    const subtitles = Array.from(card.querySelectorAll('[data-testid="listing-card-subtitle"]'))
      .map(s => s.textContent.trim()).filter(Boolean);
    const rating = Array.from(card.querySelectorAll('span'))
      .map(s => s.textContent.trim())
      .find(t => /\d\.\d+ out of 5/.test(t)) || null;

    out.push({
      id,
      url: `https://www.airbnb.ca${a.getAttribute('href').split('?')[0]}`,
      title,           // "Apartment in Montolivet"
      name,            // "Green & Natural Apartment"
      price,           // "$1,659 CAD $1,523 CAD totalShow price breakdown Free cancellation"
      subtitles,       // ["Green & Natural Apartment", "2 bedrooms…3 beds…1 bath", "Sep 6–11"]
      rating,          // "4.9 out of 5 average rating, 103 reviews4.9 (103)"
    });
    if (out.length >= topN) break;
  }
  return out;
}
```

### 3. Hand off
For each item, the orchestrator (`identify_real_property.md`) passes `url` into `workflows/extract_listing_photos.md`. `title`, `name`, `price`, `rating` are kept for the Sheets row.

## Output Shape
Array of objects (see snippet above). Stable fields: `id`, `url`. The others may be `null` for some cards (e.g. promoted slots).

## Selector Cheatsheet
| What | Selector | Notes |
|---|---|---|
| Card root | `[data-testid="card-container"]` | One per listing |
| Listing link | `a[href*="/rooms/"]` (inside card) | `/rooms/<digits>` |
| Category line | `[data-testid="listing-card-title"]` | e.g. "Apartment in Montolivet" |
| Listing name | `[data-testid="listing-card-name"]` | The host-given title |
| Price | `[data-testid="price-availability-row"]` | Includes "Free cancellation" and original-vs-discount text — parse if needed |
| Beds/baths/dates | `[data-testid="listing-card-subtitle"]` (multiple) | Text doubles up (visible + sr-only) — dedupe |
| Rating | `span` text matching `/\d\.\d+ out of 5/` | No stable testid |

## Gotchas Learned
- ~125 `a[href*="/rooms/"]` anchors on the page (each card has multiple links — image + title + heart). Dedupe by `/rooms/<id>`.
- `aria-label` on the anchor is empty; rely on the testid spans for human-readable text.
- Subtitle texts include both the visible and screen-reader copy concatenated (`"2 bedrooms2 bedrooms3 beds, · 3 beds…"`). Either accept as-is for the Sheets row, or run a `.replace(/(.+?)\1/, '$1')` style dedupe.
- A single scroll-to-bottom is enough to hydrate page 1; the Photo-tour-style stable-loop is not needed here.
- This workflow only handles page 1 (~18 listings). Pagination (clicking the "Next" arrow at the bottom) is out of scope for v1; we cap runs at 10.

## Reference Run
Search `https://www.airbnb.ca/s/Valencia--Spain/homes` → 18 unique listing IDs returned, including the Valencia test listing `1353198002579642941` as result #1.
