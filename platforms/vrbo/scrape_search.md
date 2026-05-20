# Platform Adapter: VRBO Search

## Objective
Navigate a VRBO search results page and extract the top-N listing cards in the normalized schema `{listing_id, url, title, price, rating, source_platform}`.

## Why VRBO
- VRBO skews toward owner-managed properties vs. management companies — higher chance of direct owner contact
- Property manager/owner names sometimes visible directly on search cards
- Integer listing IDs in URLs enable cross-referencing with Airbnb hit detection from reverse-image searches

## Inputs
- `search_url` — VRBO search URL, e.g. `https://www.vrbo.com/search/keywords:valencia-spain/arrival:2025-06-01/departure:2025-06-08`
- `top_n` — max listings to extract (default 5)

## Tools Used
- Playwright MCP (`browser_navigate`, `browser_evaluate`, `browser_snapshot`, `browser_scroll`)

## Procedure

### 1. Navigate
```
browser_navigate("<search_url>")
```
Wait for `networkidle`. VRBO may show a cookie consent modal:
```js
document.querySelector('[data-stid="apply-date-picker"], [aria-label="Accept"]')?.click()
```

### 2. Scroll to Load Cards
VRBO lazy-loads listing cards. Scroll down before evaluating:
```js
async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 5; i++) {
    window.scrollBy(0, 800);
    await sleep(600);
  }
}
```

### 3. Extract Listing Cards
```js
() => {
  const cards = Array.from(document.querySelectorAll('[data-stid="property-listing"], [itemprop="itemListElement"], [class*="PropertyCard"]'));
  return cards.slice(0, TOP_N).map(card => {
    const a = card.querySelector('a[href*="/vacation-rentals/"], a[href*="/homeaway/"]');
    const href = a?.href || '';
    // VRBO integer ID is in path: /vacation-rentals/p12345678
    const id = href.match(/\/p(\d+)/)?.[1] || href.match(/\/(\d{6,})/)?.[1] || '';
    const title = card.querySelector('[data-stid="content-hotel-title"], h3, [class*="title"]')
                       ?.textContent?.trim() || '';
    const price = card.querySelector('[data-stid="content-hotel-price"], [class*="price"]')
                       ?.textContent?.trim() || '';
    const rating = card.querySelector('[class*="rating"], [aria-label*="out of"]')
                        ?.textContent?.trim()?.match(/[\d.]+/)?.[0] || '';
    return {
      listing_id: id,
      url: href.split('?')[0],
      title,
      price,
      rating,
      source_platform: 'VRBO',
    };
  }).filter(c => c.listing_id);
}
```

### 4. Normalize Output
```json
{
  "listing_id": "12345678",
  "url": "https://www.vrbo.com/vacation-rentals/p12345678",
  "title": "Sunny Valencia Apartment, Steps from City Centre",
  "price": "€72/night",
  "rating": "4.8",
  "source_platform": "VRBO"
}
```

## Photo Extraction (downstream step)
VRBO listing pages show a hero photo with a "View all X photos" button. Clicking it opens a full-screen gallery overlay.

```js
// Click to open gallery
document.querySelector('[data-stid="open-gallery"], button[aria-label*="photo"]')?.click()
```

After the gallery opens, photos are in `[data-stid="media-gallery-item"] img` or `figure img`. CDN is `media.vrbo.com` or `resizer.vacationrentals.com` — no auth needed, strip `?` query params.

## Owner Contact Signals
VRBO has stronger owner-contact transparency than Airbnb:
- Listing page often shows "Hosted by [Name]" with a profile link
- "Contact the host" button may surface a contact form pre-filled with owner details
- Some listings show a direct phone number or website in the property description (common for professional managers)
- `[data-stid="host-information"]` or `.host-profile-section` typically carries name + response rate

## Gotchas
- VRBO search URL format changed in 2024 — the `keywords:` path format is current; the old `?destination=` query param still redirects but may not pre-filter properly
- Some VRBO cards are Expedia-grouped (same property on multiple brands) — the URL may redirect from vrbo.com to homeaway.com; capture the final URL after redirect
- VRBO aggressively blocks headless browsers; the persistent Firefox profile with prior VRBO visits reduces friction, but a visible window is strongly recommended
- In Spain, VRBO inventory is thinner than Booking.com or Airbnb — results may be sparse for Valencia; try expanding the search radius or removing arrival/departure date filters

## Reference Test
Search: `https://www.vrbo.com/search/keywords:valencia-spain`
Expected: 10–30 results; look for listings with "Managed by" or owner first names in titles
