# Workflow: Identify Real Property (Orchestrator)

## Objective
Top-level SOP. Given an Airbnb search URL, identify whether any of the top listings can be matched to a real property (owner site, other booking platform, real-estate listing, architecture/press feature) by reverse-searching their photos.

## Inputs
- `search_url` — required, e.g. `https://www.airbnb.ca/s/Valencia--Spain/homes`
- `top_n_listings` — default 10 (v1 cap)
- `top_n_photos` — default 2 per listing (v1 cap → 20 reverse searches/run)

## Tools Used
- Playwright MCP (browser navigation, file upload)
- `tools/download_airbnb_image.py`
- `tools/append_to_sheet.py` (added in a later step; until then, stdout)

## Procedure

### 1. Scrape the search page
Run `workflows/scrape_airbnb_search.md` on `search_url` with `top_n = top_n_listings`.
Returns an array of `{id, url, title, name, price, rating, subtitles}`.

### 2. Per listing — extract photos
For each listing (in order):

a. Run `workflows/extract_listing_photos.md` with `listing_url`.
   Returns the full photo URL list and writes them to `.tmp/<id>/photo_urls.txt`.

b. Download just the first `top_n_photos`:
   ```bash
   python tools/download_airbnb_image.py \
     --listing-id <id> \
     --urls-file <(head -n <top_n_photos> .tmp/<id>/photo_urls.txt)
   ```
   (Or build a sliced temp file if the agent's shell can't process-substitute.)

### 3. Per photo — reverse-search
For each of the downloaded `.tmp/<id>/photo-1.jpg` … `photo-<top_n_photos>.jpg`:

Run `workflows/reverse_search_photos.md`. Per photo it returns Yandex + Lens findings.

The agent decides per photo whether to mark it a *hit*. Rule of thumb:
- Same room from the same angle on a non-Airbnb domain → **hit** (record the URL + one-line note).
- Only stock-photo / mood-board hits (Pinterest, ArchDaily, Houzz with no booking context) → **suspicious** but not a confirmed property match — note it ("photo reused from <source>") and move on.
- No non-Airbnb hits → **clean**.

### 3b. Per listing — detect stock photos
After all photos are reverse-searched, collect the hit domains per photo and run the stock classifier:

```bash
python tools/classify_photo_hits.py \
  --domains-json '<json_array_of_domain_lists>'
```

Record the output in the row:
- `photo_authenticity` ← `result["listing"]` (GENUINE / SOME_STOCK / MOSTLY_STOCK / ALL_STOCK)
- `stock_photo_count` ← `result["stock_count"]`

See `workflows/detect_stock_photos.md` for full procedure, decision rules, and gotchas.

### 4. Per listing — classify and find direct contact (if hit found)

If **any** photo returned a cross-platform booking hit (Booking, Agoda, VRBO, Expedia, etc.):

Run `workflows/find_operator_contact.md` with:
- `hit_url` = the first booking-platform hit URL
- `hit_platform` = the domain (e.g. `booking`, `agoda`)
- `listing_id` = current listing ID

This adds `managed_yn`, `operator_website`, `operator_phone`, `direct_booking_url`, and `negotiation_notes` to the row.

**Skip this step** if the only hits are stock-photo / architecture portfolio sites (ArchDaily, Pinterest, Houzz) with no booking context — those are `SUSPICIOUS` classification, not a confirmed managed listing.

### 5. Per listing — emit a row
Once both photos for a listing are done, the agent emits one summary row:

| Field | Source |
|---|---|
| Listing URL | step 1, `url` |
| Title | step 1, `title` + `name` |
| Price blob | step 1, `price` |
| Rating | step 1, `rating` |
| Photos sampled | `top_n_photos` |
| Match found? | YES / SUSPICIOUS / NO (across both photos) |
| Match URLs | Deduplicated list of non-Airbnb hit URLs |
| Managed? | MANAGED / OWNER / UNKNOWN (from find_operator_contact.md) |
| Operator | Company name or blank |
| Operator phone | Direct phone (E.164) |
| Direct booking URL | Specific unit page on operator site, or blank |
| Negotiation notes | One-line action ("Call +34 XXX, ask for unit VA077-2 direct rate") |
| Notes | One-line agent judgment ("Same property on booking.com as GREEN&FRESH", "Photos reused from ArchDaily", "No external hits") |
| Date checked | Today's date (UTC) |

Until `tools/append_to_sheet.py` is wired up (later step in the plan), print each row to stdout and to `.tmp/<id>/result.json` so the run is recoverable.

### 5. Stop conditions
- Stop early and surface to the user if:
  - Airbnb shows a CAPTCHA / login wall on a listing page.
  - Google Lens hits `/sorry/index` and the user is not available to solve it (skip just that photo's Lens leg and continue with Yandex; flag in notes).
  - The same `.tmp/<id>/` already has `result.json` from today — skip unless the user asks for a refresh.

## Output
- One row per listing (stdout / JSON / Sheets).
- Working files persisted under `.tmp/<id>/`: `photo_urls.txt`, `photo-*.jpg`, `result.json`.

## V1 Limits (Explicit)
- Single page of search results — no pagination.
- 10 listings × 2 photos = 20 reverse searches per run.
- Interactive (the agent runs in a Claude session, with the user available to clear captchas).
- Sheets export is a *later* step in the plan; for now results land in `.tmp/` and stdout.

## Reference Run
Search `https://www.airbnb.ca/s/Valencia--Spain/homes` → first listing is `1353198002579642941` ("Green & Natural Apartment", €/$1,659 CAD, 4.9). Photo-1 (master bedroom) returned:
- **Yandex**: archdaily.com + archivibe.com (Mallorca "Portixol House"), plus an Airbnb listing in Antwerp using the same photo.
- **Google Lens** (after user solved a captcha): booking.com `GREEN&FRESH Apartament`, agoda.com `Travel Habitat Bioparc Apartments`, vrbo.com `Casa Henriette Olhão`.

Verdict: `SUSPICIOUS` — the same image is reused across multiple Airbnb/Booking/Agoda listings and originates from an architecture project, so this Valencia listing's "real" property identity isn't unambiguous from this photo alone. Sampling photo-2 (a different room) would tighten the conclusion.
