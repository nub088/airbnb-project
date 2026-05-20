#!/usr/bin/env python3
"""Classify reverse-image-search hit domains to detect stock/fake listing photos.

Usage:
  Single photo (comma-separated domains):
    python tools/classify_photo_hits.py --domains "shutterstock.com,booking.com,archdaily.com"

  Multiple photos (JSON array of domain lists):
    python tools/classify_photo_hits.py --domains-json '[["shutterstock.com"], ["booking.com"]]'

Output (JSON to stdout):
  {
    "per_photo": ["STOCK", "GENUINE"],
    "listing": "SOME_STOCK",
    "stock_count": 1,
    "total": 2
  }

Per-photo values: STOCK | GENUINE | MIXED
  STOCK   — hit on a known stock-photo site (no booking platform hit)
  MIXED   — hit on both a stock site AND a booking platform (unusual, flag it)
  GENUINE — no stock-photo site hits

Listing aggregate: GENUINE | SOME_STOCK | MOSTLY_STOCK | ALL_STOCK
"""
from __future__ import annotations

import argparse
import json
import re
import sys

STOCK_DOMAINS: frozenset[str] = frozenset({
    "shutterstock.com",
    "gettyimages.com",
    "istockphoto.com",
    "unsplash.com",
    "pexels.com",
    "alamy.com",
    "dreamstime.com",
    "depositphotos.com",
    "123rf.com",
    "stock.adobe.com",
})

_BOOKING_RE = re.compile(
    r"booking\.com|agoda\.com|vrbo\.com|expedia\.|hotels\.com|tripadvisor\.|homeaway\.",
    re.IGNORECASE,
)


def _is_stock(domain: str) -> bool:
    return any(sd in domain for sd in STOCK_DOMAINS)


def _is_booking(domain: str) -> bool:
    return bool(_BOOKING_RE.search(domain))


def classify_photo(domains: list[str]) -> str:
    """Return STOCK / GENUINE / MIXED for one photo's hit domain list."""
    has_stock = any(_is_stock(d) for d in domains)
    has_booking = any(_is_booking(d) for d in domains)
    if has_stock and has_booking:
        return "MIXED"
    if has_stock:
        return "STOCK"
    return "GENUINE"


def classify_listing(per_photo: list[str]) -> str:
    """Return GENUINE / SOME_STOCK / MOSTLY_STOCK / ALL_STOCK for a listing."""
    if not per_photo:
        return "GENUINE"
    stock_count = sum(1 for p in per_photo if p in ("STOCK", "MIXED"))
    ratio = stock_count / len(per_photo)
    if ratio == 1.0:
        return "ALL_STOCK"
    if ratio > 0.5:
        return "MOSTLY_STOCK"
    if ratio > 0:
        return "SOME_STOCK"
    return "GENUINE"


def run(photo_domain_lists: list[list[str]]) -> dict:
    """Classify a listing given per-photo domain lists. Returns a result dict."""
    per_photo = [classify_photo(domains) for domains in photo_domain_lists]
    stock_count = sum(1 for p in per_photo if p in ("STOCK", "MIXED"))
    return {
        "per_photo": per_photo,
        "listing": classify_listing(per_photo),
        "stock_count": stock_count,
        "total": len(per_photo),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--domains", help="Comma-separated domain list for a single photo")
    src.add_argument("--domains-json", help="JSON array of domain lists, one list per photo")
    args = ap.parse_args()

    if args.domains:
        domain_lists = [[d.strip() for d in args.domains.split(",") if d.strip()]]
    else:
        domain_lists = json.loads(args.domains_json)

    result = run(domain_lists)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
