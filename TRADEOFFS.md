# Tradeoffs

## 1. No Live SAP Or Concur OAuth

I implemented realistic file uploads instead of live enterprise integrations. Live SAP and Concur connections would require credentials, tenant-specific configuration, and production security decisions that are outside a four-day prototype.

The prototype still models source provenance, row keys, parser errors, and normalization logic, which are the important evaluation points.

## 2. No Utility PDF OCR Or Portal Scraping

I chose Green Button XML instead of PDF bill extraction. PDF OCR can easily become a brittle document-processing project and distract from the core ingestion/review/audit workflow.

In production, PDF bills may still be needed for utilities that do not support structured exports.

## 3. No Full Emissions Calculation Engine

The app stores emission factor references but does not build a full calculation engine. The assignment says the hard part is not carbon math; it is messy source data, normalization, analyst review, and audit sign-off.

This keeps the implementation focused on the data model and review workflow.

