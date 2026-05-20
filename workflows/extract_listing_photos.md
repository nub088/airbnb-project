# Workflow: Extract Listing Photos

## Objective
Given an Airbnb listing URL, collect every photo URL for the listing from the in-page "Photo tour" modal and (optionally) download the top N photos to `.tmp/<listing-id>/`.

## Inputs
- `listing_url` — e.g. `https://www.airbnb.ca/rooms/1353198002579642941?...`
- `top_n` (optional, default = all) — how many photos to download

## Tools Used
- Playwright MCP (`mcp__playwright__browser_navigate`, `browser_click`, `browser_evaluate`)
- `tools/download_airbnb_image.py` (for the download step)

## Procedure

### 1. Parse the listing ID
Extract `<LISTING_ID>` from the URL path: `/rooms/<LISTING_ID>`. It is used to (a) name the output dir `.tmp/<LISTING_ID>/` and (b) filter photo URLs (every listing image lives under `…/Hosting-<LISTING_ID>/…`).

### 2. Navigate
```
browser_navigate(listing_url)
```
Page title looks like `<Listing name> - <category> in <city>, <region>, <country> - Airbnb`. Capture it for the Sheets row later.

### 3. Open the photo modal
The hero shows 5 photos and a "Show all photos" button:
```
browser_click(target=button with name "Show all photos")
```
URL gains `&modal=PHOTO_TOUR_SCROLLABLE`. A dialog opens with `[role="dialog"][aria-label="Photo tour"]`. (The DOM also contains earlier empty `[role="dialog"]` siblings — match on the aria-label, not by index.)

### 4. Force lazy-load and collect URLs
The modal lazy-loads images as you scroll. Run via `browser_evaluate`:

```js
async () => {
  const LISTING_ID = '<LISTING_ID>';
  const dialog = Array.from(document.querySelectorAll('[role="dialog"]'))
    .find(d => d.getAttribute('aria-label') === 'Photo tour');
  if (!dialog) throw new Error('Photo tour dialog not found');

  // Largest scrollable descendant
  let scroller = dialog;
  for (const el of dialog.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
        && el.scrollHeight > el.clientHeight + 50
        && el.scrollHeight > scroller.scrollHeight) {
      scroller = el;
    }
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let prev = -1, stable = 0;
  for (let i = 0; i < 40; i++) {
    scroller.scrollTop = scroller.scrollHeight;
    await sleep(500);
    if (scroller.scrollTop === prev) { if (++stable > 2) break; } else { stable = 0; }
    prev = scroller.scrollTop;
  }

  const urls = Array.from(dialog.querySelectorAll('img'))
    .map(i => i.src)
    .filter(s => s && s.includes(`Hosting-${LISTING_ID}`))
    .map(u => u.split('?')[0]); // strip ?im_w=... — bare URL serves the original
  return [...new Set(urls)];
}
```

### 5. Download
For each URL (or the first `top_n`):
```
python tools/download_airbnb_image.py --listing-id <LISTING_ID> --url <URL>
```
The tool writes to `.tmp/<LISTING_ID>/photo-<n>.jpg`. The muscache CDN is public — no cookies / auth needed.

## Output
- File: `.tmp/<LISTING_ID>/photo_urls.txt` (one URL per line, full set)
- Files: `.tmp/<LISTING_ID>/photo-1.jpg` … `photo-N.jpg`
- Returns to caller: listing title, listing ID, count of photos, list of downloaded file paths.

## URL Pattern Reference
```
https://a0.muscache.com/im/pictures/hosting/Hosting-<LISTING_ID>/original/<UUID>.jpeg[?im_w=<width>]
```
- Strip `?im_w=…` to get the original-resolution image; or set `im_w=1440` or `2048` for a large but cached variant.
- Filter out non-listing images: host avatar (`/pictures/user/User/…`), platform icons (`/airbnb-platform-assets/…`), verified-feature thumbnails. The `Hosting-<LISTING_ID>` substring filter handles all of these.

## Gotchas Learned
- `browser_snapshot` (the a11y tree) does **not** include `img.src`. Always use `browser_evaluate` to read URLs.
- The modal is not always the first `[role="dialog"]` — match by `aria-label="Photo tour"`.
- Hero gallery shows only 5 photos. The modal contained 20 for the Valencia test listing; large listings can have 30+.
- Lazy-load needs the scroll-until-stable loop; a single `scrollTop = scrollHeight` will miss the bottom batch.

## Reference Run
Test listing: Valencia "Green & Natural Apartment" (`/rooms/1353198002579642941`) → 20 unique photo URLs, hero shows 5, modal reveals the remaining 15. Saved to `.tmp/1353198002579642941/photo_urls.txt`.
