# Platform Adapter: Google Maps / Google Hotels

## Objective
Given a property address or area + property name, look up the property on Google Maps or Google Hotels to surface business listings, direct phone numbers, websites, and owner/operator identity signals that don't appear on Airbnb.

## Why Google Maps
- Properties managed by professional operators often have a Google Business Profile (GBP) listing with direct phone, website, and operating hours
- Address-based lookup can confirm the real-world location of a listing and link it to legal entity info (e.g., a tourism company's registered business)
- Google Hotels aggregates prices across Booking.com, Hotels.com, Expedia — a quick cross-platform price check without multiple site visits
- Even without a GBP, Google Maps Street View can visually confirm whether a property's Airbnb photos match the actual building

## Inputs
- `address_or_name` — property address or operator name (e.g., "Calle Colón 14, Valencia" or "Travel Habitat Valencia")
- `listing_context` — optional: the Airbnb listing title, to disambiguate multiple results

## Tools Used
- Playwright MCP (`browser_navigate`, `browser_evaluate`, `browser_snapshot`, `browser_click`)

## Procedure

### A. Google Maps Business Lookup

#### 1. Navigate
```
browser_navigate("https://www.google.com/maps/search/<address_or_name>")
```
Or more robustly, use the search bar:
```
browser_navigate("https://www.google.com/maps")
browser_fill_form({'[aria-label="Search Google Maps"]': "<address_or_name>"})
browser_press_key("Enter")
```

#### 2. Wait and Snapshot
Wait 2–3 seconds for the sidebar to load, then `browser_snapshot` to see what's displayed.

If multiple results appear (a list), click the most relevant one based on name/address match.

#### 3. Extract Business Panel
```js
() => {
  // Business name
  const name = document.querySelector('h1.DUwDvf, [data-attrid="title"]')?.textContent?.trim() || '';
  // Phone
  const phone = Array.from(document.querySelectorAll('[data-tooltip="Copy phone number"], [aria-label*="phone"]'))
    .map(el => el.getAttribute('aria-label') || el.textContent)
    .find(t => /\+?\d[\d\s\-]{7,}/.test(t)) || '';
  // Website
  const website = document.querySelector('a[data-tooltip="Open website"], a[aria-label*="website"]')?.href || '';
  // Address
  const address = document.querySelector('[data-item-id="address"] .fontBodyMedium')?.textContent?.trim() || '';
  // Category / type
  const category = document.querySelector('.fontBodyMedium.dmRWX, [jsaction*="category"]')?.textContent?.trim() || '';
  return { name, phone, website, address, category };
}
```

#### 4. Output Shape
```json
{
  "name": "Travel Habitat Valencia",
  "phone": "+34 960 660 456",
  "website": "https://travelhabitat.com",
  "address": "Calle del Maestro Gozalbo, 19, 46005 Valencia",
  "category": "Apartment rental agency"
}
```

### B. Google Hotels Price Lookup

#### 1. Navigate
```
browser_navigate("https://www.google.com/travel/hotels?q=<property_name>+valencia")
```

#### 2. Extract Hotel Cards
```js
() => {
  const cards = Array.from(document.querySelectorAll('[class*="dv6mMc"]'));
  return cards.slice(0, 5).map(card => {
    const name = card.querySelector('h2, [class*="name"]')?.textContent?.trim() || '';
    const price = card.querySelector('[class*="price"], [data-price]')?.textContent?.trim() || '';
    const rating = card.querySelector('[class*="rating"]')?.textContent?.trim() || '';
    return { name, price, rating };
  });
}
```

Note: Google Hotels selectors are frequently updated with class-name hashing. If the above fails, `browser_snapshot` and read the ARIA tree for price/name patterns.

### C. Street View Verification
To confirm a listing's photos match the actual property:

```
browser_navigate("https://www.google.com/maps/@<lat>,<lng>,3a,75y,0h,90t/data=!3m7!1e1!3m5!1s...")
```

Or from a Maps result: click "Street View" on the property panel, then `browser_take_screenshot` to capture the street view image for manual visual comparison against the Airbnb listing photos.

## Integration with Main Pipeline
Google Maps lookup is **address-driven**, not listing-ID-driven. Use it:
1. After an Airbnb or Booking.com scrape, if you have the property address (from listing description or cross-platform hit)
2. To resolve an operator name to a business phone/website when `find_operator_contact.md` returns limited info
3. As a secondary step to confirm `managed_yn = MANAGED` when a brand name is detected

## Normalized Output (for results.csv)
Map Google Maps result to existing CSV columns:
| Maps field | CSV column |
|------------|-----------|
| `name` | `operator` (if not already set) |
| `phone` | `operator_phone` (prefer over scraped Booking phone if more reliable) |
| `website` | `operator_website` |

`listing_id` stays as the source platform's ID. Set `source_platform = GOOGLE_MAPS` only if Google Maps was the primary search source; if used as an enrichment step, keep the original `source_platform`.

## Gotchas
- Google Maps aggressively changes its CSS class names; ARIA labels are more stable — prefer `[aria-label*="phone"]` over class-based selectors
- The business panel sidebar may not appear for residential addresses (only for registered businesses) — this is expected; not all properties have a GBP
- Google Hotels requires JavaScript and may take 4–6 seconds to fully render; wait longer than usual before evaluating
- Using the persistent Firefox profile logged into Google reduces the chance of hitting reCAPTCHA on Maps/Hotels
- Street View is not available for all addresses in Spain — `browser_snapshot` first to confirm the Street View button exists before trying to load it

## Reference Test
Search: "Travel Habitat Valencia" on Google Maps
Expected: Google Business Profile with phone +34 960 660 456, website travelhabitat.com, category "Apartment rental agency"
