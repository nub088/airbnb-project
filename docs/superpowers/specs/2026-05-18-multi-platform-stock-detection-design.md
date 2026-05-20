# Design: Multi-Platform Expansion + Stock Photo Detection

**Date:** 2026-05-18  
**Status:** Implemented

---

## Context

The project started as an Airbnb-only pipeline: scrape listings → reverse-image-search photos → find operator contact. Two extensions were added:

1. **Multi-platform input** — accept listings from Booking.com, VRBO, Idealista/Fotocasa, and Google Maps as source platforms, not just as lookup targets
2. **Stock photo detection** — identify when listing photos are stock images (Shutterstock, Getty, etc.) rather than genuine property photos

---

## Architecture

### Platform Adapters (`platforms/`)

Each source platform gets its own Markdown SOP under `platforms/{name}/scrape_search.md`. Every adapter normalizes to the same listing card schema:

```json
{
  "listing_id": "...",
  "url": "...",
  "title": "...",
  "price": "...",
  "rating": "...",
  "source_platform": "BOOKING | VRBO | IDEALISTA | GOOGLE_MAPS | AIRBNB"
}
```

The Python runner (`run.py`) supports `airbnb`, `booking`, and `vrbo` via the `--platform` flag. Idealista and Google Maps are agent-driven (Playwright MCP) via their workflow SOPs — automated Python support can be added later.

### Stock Photo Classifier (`tools/classify_photo_hits.py`)

Pure Python (stdlib only). Consumes per-photo domain lists from the existing reverse-search step — no new browser automation needed.

**Per-photo classification:** `STOCK | GENUINE | MIXED`  
**Per-listing aggregate:** `GENUINE | SOME_STOCK | MOSTLY_STOCK | ALL_STOCK`

Stock domains checked: shutterstock.com, gettyimages.com, istockphoto.com, unsplash.com, pexels.com, alamy.com, dreamstime.com, depositphotos.com, 123rf.com, stock.adobe.com

---

## Files Changed

| File | Change |
|------|--------|
| `tools/classify_photo_hits.py` | New — domain-list stock classifier |
| `tools/append_to_sheet.py` | Updated COLUMNS: added `source_platform`, `photo_authenticity`, `stock_photo_count` |
| `workflows/detect_stock_photos.md` | New — stock detection SOP |
| `workflows/reverse_search_photos.md` | Added section: passing domains to classifier |
| `workflows/identify_real_property.md` | Added step 3b: stock photo detection |
| `platforms/booking/scrape_search.md` | New — Booking.com adapter SOP |
| `platforms/vrbo/scrape_search.md` | New — VRBO adapter SOP |
| `platforms/idealista/scrape_search.md` | New — Idealista/Fotocasa adapter SOP |
| `platforms/google_maps/scrape_search.md` | New — Google Maps adapter SOP |
| `run.py` | Added `--platform` flag, `scrape_search_booking()`, `scrape_search_vrbo()`, per-photo domain tracking, stock result in row |
| `results.csv` | Header updated with 3 new columns |

---

## Key Design Decisions

**Why separate stock detection from the existing SUSPICIOUS verdict?**  
The existing `classify_hits()` flags architecture/design sites (ArchDaily, Pinterest, Houzz) as SUSPICIOUS. Stock photos are a distinct signal: a photo from Shutterstock means the host deliberately chose a fake image, while an ArchDaily hit means they lifted it from an architecture project. Both matter, but they imply different things about the host's intent.

**Why domain-list rather than URL-list for stock detection?**  
The reverse-search step already normalizes to domains. Re-deriving domains from URLs in a second pass would be redundant. The classifier accepts domain strings directly and handles subdomain variations (`cdn.shutterstock.com` matches `shutterstock.com`).

**Why are Idealista and Google Maps agent-only?**  
Both use aggressive anti-bot measures (Cloudflare on Idealista, reCAPTCHA on Google). The persistent Firefox profile reduces friction for agent-driven use but doesn't eliminate it. Automating these in Python requires more upfront research into their DOM structures. The Markdown SOPs document everything needed to add Python support later.

**Why slugs instead of integer IDs for Booking.com?**  
Booking.com doesn't expose integer IDs in URLs or DOM — the property slug (`hotel/es/property-name`) is the stable identifier. It's less useful for cross-referencing than integer IDs, but it's what's available.
