#!/usr/bin/env python3
"""Standalone orchestrator: listing → reverse-image → operator contact → results.csv

Usage examples:

  # Run on a single Airbnb listing
  python run.py --listing-id 1353198002579642941

  # Run on top-N listings from a search URL (Airbnb default)
  python run.py --search-url "https://www.airbnb.com/s/Valencia--Spain/homes" --top-n 5

  # Run from a Booking.com search URL
  python run.py --platform booking --search-url "https://www.booking.com/searchresults.html?ss=Valencia"

  # Run from a VRBO search URL
  python run.py --platform vrbo --search-url "https://www.vrbo.com/search/keywords:valencia-spain"

  # Explicit photo count per listing (default 2)
  python run.py --listing-id 1353198002579642941 --photos 3

  # Skip photos you already have (re-run operator detection only)
  python run.py --listing-id 1353198002579642941 --skip-download

Options:
  --platform        Source platform: airbnb (default), booking, vrbo, idealista, google_maps
  --headless        Run Firefox without a visible window (default: visible so you can solve captchas)
  --yandex-only     Skip Google Lens (avoids captcha risk)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Add project root to path so we can import tools as a module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.classify_photo_hits import run as classify_photos

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).resolve().parent
TMP = ROOT / ".tmp"
BROWSER_PROFILE = ROOT / "browser-profile"
RESULTS_CSV = ROOT / "results.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def launch_browser(playwright, headless: bool):
    return playwright.firefox.launch_persistent_context(
        str(BROWSER_PROFILE),
        headless=headless,
        viewport={"width": 1280, "height": 900},
    )


def new_page(ctx):
    page = ctx.new_page()
    page.set_extra_http_headers({"User-Agent": UA})
    return page


# ---------------------------------------------------------------------------
# Step 1: Scrape Airbnb search page for listing IDs
# ---------------------------------------------------------------------------

def scrape_search(page, search_url: str, top_n: int) -> list[dict]:
    print(f"\n[search] Navigating to {search_url}")
    page.goto(search_url, wait_until="networkidle", timeout=30_000)
    time.sleep(2)

    listings = page.evaluate("""
    () => {
        const cards = Array.from(document.querySelectorAll('a[href*="/rooms/"]'));
        const seen = new Set();
        const results = [];
        for (const a of cards) {
            const m = a.href.match(/\\/rooms\\/(\\d+)/);
            if (!m) continue;
            const id = m[1];
            if (seen.has(id)) continue;
            seen.add(id);
            const title = a.querySelector('[data-testid="listing-card-title"], h3, h2')?.textContent?.trim() || '';
            const price = a.querySelector('[data-testid="price-availability-row"], [aria-label*="per night"]')?.textContent?.trim() || '';
            results.push({ id, url: 'https://www.airbnb.com/rooms/' + id, title, price });
            if (results.length >= """ + str(top_n) + """) break;
        }
        return results;
    }
    """)

    print(f"[search] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Step 1b: Scrape Booking.com search page
# ---------------------------------------------------------------------------

def scrape_search_booking(page, search_url: str, top_n: int) -> list[dict]:
    print(f"\n[search:booking] Navigating to {search_url}")
    page.goto(search_url, wait_until="networkidle", timeout=30_000)
    time.sleep(2)

    # Dismiss cookie consent if present
    try:
        page.click('[id*="onetrust-accept"], [aria-label*="Accept all"]', timeout=4_000)
        time.sleep(1)
    except Exception:
        pass

    listings = page.evaluate(f"""
    () => {{
        const cards = Array.from(document.querySelectorAll('[data-testid="property-card"]'));
        const results = [];
        for (const card of cards) {{
            const a = card.querySelector('a[data-testid="title-link"], a[href*="/hotel/"]');
            if (!a) continue;
            const href = a.href.split('?')[0];
            const m = href.match(/\\/hotel\\/[a-z]{{2}}\\/([^/?]+)/);
            if (!m) continue;
            const slug = m[1];
            const title = card.querySelector('[data-testid="title"]')?.textContent?.trim() || '';
            const price = card.querySelector('[data-testid="price-and-discounted-price"]')?.textContent?.trim()
                       || card.querySelector('.bui-price-display__value')?.textContent?.trim() || '';
            const rating = card.querySelector('[data-testid="review-score"]')
                               ?.textContent?.trim()?.match(/[\\d.]+/)?.[0] || '';
            results.push({{ id: slug, url: href, title, price, rating, source_platform: 'BOOKING' }});
            if (results.length >= {top_n}) break;
        }}
        return results;
    }}
    """)

    print(f"[search:booking] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Step 1c: Scrape VRBO search page
# ---------------------------------------------------------------------------

def scrape_search_vrbo(page, search_url: str, top_n: int) -> list[dict]:
    print(f"\n[search:vrbo] Navigating to {search_url}")
    page.goto(search_url, wait_until="networkidle", timeout=30_000)
    time.sleep(3)

    # Scroll to load lazy cards
    page.evaluate("""
    async () => {
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        for (let i = 0; i < 5; i++) { window.scrollBy(0, 800); await sleep(600); }
    }
    """)

    listings = page.evaluate(f"""
    () => {{
        const cards = Array.from(document.querySelectorAll(
            '[data-stid="property-listing"], [itemprop="itemListElement"], [class*="PropertyCard"]'
        ));
        const results = [];
        for (const card of cards) {{
            const a = card.querySelector('a[href*="/vacation-rentals/"], a[href*="/homeaway/"]');
            if (!a) continue;
            const href = a.href.split('?')[0];
            const m = href.match(/\\/p(\\d+)/) || href.match(/\\/(\\d{{6,}})/);
            if (!m) continue;
            const id = m[1];
            const title = card.querySelector('[data-stid="content-hotel-title"], h3')?.textContent?.trim() || '';
            const price = card.querySelector('[data-stid="content-hotel-price"], [class*="price"]')
                               ?.textContent?.trim() || '';
            const rating = card.querySelector('[aria-label*="out of"]')
                               ?.textContent?.trim()?.match(/[\\d.]+/)?.[0] || '';
            results.push({{ id, url: href, title, price, rating, source_platform: 'VRBO' }});
            if (results.length >= {top_n}) break;
        }}
        return results;
    }}
    """)

    print(f"[search:vrbo] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Step 2: Extract photo URLs from a listing page
# ---------------------------------------------------------------------------

def extract_photo_urls(page, listing_url: str, listing_id: str) -> list[str]:
    print(f"\n[photos] Loading {listing_url}")
    page.goto(listing_url, wait_until="networkidle", timeout=30_000)
    time.sleep(2)

    # Click "Show all photos"
    try:
        page.click('button:has-text("Show all photos")', timeout=8_000)
        time.sleep(2)
    except PWTimeout:
        print("[photos] 'Show all photos' button not found — trying hero images only")

    # Scroll-to-load inside the photo tour dialog
    urls = page.evaluate(f"""
    async () => {{
        const LISTING_ID = '{listing_id}';
        const dialog = Array.from(document.querySelectorAll('[role="dialog"]'))
            .find(d => d.getAttribute('aria-label') === 'Photo tour');
        const root = dialog || document.body;

        // Find the deepest scrollable container
        let scroller = root;
        for (const el of root.querySelectorAll('*')) {{
            const cs = getComputedStyle(el);
            if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                && el.scrollHeight > el.clientHeight + 50
                && el.scrollHeight > scroller.scrollHeight) {{
                scroller = el;
            }}
        }}

        const sleep = ms => new Promise(r => setTimeout(r, ms));
        let prev = -1, stable = 0;
        for (let i = 0; i < 40; i++) {{
            scroller.scrollTop = scroller.scrollHeight;
            await sleep(500);
            if (scroller.scrollTop === prev) {{ if (++stable > 2) break; }} else {{ stable = 0; }}
            prev = scroller.scrollTop;
        }}

        const urls = Array.from(root.querySelectorAll('img'))
            .map(i => i.src)
            .filter(s => s && s.includes('Hosting-' + LISTING_ID))
            .map(u => u.split('?')[0]);
        return [...new Set(urls)];
    }}
    """)

    out_dir = TMP / listing_id
    out_dir.mkdir(parents=True, exist_ok=True)
    url_file = out_dir / "photo_urls.txt"
    url_file.write_text("\n".join(urls))
    print(f"[photos] {len(urls)} unique URLs → {url_file.relative_to(ROOT)}")
    return urls


# ---------------------------------------------------------------------------
# Step 3: Download photos via the existing tool
# ---------------------------------------------------------------------------

def download_photos(listing_id: str, urls: list[str], count: int) -> list[Path]:
    out_dir = TMP / listing_id
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for i, url in enumerate(urls[:count], 1):
        dest = out_dir / f"photo-{i}.jpg"
        if dest.exists():
            print(f"[download] {dest.name} already exists, skipping")
            downloaded.append(dest)
            continue
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "download_airbnb_image.py"),
             "--listing-id", listing_id, "--url", url],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            downloaded.append(dest)
        else:
            print(f"[download] ✗ photo-{i}: {result.stderr.strip()}", file=sys.stderr)
    return downloaded


# ---------------------------------------------------------------------------
# Step 4a: Yandex reverse image search
# ---------------------------------------------------------------------------

def yandex_search(page, photo_path: Path) -> list[dict]:
    print(f"[yandex] Uploading {photo_path.name}")
    page.goto("https://yandex.com/images/", wait_until="domcontentloaded", timeout=20_000)
    time.sleep(1)

    # Trigger the hidden file input
    with page.expect_file_chooser() as fc_info:
        page.evaluate("() => document.querySelector('input[type=\"file\"]').click()")
    fc_info.value.set_files(str(photo_path))
    time.sleep(3)

    # Wait for results page
    try:
        page.wait_for_url(re.compile(r"yandex\.com/images/search"), timeout=15_000)
    except PWTimeout:
        print("[yandex] Timed out waiting for results")
        return []

    time.sleep(2)
    hits = page.evaluate("""
    () => {
        const anchors = Array.from(document.querySelectorAll('a[href^="http"]'));
        const seen = new Set();
        return anchors
            .map(a => ({ href: a.getAttribute('href'), text: a.textContent.trim().slice(0, 120) }))
            .filter(a => !/yandex\\.|ya\\.ru|muscache\\.com|airbnb\\./i.test(a.href))
            .filter(a => {
                const h = a.href.split('?')[0];
                if (seen.has(h)) return false; seen.add(h); return true;
            })
            .map(a => ({ ...a, domain: new URL(a.href).hostname.replace('www.','') }));
    }
    """)
    print(f"[yandex] {len(hits)} outbound hits")
    return hits


# ---------------------------------------------------------------------------
# Step 4b: Google Lens reverse image search (captcha-prone)
# ---------------------------------------------------------------------------

def lens_search(page, photo_path: Path) -> list[dict]:
    print(f"[lens] Uploading {photo_path.name}")
    page.goto("https://lens.google.com/", wait_until="domcontentloaded", timeout=20_000)
    time.sleep(2)

    try:
        with page.expect_file_chooser(timeout=8_000) as fc_info:
            page.evaluate("""
            () => {
                const inp = document.querySelector('input[name="encoded_image"], input[type="file"]');
                if (inp) inp.click();
            }
            """)
        fc_info.value.set_files(str(photo_path))
    except PWTimeout:
        print("[lens] Could not trigger file chooser — skipping Lens")
        return []

    time.sleep(4)

    # Check for captcha
    if "sorry/index" in page.url or "captcha" in page.url.lower():
        print("[lens] ⚠ CAPTCHA detected. Solve it in the browser window, then press Enter here.")
        input("  → Press Enter once the captcha is solved...")
        time.sleep(3)

    hits = page.evaluate("""
    () => {
        const anchors = Array.from(document.querySelectorAll('a[href^="http"]'));
        const seen = new Set();
        return anchors
            .map(a => ({ href: a.href, text: (a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 140) }))
            .filter(r => !/google\\.|gstatic|googleusercontent|googleadservices/i.test(r.href))
            .filter(r => !/(^|\\.)airbnb\\./i.test(r.href))
            .filter(r => { if (seen.has(r.href)) return false; seen.add(r.href); return true; })
            .map(r => ({ ...r, domain: new URL(r.href).hostname.replace('www.','') }));
    }
    """)
    print(f"[lens] {len(hits)} hits")
    return hits


# ---------------------------------------------------------------------------
# Step 5: Classify hits and extract operator contact
# ---------------------------------------------------------------------------

BOOKING_PLATFORMS = re.compile(
    r"booking\.com|agoda\.com|vrbo\.com|expedia\.|hotels\.com|tripadvisor\.|homeaway\.",
    re.IGNORECASE,
)


def classify_hits(yandex_hits: list[dict], lens_hits: list[dict]) -> dict:
    all_hits = yandex_hits + lens_hits
    booking_hits = [h for h in all_hits if BOOKING_PLATFORMS.search(h["href"])]
    stock_photo_hits = [
        h for h in all_hits
        if re.search(r"archdaily|archivibe|houzz|pinterest|dezeen|contemporist", h["href"], re.I)
    ]

    if booking_hits:
        verdict = "MANAGED_OR_CROSS_LISTED"
    elif stock_photo_hits:
        verdict = "SUSPICIOUS"
    elif all_hits:
        verdict = "HIT_NON_BOOKING"
    else:
        verdict = "CLEAN"

    return {
        "verdict": verdict,
        "booking_hits": booking_hits,
        "stock_hits": stock_photo_hits,
        "all_hits": all_hits,
    }


def fetch_operator_contact(ctx, hit_url: str) -> dict:
    result = {
        "managed_yn": "UNKNOWN",
        "operator": "",
        "operator_website": "",
        "operator_phone": "",
        "operator_email": "",
        "direct_booking_url": "",
        "cheapest_cross_platform_price_eur": "",
        "cross_platform_source": urlparse(hit_url).netloc.replace("www.", ""),
    }

    page = new_page(ctx)
    try:
        print(f"[contact] Loading {hit_url}")
        page.goto(hit_url, wait_until="networkidle", timeout=30_000)
        # Give JS-rendered content extra time to settle
        time.sleep(3)
        text = page.content()
    except Exception as e:
        print(f"[contact] fetch failed: {e}")
        page.close()
        return result
    finally:
        page.close()

    # Phone: look for Spanish/international phone patterns
    phones = re.findall(r"(?:\+34|0034)?[\s\-]?[6-9]\d{8}|\+\d{1,3}[\s\-]?\d{6,}", text)
    if phones:
        result["operator_phone"] = phones[0].strip()

    # Email
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    non_generic = [e for e in emails if not re.search(r"noreply|example|test", e, re.I)]
    if non_generic:
        result["operator_email"] = non_generic[0]

    # Price: rough EUR extraction from rendered page
    prices = re.findall(r"€\s*(\d+(?:[.,]\d+)?)", text)
    if prices:
        try:
            result["cheapest_cross_platform_price_eur"] = str(int(float(prices[0].replace(",", "."))))
        except ValueError:
            pass

    # Managed brand signals — search the full rendered text, not just raw HTML tags
    page_text = re.sub(r"<[^>]+>", " ", text)  # strip tags for clean text search
    title_match = re.search(r"<title[^>]*>([^<]{5,120})</title>", text, re.I)
    page_title = title_match.group(1) if title_match else ""

    brand_pattern = re.compile(
        r"Travel Habitat|Habitat Apartments|HomeKeys|Spain.Holiday|TH Bioparc|TH Valencia",
        re.I,
    )
    if brand_pattern.search(page_title + page_text[:5000]):
        result["managed_yn"] = "MANAGED"
        m = brand_pattern.search(page_title + page_text[:500])
        if m:
            result["operator"] = m.group(0)

    return result


# ---------------------------------------------------------------------------
# Step 6: Write result row to CSV
# ---------------------------------------------------------------------------

def write_result(row: dict) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "append_to_sheet.py")] +
        [arg for k, v in row.items() for arg in (f"--{k.replace('_','-')}", str(v)) if v],
        check=False
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def process_listing(ctx, listing: dict, photos: int, skip_download: bool,
                    yandex_only: bool, headless: bool) -> None:
    lid = listing["id"]
    lurl = listing["url"]
    out_dir = TMP / lid
    result_file = out_dir / "result.json"

    if result_file.exists():
        print(f"\n[{lid}] result.json already exists — skipping (delete it to re-run)")
        return

    page = new_page(ctx)

    # 2. Extract + download photos
    if skip_download and (out_dir / "photo-1.jpg").exists():
        photo_paths = sorted(out_dir.glob("photo-*.jpg"))[:photos]
        print(f"[{lid}] Using {len(photo_paths)} cached photos")
    else:
        try:
            urls = extract_photo_urls(page, lurl, lid)
        except Exception as e:
            print(f"[{lid}] Photo extraction failed: {e}", file=sys.stderr)
            page.close()
            return
        photo_paths = download_photos(lid, urls, photos)

    if not photo_paths:
        print(f"[{lid}] No photos downloaded — skipping", file=sys.stderr)
        page.close()
        return

    # 3. Reverse search each photo, tracking per-photo domains for stock detection
    all_yandex, all_lens = [], []
    photo_domain_lists: list[list[str]] = []
    for photo_path in photo_paths:
        photo_yandex, photo_lens = [], []
        try:
            photo_yandex = yandex_search(page, photo_path)
            all_yandex.extend(photo_yandex)
        except Exception as e:
            print(f"[{lid}] Yandex error on {photo_path.name}: {e}", file=sys.stderr)

        if not yandex_only:
            try:
                photo_lens = lens_search(page, photo_path)
                all_lens.extend(photo_lens)
            except Exception as e:
                print(f"[{lid}] Lens error on {photo_path.name}: {e}", file=sys.stderr)

        photo_domain_lists.append([h["domain"] for h in photo_yandex + photo_lens])

    # 3b. Stock photo detection
    stock_result = classify_photos(photo_domain_lists)
    print(f"[{lid}] Photo authenticity: {stock_result['listing']} ({stock_result['stock_count']}/{stock_result['total']} stock)")

    # 4. Classify
    classification = classify_hits(all_yandex, all_lens)
    print(f"[{lid}] Verdict: {classification['verdict']}")

    # 5. Find operator contact if booking hit found
    contact = {}
    if classification["booking_hits"]:
        hit = classification["booking_hits"][0]
        print(f"[{lid}] Fetching contact from: {hit['href']}")
        contact = fetch_operator_contact(ctx, hit["href"])

    # Estimate direct price
    airbnb_price = listing.get("price", "")
    eur_m = re.search(r"€\s*(\d+)", airbnb_price)
    airbnb_eur = int(eur_m.group(1)) if eur_m else 0
    cross_price = contact.get("cheapest_cross_platform_price_eur", "")
    if cross_price:
        est_direct = round(int(cross_price) * 0.92)
    elif airbnb_eur:
        est_direct = round(airbnb_eur * 0.82)
    else:
        est_direct = ""

    hit_urls = " | ".join(h["href"] for h in classification["booking_hits"][:3])
    notes = f"verdict={classification['verdict']}; hits: {hit_urls or 'none'}"
    if classification["stock_hits"]:
        notes += f"; stock-photo hits: {classification['stock_hits'][0]['domain']}"

    negotiation_notes = ""
    if contact.get("operator_phone") and contact.get("operator"):
        negotiation_notes = (
            f"Call {contact['operator_phone']}, ask for direct rate "
            f"({contact['operator']}). Est. direct €{est_direct} vs Airbnb ~€{airbnb_eur or '?'}."
        )

    row = {
        "listing_id": lid,
        "source_platform": listing.get("source_platform", "AIRBNB"),
        "airbnb_url": lurl,
        "airbnb_price_eur": str(airbnb_eur) if airbnb_eur else airbnb_price,
        "cheapest_cross_platform_price_eur": cross_price,
        "cross_platform_source": contact.get("cross_platform_source", ""),
        "estimated_direct_price_eur": str(est_direct) if est_direct else "",
        "managed_yn": contact.get("managed_yn", "UNKNOWN" if classification["booking_hits"] else "OWNER"),
        "operator": contact.get("operator", ""),
        "operator_website": contact.get("operator_website", ""),
        "operator_phone": contact.get("operator_phone", ""),
        "operator_email": contact.get("operator_email", ""),
        "direct_booking_url": contact.get("direct_booking_url", ""),
        "photo_authenticity": stock_result["listing"],
        "stock_photo_count": str(stock_result["stock_count"]),
        "negotiation_notes": negotiation_notes,
        "evidence_urls": hit_urls,
        "notes": notes,
        "confidence": "medium" if classification["booking_hits"] else "low",
    }

    write_result(row)

    # Persist for resumability
    result_file.write_text(json.dumps({**row, "all_hits": classification["all_hits"]}, indent=2))
    print(f"[{lid}] Done → {result_file.relative_to(ROOT)}")
    page.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing-id", help="Run on a single listing ID (Airbnb only)")
    group.add_argument("--search-url", help="Search URL to scrape for listings")
    ap.add_argument("--platform", default="airbnb",
                    choices=["airbnb", "booking", "vrbo", "idealista", "google_maps"],
                    help="Source platform (default: airbnb)")
    ap.add_argument("--top-n", type=int, default=5, help="Max listings from search URL (default 5)")
    ap.add_argument("--photos", type=int, default=2, help="Photos to reverse-search per listing (default 2)")
    ap.add_argument("--skip-download", action="store_true", help="Skip photo download if files exist")
    ap.add_argument("--yandex-only", action="store_true", help="Skip Google Lens to avoid captchas")
    ap.add_argument("--headless", action="store_true", help="Run Firefox headless (no window)")
    args = ap.parse_args()

    _scrape_fn = {
        "airbnb": scrape_search,
        "booking": scrape_search_booking,
        "vrbo": scrape_search_vrbo,
    }
    if args.platform in ("idealista", "google_maps") and args.search_url:
        print(f"[{args.platform}] Automated Python scraping not yet implemented for this platform.")
        print(f"  Use the agent workflow at: platforms/{args.platform}/scrape_search.md")
        return 1

    with sync_playwright() as pw:
        ctx = launch_browser(pw, args.headless)
        try:
            if args.listing_id:
                listings = [{"id": args.listing_id, "url": f"https://www.airbnb.com/rooms/{args.listing_id}",
                             "title": "", "price": "", "source_platform": "AIRBNB"}]
            else:
                page = new_page(ctx)
                listings = _scrape_fn[args.platform](page, args.search_url, args.top_n)
                page.close()

            for listing in listings:
                process_listing(
                    ctx, listing,
                    photos=args.photos,
                    skip_download=args.skip_download,
                    yandex_only=args.yandex_only,
                    headless=args.headless,
                )

        finally:
            ctx.close()

    print(f"\nAll done. Results in {RESULTS_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
