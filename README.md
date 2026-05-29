# Accommodation Finder

Hobby project: given a short-term rental listing URL or ID, find the operator behind the listing and surface direct contact information so you can book without the platform.

**How it works:**
1. Download photos from the listing
2. Reverse-image-search each photo on Yandex Images and Google Lens
3. Cross-platform hits expose the operator name
4. Scrape the operator's page for phone, email, and a direct booking link
5. Estimate the direct price (skipping platform fees) and write a negotiation note
6. Append everything to `results.csv`

## Architecture

WAT framework (Workflows → Agent → Tools):

```
workflows/   — Markdown SOPs describing each step
tools/       — Deterministic Python scripts (download, CSV append)
run.py       — Standalone orchestrator; no Claude needed
.tmp/        — Working files per listing (photos, intermediate JSON)
browser-profile/  — Firefox profile with login session persisted
results.csv  — Append-only output
```

## Setup

### 1. Install dependencies

```bash
pip install playwright requests
playwright install firefox
```

### 2. Seed the Firefox profile (one-time)

```bash
./tools/setup_firefox_profile.sh
```

This opens Firefox with the persistent profile. Log into your account on the source platform, dismiss any popups, then close the window. The session is saved to `./browser-profile/` and reused on every run.

For Google Lens: also log into a Google account in the same window — this dramatically reduces captcha frequency.

## Usage

```bash
# Single listing
python run.py --listing-id 1353198002579642941

# Top 10 listings from a search URL
python run.py --search-url "<search-url>" --top-n 10

# Skip Google Lens entirely (faster, no captcha risk)
python run.py --search-url "..." --yandex-only

# Re-run contact detection on photos you already have
python run.py --listing-id 1353198002579642941 --skip-download

# Headless (no browser window)
python run.py --listing-id 1353198002579642941 --headless
```

Results land in `results.csv` and `.tmp/<listing-id>/result.json`.

## Output columns

| Column | Description |
|---|---|
| `listing_id` / `listing_url` | Source listing |
| `listed_price_eur` | Nightly price scraped from search card |
| `cheapest_cross_platform_price_eur` | Price found on the cross-platform hit |
| `estimated_direct_price_eur` | `cross_platform × 0.92` (or `listed × 0.82` if no cross-platform baseline) |
| `managed_yn` | MANAGED / OWNER / UNKNOWN |
| `operator` | Company name (e.g. "Travel Habitat") |
| `operator_phone` / `operator_email` | Direct contact |
| `direct_booking_url` | Specific unit page on the operator's own site |
| `negotiation_notes` | One-line action ("Call +34 960 660 456, ref unit VA077-2. Est. direct €64 vs listed €80.") |
| `evidence_urls` | Cross-platform hit URLs that triggered the identification |

## Captcha handling

- **Yandex**: anti-bot tolerant for one-off uploads — runs clean.
- **Google Lens**: intermittently challenges Playwright-driven browsers. When detected, the script pauses and asks you to solve it in the browser window, then press Enter. Use `--yandex-only` to skip Lens entirely if you're running unattended.

## Known limitations

- Operator brand detection (`managed_yn`) uses a keyword list. Unknown brands will come through as `UNKNOWN` — open `evidence_urls` manually to check.
- The direct-price formula is a rough estimate (platform fees vary by listing and region).
- The photo lazy-loader is scroll-dependent; very large listings (30+ photos) may not fully load in the scroll loop. Increase `--photos` only if you need deeper sampling.

## Test fixture

Listing `1353198002579642941` — Valencia "Green & Natural Apartment" — is the canonical test target.
Photo 3 and 4 are the most distinctive (exterior/kitchen); photo 1 is a stock architecture shot shared across multiple listings and portfolios.

Expected result: `MANAGED`, operator = Travel Habitat, phone = +34 960 660 456, direct unit = VA077-2.
