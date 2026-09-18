# Dataset provenance

## Official source

Hutchinson, Matthew; Walker, Hallie; Abraham, Joel et al. (2026).
*Ecology of community reassembly: Movements and diets of megafauna during a
decade of restoration in Mozambique* [Dataset]. Dryad.
https://doi.org/10.5061/dryad.m905qfv85

Original GPS table: `GPS-COLLAR-LOCATION-RECORDS_ELEPHANT.csv` in `DataS1.zip`.

The official Dryad record reports 839,947 elephant GPS fixes from 18 individuals.
The reduced workbook README reports 839,746 source rows. This 201-row provenance
difference must be recorded rather than silently hidden; it does not alter the
audited 60,000-row reduced workbook.

The official source documents WGS84 decimal-degree coordinates and local GPS
timestamps in UTC+02:00.

## How this reduced workbook was produced

- Six elephants with a nominal 15-minute collar schedule were retained.
- A dense block of 10,000 consecutive fixes was retained per elephant.
- Total reduced size: 60,000 rows.
- The source latitude/longitude fields for the retained LOAF-18 rows were reversed;
  the workbook swapped them to the correct approximately 19 degrees south,
  34 degrees east positions.
- Repeated AnimalID + Timestamp source rows were consolidated with median coordinates.
- `RecordsCombined` records how many source rows were consolidated.
- `DOP` was removed because it was entirely missing.
- `HDOP` was retained for traceability but is constant at zero in this subset.
- Random sampling was not used because it would destroy trajectory order.

## Licence and citation

Dryad publishes datasets under the Creative Commons Zero (CC0) Public Domain
Dedication. Reuse and modification are permitted. The dataset will still be
cited in the report, README, and presentation as scholarly attribution.
