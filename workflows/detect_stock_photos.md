# Workflow: Detect Stock/Fake Photos

## Objective
After collecting reverse-image-search hit domains for each listing photo, determine whether the listing uses genuine property photos or stock/third-party images. Stock photos are a strong signal that the host is misrepresenting the property.

## When to Run
Insert this step **after** `reverse_search_photos.md` and **before** `find_operator_contact.md` in the main pipeline.

## Inputs
- `photo_domain_lists` — a list (one entry per sampled photo) where each entry is the list of external domains returned by Yandex + Google Lens for that photo
  - Example: `[["archdaily.com", "shutterstock.com"], ["booking.com", "vrbo.com"]]`

## Tools Used
- `tools/classify_photo_hits.py` — pure Python, no browser needed

## Procedure

### Option A: Via CLI (agent-driven or one-off)

```bash
python tools/classify_photo_hits.py \
  --domains-json '[["shutterstock.com","archdaily.com"], ["booking.com"]]'
```

Output:
```json
{
  "per_photo": ["STOCK", "GENUINE"],
  "listing": "SOME_STOCK",
  "stock_count": 1,
  "total": 2
}
```

### Option B: Imported in Python runner (`run.py`)
```python
from tools.classify_photo_hits import run as classify_photos

result = classify_photos(photo_domain_lists)
# result["listing"]      → "GENUINE" | "SOME_STOCK" | "MOSTLY_STOCK" | "ALL_STOCK"
# result["stock_count"]  → int
```

## Stock Domain List
The classifier checks against these known stock photo platforms:

| Domain | Notes |
|--------|-------|
| shutterstock.com | Largest stock library |
| gettyimages.com | Premium stock |
| istockphoto.com | Getty sub-brand |
| unsplash.com | Free stock |
| pexels.com | Free stock |
| alamy.com | UK-based stock |
| dreamstime.com | Mid-tier stock |
| depositphotos.com | Budget stock |
| 123rf.com | Budget stock |
| stock.adobe.com | Adobe Stock |

## Output Shape
```json
{
  "per_photo": ["STOCK", "GENUINE", "MIXED"],
  "listing": "SOME_STOCK",
  "stock_count": 1,
  "total": 3
}
```

**Per-photo values:**
- `STOCK` — hit on a stock-photo domain (no booking platform hit alongside it)
- `GENUINE` — no stock hits; hits are booking platforms or property-specific sites
- `MIXED` — hit on both a stock site and a booking platform (unusual — flag for manual review)

**Listing aggregate:**
- `GENUINE` — zero stock photos detected
- `SOME_STOCK` — at least one but ≤50% of sampled photos are stock
- `MOSTLY_STOCK` — >50% of sampled photos are stock
- `ALL_STOCK` — every sampled photo is stock

## Decision Rule
| Listing result | Action |
|----------------|--------|
| `GENUINE` | Photos appear property-specific — proceed normally |
| `SOME_STOCK` | Proceed but note in `notes` column; contact finding still worthwhile |
| `MOSTLY_STOCK` | Strong misrepresentation signal — record and flag; contact finding still useful |
| `ALL_STOCK` | High misrepresentation confidence — warn user; update `notes` prominently |

## Result CSV Columns
Write three columns from this step:

| Column | Value |
|--------|-------|
| `photo_authenticity` | Listing aggregate (`GENUINE` / `SOME_STOCK` / `MOSTLY_STOCK` / `ALL_STOCK`) |
| `stock_photo_count` | `result["stock_count"]` |

## Gotchas
- Architecture/design sites (`archdaily.com`, `pinterest.com`, `dezeen.com`) are NOT in the stock domain list — they surface via the existing `SUSPICIOUS` verdict path in `classify_hits()`. Separating these from stock sites is intentional: an architecture press feature is a different signal than a Shutterstock watermarked image.
- A photo with zero hits is classified `GENUINE` (absence of evidence is not evidence of stock use).
- `MIXED` is rare in practice — it means the same photo appears on both a stock site and a booking platform, which could happen if an operator downloaded a stock photo and also used it on Booking.com.
