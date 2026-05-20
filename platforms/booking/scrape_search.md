# Platform Adapter: Booking.com Search

## Objective
Navigate a Booking.com search results page and extract the top-N listing cards in the normalized schema `{listing_id, url, title, price, rating, source_platform}`.

## Why Booking.com
- Operator/property names are more prominently displayed than on Airbnb (often includes management company name in the listing title or subtitle)
- Reviews and property addresses surface contact signals directly on the listing page
- Cross-listing with Airbnb is common for managed properties — if you find a property on both, you have strong operator confirmation

## Inputs
- `search_url` — Booking.com search URL, e.g. `https://www.booking.com/searchresults.html?ss=Valencia%2C+Spain&nflt=ht_id%3D220` (filter `ht_id=220` = Apartments)
- `top_n` — max listings to extract (default 5)

## Tools Used
- Playwright MCP (`browser_navigate`, `browser_evaluate`, `browser_snapshot`, `browser_scroll`)

## Procedure

### 1. Navigate
```
browser_navigate("<search_url>")
```
Wait for `networkidle`. Booking.com may show a cookie consent banner — dismiss it:
```js
document.querySelector('[id*="cookie-banner"] button, [aria-label*="Accept"]')?.click()
```

### 2. Extract Listing Cards
```js
() => {
  const cards = Array.from(document.querySelectorAll('[data-testid="property-card"]'));
  return cards.slice(0, TOP_N).map(card => {
    const a = card.querySelector('a[data-testid="title-link"], a[href*="/hotel/"]');
    const href = a?.href || '';
    // Booking.com hotel slug is the identifier (no integer ID exposed in URL)
    const slug = href.match(/\/hotel\/[a-z]{2}\/([^/?]+)/)?.[1] || '';
    const title = card.querySelector('[data-testid="title"]')?.textContent?.trim() || '';
    const price = card.querySelector('[data-testid="price-and-discounted-price"], .bui-price-display__value')
                       ?.textContent?.trim() || '';
    const rating = card.querySelector('[data-testid="review-score"]')
                        ?.textContent?.trim()?.match(/[\d.]+/)?.[0] || '';
    return {
      listing_id: slug,
      url: href.split('?')[0],
      title,
      price,
      rating,
      source_platform: 'BOOKING',
    };
  }).filter(c => c.listing_id);
}
```

### 3. Normalize Output
Each card must conform to the shared schema:
```json
{
  "listing_id": "barcelona-ab-apartment",
  "url": "https://www.booking.com/hotel/es/barcelona-ab-apartment.html",
  "title": "Barcelona AB Apartment",
  "price": "€85",
  "rating": "8.9",
  "source_platform": "BOOKING"
}
```
Note: Booking.com uses string slugs, not integer IDs. Use the slug as `listing_id`.

## Photo Extraction (downstream step)
Booking.com listing pages have a photo gallery accessible via the main hero image or a "Photos" tab. The photo grid is not inside a dialog modal like Airbnb — it loads inline.

Selector for photos: `[data-testid="photo-grid"] img, .bh-photo-grid img, .hotel-photos img`

The image CDN is `cf.bstatic.com` — photos have no authentication requirement. Strip `?` query params to get original resolution.

## Operator Name Signals
Booking.com often reveals operator information directly in the listing:
- **Page title / H1**: Often the management brand name (e.g., "Blueground | Modern Studio Valencia")
- **"Hosted by" section**: `[data-testid="host-name"]` or text matching "Managed by"
- **Review author context**: Guests sometimes name the management company in reviews

## Gotchas
- Booking.com lazy-loads cards; wait for `[data-testid="property-card"]` to appear before evaluating
- The cookie consent overlay (`#onetrust-accept-btn-handler` or similar) blocks interaction until dismissed
- Some cards are "Genius deals" or "Sponsored" — they appear in the same container, filter by presence of a real URL slug
- Search URLs degrade gracefully: if `nflt` (filter) params are stripped, you still get results but with more hotel/non-apartment types mixed in
- Price shown is per-night; may be in local currency depending on browser locale — the persistent Firefox profile should be set to EUR for consistency

## Reference Test
Search: `https://www.booking.com/searchresults.html?ss=Valencia%2C+Spain&nflt=ht_id%3D220`
Expected: apartment listings with operator names often visible in title (e.g., "Travel Habitat", "Blueground", "Sonder")
