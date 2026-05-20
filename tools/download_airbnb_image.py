#!/usr/bin/env python3
"""Download Airbnb listing photos from the public muscache CDN.

Two modes:
  Single URL:
    python tools/download_airbnb_image.py --listing-id 12345 --url <muscache-url>
  Batch from a file (one URL per line, blanks/`#` comments ignored):
    python tools/download_airbnb_image.py --listing-id 12345 --urls-file .tmp/12345/photo_urls.txt

Output:
  Writes to .tmp/<listing-id>/photo-<n>.jpg with sequential numbering. In
  single-URL mode `n` is the lowest unused integer for that directory. In
  batch mode `n` restarts at 1 and the dir is created fresh.

Notes:
  - The CDN is public; no cookies / auth needed.
  - Strips `?im_w=...` to request the original-resolution image.
  - Skips a URL with a clear warning if the HTTP response is not 200 or not an
    image/* content-type, but does not abort the rest of the batch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
TIMEOUT = 20
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


def strip_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def next_index(out_dir: Path) -> int:
    existing = sorted(out_dir.glob("photo-*.jpg"))
    if not existing:
        return 1
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.split("-", 1)[1]))
        except (IndexError, ValueError):
            pass
    return (max(nums) + 1) if nums else 1


def download_one(url: str, dest: Path) -> bool:
    target = strip_query(url)
    try:
        r = requests.get(target, headers={"User-Agent": UA}, timeout=TIMEOUT, stream=True)
    except requests.RequestException as e:
        print(f"  ✗ request failed: {e}", file=sys.stderr)
        return False
    if r.status_code != 200:
        print(f"  ✗ HTTP {r.status_code} for {target}", file=sys.stderr)
        return False
    ct = r.headers.get("Content-Type", "")
    if not ct.startswith("image/"):
        print(f"  ✗ unexpected Content-Type {ct!r} for {target}", file=sys.stderr)
        return False
    with dest.open("wb") as f:
        for chunk in r.iter_content(64 * 1024):
            if chunk:
                f.write(chunk)
    print(f"  ✓ {dest.relative_to(ROOT)} ({dest.stat().st_size} bytes)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listing-id", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Single muscache image URL")
    src.add_argument("--urls-file", help="File with one URL per line")
    args = ap.parse_args()

    out_dir = TMP / args.listing_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.url:
        idx = next_index(out_dir)
        dest = out_dir / f"photo-{idx}.jpg"
        return 0 if download_one(args.url, dest) else 1

    urls = [
        ln.strip()
        for ln in Path(args.urls_file).read_text().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    print(f"Downloading {len(urls)} photos to {out_dir.relative_to(ROOT)}/")
    ok = 0
    for i, url in enumerate(urls, 1):
        dest = out_dir / f"photo-{i}.jpg"
        if download_one(url, dest):
            ok += 1
    print(f"Done: {ok}/{len(urls)} succeeded.")
    return 0 if ok == len(urls) else 1


if __name__ == "__main__":
    sys.exit(main())
