# Engineering contract: elephant GPS sampling project

## Engineering question

Which simulated GPS sampling interval minimises the number of collar fixes while
keeping elephant movement-path reconstruction within the provisional accuracy
limits, and how does cubic-spline interpolation compare with linear interpolation?

## Primary inputs

- `AnimalID`: one of the six audited elephant identifiers.
- `Timestamp`: parseable local GPS time (UTC+02:00), ordered within each animal.
- `Latitude`: WGS84 decimal degrees in the audited spatial domain.
- `Longitude`: WGS84 decimal degrees in the audited spatial domain.
- `sampling_interval_minutes`: one of 30, 60, 120, or 240 minutes.
- `method`: linear interpolation baseline or cubic-spline alternative.

`Species`, `Year`, `DayOfYear`, `HDOP`, and `RecordsCombined` are retained for
metadata or audit checks. They are not primary predictors.

## Required outputs

- Reconstructed latitude and longitude at deliberately omitted timestamps.
- Pointwise position error in metres.
- Median, RMSE, and 95th-percentile position error.
- Absolute percentage error in reconstructed total path length.
- Percentage reduction in GPS fixes.
- Runtime for each interval and method.
- Longest interval that passes the approved tolerance.

## Supported domain

- Workbook schema and six AnimalIDs verified by the Week 1 audit.
- Timestamps from 2018-08-17 01:16:00 to 2019-12-06 01:00:00.
- Observed latitude from -19.12931 to -18.74630 degrees.
- Observed longitude from 34.18622 to 34.60529 degrees.
- Coordinate validity: latitude -90 to 90; longitude -180 to 180.
- Tested intervals: 30, 60, 120, and 240 minutes, all multiples of the 15-minute reference interval.
- Interpolation only inside a continuous trajectory segment. Do not interpolate
  across a source gap above 30 minutes and do not extrapolate beyond segment ends.

## Provisional acceptance limits

- Median reconstruction error <= 100 metres.
- Absolute total path-length error <= 10 percent.
- Always report the 95th-percentile error even though it has no initial pass/fail threshold.
- Treat these as initial engineering assumptions and perform sensitivity analysis later.

## Intended engineering use

Compare tracking detail against the number of required GPS fixes so that a
defensible collar sampling schedule can be recommended for these data.

## Unsupported uses and claims

- Do not claim an exact battery-life increase: the workbook has no power/current data.
- Do not claim future movement prediction: this is reconstruction of withheld points.
- Do not claim the 15-minute reference is the elephant's exact continuous path.
- Do not generalise results to every elephant or every location.
- Do not interpolate across long source gaps.
- Do not use HDOP as a quality predictor here because it is constant at zero.
