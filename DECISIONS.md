# Decisions

## SAP

I chose a CSV upload shaped like an SAP S/4HANA material/procurement export rather than live OData, BAPI, or IDoc integration. The assignment is about realistic ingestion judgment in four days, and a CSV export is a common handoff from enterprise SAP users to analyst teams.

The subset handled:

- material/procurement document rows
- plant codes
- document numbers and line items
- mixed English/German headers
- mixed date formats
- fuel/procurement categories
- inconsistent units
- failed rows for unsupported units, bad dates, non-positive quantities, and missing source keys

Ignored for this prototype:

- live SAP authentication
- IDoc segment parsing
- purchase order lifecycle state
- full material master synchronization

PM questions:

- Which SAP module/export is the client actually using?
- Are plant and material master lookup tables available?
- Should procurement categories be mapped by material group, GL account, or vendor?

## Utility Electricity

I chose Green Button Download My Data-style XML. It is a realistic utility data shape and is more defensible than inventing a generic CSV. It also lets the prototype show billing periods, meter IDs, tariffs, and kWh usage.

The subset handled:

- meter ID
- usage quantity and unit
- billing period start/end
- tariff/rate label
- service address
- failed rows for missing usage, invalid units, non-positive kWh, and bad billing dates

Ignored for this prototype:

- PDF bill OCR
- portal scraping
- interval-level time-of-use analytics
- utility OAuth or Green Button Connect My Data authorization

PM questions:

- Which utilities serve the client facilities?
- Are exports monthly billing summaries or interval reads?
- Do analysts need market-based and location-based Scope 2 treatment?

## Corporate Travel

I chose Concur-style itinerary JSON because travel platforms commonly expose trip segments rather than one clean emissions row. Flights, hotels, and ground transport need different normalization logic.

The subset handled:

- flight segments with airport codes
- hotel stays with city/country and nights
- ground transport with distance where available
- missing flight distance fallback through airport lookup
- failed rows for unsupported categories, missing hotel nights, and airport pairs that cannot produce distance

Ignored for this prototype:

- live Concur/Navan OAuth
- expense receipt attachments
- cabin-class-specific emissions calculations
- traveler HR hierarchy

PM questions:

- Is the source Concur, Navan, or another travel platform?
- Are distances supplied by the platform or must we compute them?
- Which travel categories should analysts manually review every time?
