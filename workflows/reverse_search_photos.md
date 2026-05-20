# Workflow: Reverse-Search Photos

## Objective
For each downloaded listing photo, run a reverse-image search on **Yandex Images** and **Google Lens** and return any non-Airbnb hits (owner sites, other booking platforms, real estate listings, architecture/press features) that hint at the underlying real property.

## Inputs
- `listing_id` — the Airbnb listing ID; photos are at `.tmp/<listing_id>/photo-<n>.jpg`
- `photo_indices` — which photos to search (default = first 2, per the v1 cap)

## Tools Used
- Playwright MCP (`browser_navigate`, `browser_evaluate`, `browser_file_upload`, `browser_tabs`)

## Procedure

For each photo `.tmp/<listing_id>/photo-<n>.jpg`:

### A. Yandex Images (primary — captcha-free)

1. `browser_navigate("https://yandex.com/images/")`
2. Click the camera/"Image search" button in the search bar (`button[aria-label="Image search"]` or `getByRole('button', {name: 'Image search'})`).
3. The file input is hidden. Trigger it via `browser_evaluate`:
   ```js
   () => document.querySelector('input.CbirCore-FileInput[type="file"]').click()
   ```
   This opens the OS file chooser → Playwright reports `Modal state: File chooser`.
4. `browser_file_upload(["<absolute_path_to_photo>"])`
5. Yandex redirects to `https://yandex.com/images/search?cbir_id=…&rpt=imageview&cbir_page=search-by-image`.
6. Wait ~2 s, then extract results via `browser_evaluate`:
   ```js
   () => {
     const sections = {};
     // Section: Sites containing this image
     const sitesSection = Array.from(document.querySelectorAll('[class*="CbirSites"], [class*="CbirSection"]'))
       .find(s => /^Sites\b/i.test(s.querySelector('h2,h3')?.textContent || ''));
     // Section: Similar images
     const simSection = document.querySelector('[class*="CbirSimilarList"]');
     // All outbound (non-yandex) result anchors
     const outbound = Array.from(document.querySelectorAll('a[href^="http"]'))
       .map(a => ({href: a.getAttribute('href'), text: a.textContent.trim().slice(0, 120)}))
       .filter(a => !/yandex\.|ya\.ru/.test(a.href));
     // Tag chips (Yandex's "Image appears to contain" guesses)
     const tags = Array.from(document.querySelectorAll('[class*="CbirTags"] a, [class*="CbirTags"] span'))
       .map(t => t.textContent.trim()).filter(Boolean);
     return {outbound, tags};
   }
   ```
7. Filter `outbound` for interesting hits:
   - **Non-Airbnb domains** (drop `airbnb.*` and `muscache.com`).
   - Yandex appends `?utm_source=yandexsmartcamera` to result URLs — strip for the Sheets row.
   - Group by `URL().hostname` so multiple deep-links to the same site collapse.
8. **Agent judgment**: scan the result page (optionally `browser_take_screenshot`) to decide whether a hit is *the same property* (same room/angle) or just a visually similar stock photo. Only the former is a confirmed identification.

### B. Google Lens (secondary — captcha-prone)

> **Captcha risk:** Uploading from a fresh Playwright-driven Firefox triggers `https://www.google.com/sorry/index` (the "unusual traffic" challenge). Mitigation: log into Google once in the persistent profile (`./browser-profile/`), the same way Airbnb was seeded. Even then, Lens can intermittently captcha — when it happens, **stop and ask the user to solve it in-browser**, then continue. Once solved, the same browser context typically runs clean for a while.

1. `browser_navigate("https://lens.google.com/")` → redirects to `google.com/?olud&zx=…`.
2. Click `[aria-label="Search by image"]` (the lens icon in the Google homepage search bar).
3. Trigger the hidden Lens input:
   ```js
   () => document.querySelector('input[name="encoded_image"]').click()
   ```
4. `browser_file_upload(["<absolute_path>"])`.
5. **If** redirected to `google.com/sorry/index` → surface the captcha URL to the user, wait for them to solve it, then re-snapshot. Do not skip — the result is often worth waiting for.
6. The result page URL contains `udm=26` and `lns_mode=un`. Extract via `browser_evaluate`:
   ```js
   () => {
     const anchors = Array.from(document.querySelectorAll('a[href^="http"]'));
     const seen = new Set();
     return anchors
       .map(a => ({ href: a.href, text: (a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 140) }))
       .filter(r => !/google\.|gstatic|googleusercontent|googleadservices/.test(r.href))
       .filter(r => { if (seen.has(r.href)) return false; seen.add(r.href); return true; });
   }
   ```
7. The relevant section is headed **"Visual matches"** (Lens does not always render a separate "Exact matches" header; visually-identical results sit at the top of "Visual matches" alongside near-duplicates).
8. Filter out Airbnb's own international subdomains (`airbnb.com`, `airbnb.co.in`, `airbnb.co.nz`, `airbnb.ca`, etc. — match `/(^|\.)airbnb\./`) so we keep only cross-platform hits.
9. **High-signal domains** to flag specifically: `booking.com`, `vrbo.com`, `agoda.com`, `expedia.*`, `hotels.com`, plus any host's own domain. Anchor text is concatenated like `"Booking.comGREEN&FRESH Apartament…"` — the page's `<h3>` headings (extracted alongside) carry the cleaner title.

## Output Shape
Per photo:
```json
{
  "photo": ".tmp/<listing_id>/photo-1.jpg",
  "yandex": {
    "outbound_hits": [{"domain": "...", "url": "...", "text": "..."}],
    "tags": ["Bedroom", "Interior design", ...]
  },
  "google_lens": {
    "exact_matches": [...],
    "visual_matches": [...],
    "captcha_blocked": false
  }
}
```

## Decision Rule For "Real Property Identified"
A photo is a *confirmed hit* when **either** Yandex or Lens surfaces a non-Airbnb URL whose page shows the **same room from the same angle**. Stock-photo / wallpaper hits do not count. The agent records the URL + a one-line note ("VRBO listing same bedroom", "Architect's portfolio — Mallorca").

## Passing Domains to the Stock Classifier
After completing reverse searches for all photos in a listing, collect the hit domains per photo and pass them to `tools/classify_photo_hits.py`:

```python
# For each photo, build a list of all hit domains (Yandex + Lens combined)
photo_domain_lists = [
    [hit["domain"] for hit in (yandex_hits + lens_hits)],
    # ... one list per photo
]
```

Then run:
```bash
python tools/classify_photo_hits.py --domains-json '<json_of_photo_domain_lists>'
```

See `workflows/detect_stock_photos.md` for classification logic and CSV column mapping.

## Gotchas Learned
- Both Yandex and Google Lens use **hidden** `input[type="file"]` triggered by JS. `browser_click` on the visible camera button does **not** raise the Playwright file-chooser modal; you must `evaluate(() => input.click())` to trigger it, then call `browser_file_upload`.
- Yandex appears to be **anti-bot-tolerant** for one-off uploads — the Valencia test ran clean.
- Google **rate-limits** Playwright-driven Lens uploads aggressively. Even with a logged-in profile, expect intermittent captchas.
- Yandex enriches each outbound URL with `utm_source=yandexsmartcamera` — useful as a "definitely came from this Yandex search" marker, but strip before storing for cleaner deduplication.
- Yandex also returns a "Sites" section that lists every page hosting the image — often the most useful signal for "this Airbnb photo also lives on owner-website.com / archdaily.com / vrbo.com".

## Reference Run
Uploaded `.tmp/1353198002579642941/photo-1.jpg` (master bedroom from the Valencia "Green & Natural Apartment" listing) to Yandex →
- archdaily.com — "Portixol House / PMA Studio" (Mallorca architecture project)
- archivibe.com — same project's press feature
- a different Airbnb listing in Antwerpen, Belgium ("Brand new cottage in a vibrant area")

→ Strong signal the host is reusing third-party stock/architecture photos rather than photos of the actual Valencia property.

Same photo uploaded to Google Lens (after the user manually solved a `/sorry/index` captcha) →
- booking.com — "GREEN&FRESH Apartament, Valencia"
- agoda.com — "Travel Habitat Bioparc Apartments (València)"
- vrbo.com — "Casa Henriette, Olhão, Algarve"
- archdaily / pinterest hits for the Mallorca and Fabian Tan ("Jose House") architecture projects.

Combined read: the photo is in circulation across stock/architecture sites *and* is being used by what appear to be the same operator's listings on Airbnb / Booking / Agoda — exactly the cross-platform reuse this project is designed to surface.
