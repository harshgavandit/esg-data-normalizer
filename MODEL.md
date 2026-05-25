# Data Model

The model separates source truth from analyst-approved ESG activity. That separation is the core design choice: source exports are messy and should be preserved exactly, while normalized rows are the reviewable interpretation.

## Tenant Boundary

`Organization` is the tenant boundary. Every import, raw record, activity record, lookup, approval, and audit event belongs to an organization. `Membership` connects a user to one organization with a simple role: admin, analyst, or auditor.

Every API query filters by the authenticated user's organization. This avoids the common prototype mistake where multi-tenancy exists in the schema but not in the access layer.

## Source Truth And Normalized Activity

`SourceSystem` describes the chosen ingestion mechanism for SAP, utility, and travel. `ImportBatch` tracks one upload attempt with row counts and status.

`RawRecord` stores each original source row or payload in JSON. This table answers: which source produced this row, when did it arrive, what did the system actually receive, and did parsing fail?

`ActivityRecord` stores the normalized ESG interpretation: activity type, Scope 1/2/3 category, original quantity/unit, normalized quantity/unit, period, location, confidence, status, and lock timestamp. It references exactly one raw record, so analysts can defend the normalized value against the source input.

## Normalization

Unit normalization is intentionally explicit. `UnitConversion` contains conversions such as gallons to liters, MWh to kWh, and miles to kilometers. The normalized row keeps both original and normalized values because auditors often need to see the path from source to standard unit.

Scope categorization is stored on `ActivityRecord`:

- SAP fuel rows map mainly to Scope 1.
- SAP procurement rows map to Scope 3.
- Utility electricity maps to Scope 2.
- Business travel maps to Scope 3.

Emission factors exist as reference data, but this prototype does not try to become a full carbon accounting engine.

## Review, Approval, And Audit

`ReviewFinding` stores row-level issues such as unknown units, unknown plants, odd billing periods, missing airport distance, or duplicate source keys. Findings are visible to the analyst rather than hidden in logs. Error-level findings make a row `failed`; warning-only findings make it `suspicious`; clean rows remain `pending_review`.

`Approval` records analyst decisions. `AuditEvent` is an immutable timeline for import, edit, approve, reject, and lock actions. Edits store before/after JSON so the review process is defensible.

Rows with error-level findings cannot be approved until corrected or rejected. Locked activity records are read-only. A locked row represents the version that would be shared with auditors.
