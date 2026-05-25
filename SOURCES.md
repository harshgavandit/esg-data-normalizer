# Sources

## SAP Fuel And Procurement

Researched format: SAP S/4HANA material/procurement style exports and OData/API concepts.

Useful references:

- SAP S/4HANA Cloud APIs and integration documentation: https://help.sap.com/docs/SAP_S4HANA_CLOUD
- SAP Business Accelerator Hub API catalog: https://api.sap.com/

What I learned:

- SAP data is rarely analyst-friendly.
- Document numbers, line items, posting dates, plant codes, material numbers, and units are common pieces of movement/procurement data.
- Plant codes and material categories require lookup tables to become meaningful ESG activity.
- Header names may vary by configuration and language.

Sample data rationale:

`samples/sap_fuel_procurement.csv` includes German headers, mixed date formats, liters/gallons/kWh/kg, unknown plant code, missing material description, and a negative adjustment row.

What would break in production:

- Client-specific SAP custom fields.
- IDoc or OData payloads instead of CSV.
- Material groups requiring a real master-data mapping process.

## Utility Electricity

Researched format: Green Button energy usage data.

Useful references:

- Green Button Alliance: https://www.greenbuttonalliance.org/green-button
- Green Button Connect My Data: https://www.greenbuttonalliance.org/green-button-connect-my-data-cmd

What I learned:

- Utility data is centered on meters, usage values, units, tariffs, and billing/interval periods.
- Billing periods often do not align cleanly with calendar months.
- Structured exports are a better prototype target than PDF bills because they expose the data model clearly.

Sample data rationale:

`samples/utility_green_button.xml` includes meter IDs, kWh and MWh units, tariff labels, billing periods, an unknown meter, and an unusually short period.

What would break in production:

- Utility-specific XML variants.
- Interval data at high volume.
- Missing or inconsistent meter-to-facility mapping.

## Corporate Travel

Researched format: SAP Concur travel/itinerary-style APIs.

Useful references:

- SAP Concur Developer Center: https://preview.developer.concur.com/
- SAP Concur API reference: https://preview.developer.concur.com/api-reference/

What I learned:

- Travel data appears as segments and expenses, not as one carbon-ready row.
- Flights may provide airport codes but not distance.
- Hotels and ground transport require category-specific normalization.

Sample data rationale:

`samples/travel_concur_itinerary.json` includes flights, hotel nights, ground transport, missing computed flight distance, and an unknown airport code.

What would break in production:

- Platform-specific schema differences.
- Code-share flights and multi-leg trips.
- Missing traveler or department hierarchy.
- Expense items that do not map cleanly to travel categories.

