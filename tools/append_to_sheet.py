#!/usr/bin/env python3
"""Append a row of identification findings to results.csv.

Usage:
    python tools/append_to_sheet.py \
        --listing-id 1353198002579642941 \
        --airbnb-url "https://www.airbnb.com/rooms/1353198002579642941" \
        --operator "Travel Habitat" \
        --address "Carrer d'Archena 14, 46018 Valencia, ES" \
        --internal-code VA077-2 \
        --owner-contact "atencionalcliente@travelhabitat.com" \
        --confidence medium \
        --notes "Operator confirmed via Booking+Agoda cross-listing; real owner via Registro pending"

Any flag can be omitted; the column is left blank.

Designed as a drop-in replacement for the originally planned Google Sheets
writer: no auth, no network, just an append-only CSV that any spreadsheet
tool can open.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

COLUMNS = [
    "timestamp_utc",
    "listing_id",
    "source_platform",
    "airbnb_url",
    "airbnb_price_eur",
    "cheapest_cross_platform_price_eur",
    "cross_platform_source",
    "estimated_direct_price_eur",
    "managed_yn",
    "operator",
    "operator_website",
    "operator_phone",
    "operator_email",
    "direct_booking_url",
    "photo_authenticity",
    "stock_photo_count",
    "negotiation_notes",
    "address",
    "internal_code",
    "tourist_licence",
    "owner_name",
    "evidence_urls",
    "confidence",
    "notes",
]

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "results.csv"


def append_row(csv_path: Path, row: dict) -> None:
    new_file = not csv_path.exists()
    row["timestamp_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in COLUMNS})


def main() -> None:
    p = argparse.ArgumentParser(description="Append a finding row to results.csv")
    p.add_argument("--csv", default=str(DEFAULT_CSV), help="Output CSV path")
    for col in COLUMNS:
        if col == "timestamp_utc":
            continue
        p.add_argument(f"--{col.replace('_', '-')}", default="", help=f"Value for {col}")
    args = p.parse_args()

    row = {col: getattr(args, col) for col in COLUMNS if col != "timestamp_utc"}
    append_row(Path(args.csv), row)
    print(f"Appended row to {args.csv}")


if __name__ == "__main__":
    main()
