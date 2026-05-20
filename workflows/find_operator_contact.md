# Workflow: Find Operator Contact

## Objective
Given a cross-platform hit URL (Booking, Agoda, VRBO, etc.) identified during reverse-image search, determine whether the listing is **managed** (a property management company) or **owner-operated**, then surface the best direct contact channel for negotiating outside Airbnb.

## Inputs
- `hit_url` — URL of the cross-platform hit (e.g. Booking.com listing, Agoda page, VRBO listing)
- `hit_platform` — e.g. `booking`, `agoda`, `vrbo`, `direct`
- `listing_id` — Airbnb listing ID (for output tagging)
- `airbnb_price_eur` — nightly price in EUR scraped from the Airbnb search card

## Classification Rule

A listing is **managed** if any of the following are true:
- The property/apartment name on the hit platform contains a brand (e.g. "Travel Habitat", "Spain-Holiday", "HomeKeys", "Habitat Apartments")
- The cross-platform listing shows the same property under multiple branded names
- There is a "Managed by" or "Offered by" field naming a company (not a person's first name)
- Multiple apartments at the same address appear under the same brand on multiple platforms

A listing is **owner-operated** if:
- The host name on Airbnb is a first name (e.g. "María") with no company affiliation
- No cross-platform brand name is found
- The property appears only on Airbnb

If unclear, mark `managed_yn = UNKNOWN`.

## Procedure

### 1. Scrape the hit page
Use `WebFetch` (or `browser_navigate` + `browser_snapshot` for JS-heavy pages) on `hit_url`.

Extract:
- Property/hotel name on the hit platform
- "Managed by" / "Offered by" / "Host" field
- Address shown (for Catastro cross-reference later if needed)
- Any link to an operator/owner website (often in the property description or "About the host" section)
- Direct booking URL if present ("Book on [brand]", "Visit website")

### 2. Identify the operator brand

If the hit page names a management company:
a. Search for their direct website: `<brand name> Valencia apartments official site`
b. Fetch their homepage and contact page (`/contact`, `/contacto`, `/en/contact/`)

Extract from the operator site:
- **Phone** (priority #1 — most useful for negotiation)
- **Email** (if available — rare for Spanish firms due to GDPR norms; a contact form URL is fine)
- **Direct booking URL** — look for "Book direct", "Reserve now", "Reservar", or a `/rentals/` or `/apartments/` section that lists the specific unit
- **WhatsApp** — increasingly common for Spanish property managers; look for `wa.me/` links or a WhatsApp widget

### 3. Find the specific unit on the operator site (optional but high-value)
If the operator has a property search on their site, try to locate the exact apartment by:
- Address match (Carrer d'Archena 14 → search the operator's listings by that street)
- Internal code if visible (e.g. VA077-2)
- Cross-referencing photo thumbnails

This gives a direct URL to the unit on the operator's own site — the cleanest negotiation entry point.

### 4. Price estimate

Extract the nightly price shown on `hit_url` (the cross-platform listing page) — this is `cheapest_cross_platform_price_eur`. If multiple cross-platform hits exist, use the lowest.

Calculate `estimated_direct_price_eur` using this rule:

```
if cheapest_cross_platform_price_eur is available:
    estimated = round(cheapest_cross_platform_price_eur * 0.92)
    # Operator saves ~8% more by skipping Booking/Agoda commission on top of Airbnb savings
else:
    estimated = round(airbnb_price_eur * 0.82)
    # Estimate Airbnb total minus platform fees (~18%) if no cross-platform baseline
```

Round to the nearest whole euro. Record `cross_platform_source` as the domain (e.g. `booking.com`).

### 5. Emit result

| Field | Value |
|---|---|
| `airbnb_price_eur` | From input |
| `cheapest_cross_platform_price_eur` | Scraped from hit page |
| `cross_platform_source` | e.g. `booking.com` |
| `estimated_direct_price_eur` | Calculated (see step 4) |
| `managed_yn` | MANAGED / OWNER / UNKNOWN |
| `operator` | Company name (or host first name if owner) |
| `operator_website` | Direct site URL |
| `operator_phone` | E.164 format e.g. +34 960 660 456 |
| `operator_email` | Company email if publicly listed; blank if not found |
| `direct_booking_url` | Specific unit page on operator site (if found) |
| `negotiation_notes` | One-line: "Call +34 XXX, ask for unit VA077-2 direct rate. Est. direct €62 vs Airbnb €80." |

Write to `results.csv` via `tools/append_to_sheet.py` (all fields fit in existing columns; overflow into `notes`).

## Decision Tree After Classification

```
MANAGED → Operator site found?
    YES → Direct booking URL found?
        YES → Record URL. Contact to negotiate = operator phone/email. Done.
        NO  → Record operator contact only. Note "book direct link not found".
    NO  → Try Google: "<operator name> Valencia apartamentos contacto"
          → If still nothing, record operator name only.

OWNER → Mark direct_booking_available = NO.
        Negotiation path = Airbnb in-app message (length-of-stay / off-season pitch).
        No further steps needed.

UNKNOWN → Flag for manual review. Move to next listing.
```

## Gotchas

- Many Spanish property managers hide email behind contact forms (GDPR). A contact form URL is good enough — record it.
- Travel Habitat uses `travelhabitat.es` with a `/en/contact/` page and a `/rentals/` section searchable by address. Their contact page was fetchable via WebFetch (no JS wall).
- Agoda and Booking often show "Managed by [operator]" in the sidebar — this is the fastest classification signal.
- If the operator domain is JS-heavy (SPA), fall back to `browser_navigate` + `browser_snapshot` + `browser_evaluate` for contact extraction.

## Reference Run

Hit URL: `https://www.agoda.com/travel-habitat-bioparc-apartments/hotel/valencia-es.html`

- Brand name in title: "Travel Habitat Bioparc Apartments" → **MANAGED**
- Operator: Travel Habitat
- Site: `travelhabitat.es`
- Phone: +34 960 660 456
- Email: `atencionalcliente@travelhabitat.com`
- Contact page: `https://travelhabitat.es/en/contact/`
- Specific unit: `https://travelhabitat.es/rentals/apartment-valencia-a-va077-2-th-bioparc-con-terraza-apartment-2-491393.html`
- `direct_booking_available`: YES
- Negotiation note: "Call +34 960 660 456 or email atencionalcliente@travelhabitat.com, reference unit VA077-2. Ask for direct rate — saves TH the ~15% Airbnb commission."
