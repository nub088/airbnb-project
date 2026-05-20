# Platform Adapter: Idealista / Fotocasa Search

## Objective
Navigate an Idealista (or Fotocasa) search page for tourist apartments / short-term rentals and extract listing cards in the normalized schema `{listing_id, url, title, price, rating, source_platform}`.

## Why Idealista / Fotocasa
- Spanish property portals — strongest overlap with Valencia short-term rental inventory
- Tourist licence numbers (`VT-` prefix) are **frequently listed inline** on the search card and/or listing page — this is the single highest-value data point for finding the real owner via the Registro de Turismo de la Comunitat Valenciana
- Owner names and direct contact numbers appear more openly than on Airbnb (Idealista has a "contact owner" flow without masking the phone)
- Fotocasa also lists tourist apartments; same extraction approach applies

## Inputs
- `search_url` — Idealista URL for tourist apartments in Valencia, e.g.:
  `https://www.idealista.com/alquiler-viviendas/valencia-provincia/con-alquiler-turistico/`
  Or Fotocasa: `https://www.fotocasa.es/es/alquiler/viviendas/valencia-capital/todas-las-zonas/l`
- `top_n` — max listings (default 5)

## Tools Used
- Playwright MCP (`browser_navigate`, `browser_evaluate`, `browser_snapshot`, `browser_scroll`)

## Procedure

### 1. Navigate
```
browser_navigate("<search_url>")
```
Idealista shows a cookie consent modal on first visit — accept it:
```js
document.querySelector('#didomi-notice-agree-button, [aria-label*="Accept all"]')?.click()
```

### 2. Extract Listing Cards (Idealista)
```js
() => {
  const articles = Array.from(document.querySelectorAll('article.item, [class*="item-info-container"]'));
  return articles.slice(0, TOP_N).map(a => {
    const link = a.querySelector('a.item-link, a[href*="/inmueble/"]');
    const href = link?.href || '';
    const id = href.match(/\/inmueble\/(\d+)/)?.[1] || '';
    const title = a.querySelector('.item-title, h3.item-title')?.textContent?.trim() || '';
    const price = a.querySelector('.item-price, .price-row')?.textContent?.trim() || '';
    // Tourist licence sometimes in the detail text
    const detail = a.querySelector('.item-detail-char, .item-description')?.textContent || '';
    const licence = detail.match(/VT[-\s]?\d+/i)?.[0] || '';
    return {
      listing_id: id,
      url: href,
      title: title + (licence ? ` [${licence}]` : ''),
      price,
      rating: '',
      source_platform: 'IDEALISTA',
      tourist_licence: licence,
    };
  }).filter(c => c.listing_id);
}
```

### 3. Extract Listing Cards (Fotocasa)
```js
() => {
  const cards = Array.from(document.querySelectorAll('[class*="re-CardPackMinimal"], article[class*="re-Card"]'));
  return cards.slice(0, TOP_N).map(card => {
    const a = card.querySelector('a[href*="/anuncio/"]');
    const href = a?.href || '';
    const id = href.match(/\/(\d+)\.htm/)?.[1] || '';
    const title = card.querySelector('span[class*="title"], h3')?.textContent?.trim() || '';
    const price = card.querySelector('span[class*="price"]')?.textContent?.trim() || '';
    return {
      listing_id: id,
      url: href,
      title,
      price,
      rating: '',
      source_platform: 'IDEALISTA',  // treat both as IDEALISTA in CSV
    };
  }).filter(c => c.listing_id);
}
```

### 4. Normalize Output
```json
{
  "listing_id": "98765432",
  "url": "https://www.idealista.com/inmueble/98765432/",
  "title": "Piso en Ruzafa, Valencia [VT-12345-A-2019-0001]",
  "price": "€900/mes",
  "rating": "",
  "source_platform": "IDEALISTA",
  "tourist_licence": "VT-12345-A-2019-0001"
}
```

## Photo Extraction (downstream step)
Idealista listing pages show a main photo carousel. All photos load via:
`img[src*="images.idealista.com"]` or `[class*="main-image"] img`

The CDN `images.idealista.com` is public — no auth required. Strip `?` query params for original resolution.

## Tourist Licence Cross-Reference
A tourist licence number (e.g., `VT-46250-A-2019-0001`) encodes:
- `46250` — municipal code (Valencia city = 46250)
- `A` or `V` — apartment or villa
- `2019` — registration year
- `0001` — sequential number

To look up the owner: search the **Registro de Turismo de la Comunitat Valenciana** at `https://turisme.gva.es` or call the tourist office. The licence number is the single most reliable path to the real property owner's name and contact.

## Owner Contact Signals
- Idealista: "Contactar con el propietario" button — may show masked phone, but `browser_evaluate` on the listing page can sometimes extract the full number from page source
- Fotocasa: "Ver teléfono" button — clicking it reveals the number; use `browser_click` to trigger, then extract via `browser_evaluate` on the revealed element
- Both portals: look for agency name in the listing (if it's a managed listing, the agency name will appear at the top of the contact card)

## Gotchas
- Idealista blocks scraping aggressively with Cloudflare — the persistent Firefox profile with prior Idealista visits is critical; a fresh browser session will likely be blocked
- Idealista search results for "alquiler turístico" may include both long-term and short-term rentals mixed together — filter by the presence of `VT-` licence in the description to identify tourist apartments
- Fotocasa uses Next.js; some content is server-rendered but prices can be deferred — wait 2s after page load before evaluating
- Idealista photo selectors vary between listing types; if the main carousel selector misses, try `[id*="photoSlider"] img` as a fallback
- Tourist licence visibility is inconsistent: some owners list it voluntarily, others don't. Absence of a licence on Idealista doesn't mean the listing lacks one — check the Airbnb listing for the same property too.

## Reference Test
Search: `https://www.idealista.com/alquiler-viviendas/valencia/con-alquiler-turistico/`
Expected: 15–30 listings, several with VT codes visible in the card text or title
