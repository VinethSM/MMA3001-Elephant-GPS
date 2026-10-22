## D1 — Approve the six spatial removals

**Date:** 18/09/26

### Evidence inspected

I inspected `reports/week2_spike_candidates.csv` and
`private_figures/week2_candidate_spike_inspection.png`.

### My choice

I approved the removal of the six documented AnimalID–Timestamp events and no other records.

### My reason

Each approved event exceeded 5 m/s on both adjacent movements. The local trajectory also showed a sudden multi-kilometre displacement that did not match the surrounding GPS positions. I therefore treated these six records as spatial GPS errors.

### Rejected option

I rejected automatically deleting every observation above a general speed threshold. A genuine movement could otherwise be removed without inspecting the surrounding trajectory.

### Assumption or limitation

The screen identifies an implausible movement pattern, but it does not prove the exact physical reason for the GPS error.

### AI contribution

AI helped produce the adjacent-speed screening code and inspection figure. I checked the six records and made the final removal decision after inspecting the output.

### Interview explanation

I used 5 m/s as a transparent screening threshold, not an automatic deletion rule. I removed only six fixed, documented events after checking their adjacent speeds and surrounding movement paths.







## D2 — Confirm the trajectory segmentation rule

**Date:** 18/09/26

### Evidence inspected

I inspected the cleaned time-gap counts, the segment-start table and the time-gap distribution.

### My choice

I started a new trajectory segment only when the within-animal recording gap was greater than 30 minutes. A gap of exactly 30 minutes remained within the same segment.

### My reason

The normal recording interval is approximately 15 minutes. A gap above 30 minutes means that more than one expected recording opportunity may be absent. The animal’s movement during that period is not adequately supported by the available observations.

### Observed consequence

The original audit identified 70 gaps above 30 minutes. Removing the two consecutive GPS errors at 11:00 and 11:15 created one new 45-minute gap. The cleaned data therefore contained 71 long-gap boundaries and 77 segments across six elephants.

### Rejected option

I rejected connecting every observation into one uninterrupted path because this would calculate distance and speed across periods where the animal’s movement was unknown.

### AI contribution

AI helped implement the segmentation calculation. I confirmed the threshold and checked the segment and gap counts before accepting it.

### Interview explanation

The original schedule was approximately 15 minutes. I started a new segment after gaps above 30 minutes and left movement variables blank at segment starts so the program never calculated movement across unsupported periods.






## D3 — Choose the interpolation coordinate system

**Date:** 18/09/26


### Evidence inspected

I inspected `reports/week2_projection_comparison.csv` and compared local Euclidean step distances against Haversine step distances.

### My choice

I will use local x/y coordinates in metres for interpolation. I will use Haversine distance for final geographic positional-error calculations.

### My reason

The local x/y system gives both interpolation coordinates the same physical unit of metres. The comparison showed that its step distances were extremely close to the Haversine distances over the project’s study area.

### Actual comparison

- Median absolute difference: 0.004309 m
- 95th-percentile absolute difference: 0.119265 m
- Maximum absolute difference: 2.901643 m
- Maximum percentage difference: 0.218461%

### Rejected option

I rejected treating raw latitude and longitude degrees as equal physical distance coordinates because a degree of longitude and a degree of latitude do not represent the same number of metres.

### Limitation

The local equirectangular coordinates are an approximation tied to this geographical area. Final geographical errors will therefore still be checked using Haversine distance.

### AI contribution

AI helped implement the local coordinate conversion and comparison. I inspected the calculated differences and chose the coordinate system based on the output.

### Interview explanation

I interpolated in local x/y coordinates because both axes are measured in metres. I retained Haversine distance for final geographic errors so the reported validation results account for the Earth’s curvature.

## D4 — Interpolation methods retained after pilot

**Decision:** Retain linear interpolation, natural cubic-spline interpolation,
and PCHIP for the full reconstruction experiment.

**Reasoning:** Linear interpolation is retained as the simple baseline. PCHIP
produced the lowest median position error and RMSE at both pilot intervals and
had no detected overshoot. Cubic spline produced the lowest 95th-percentile
error and median absolute path-length error, but approximately 34–37% of its
pilot reconstructions contained coordinate overshoot. Linear interpolation was
the fastest method and had no overshoot, but generally produced larger position
and path-length errors.

All three methods completed the pilot without failed cases, and their absolute
runtime was small. Therefore, the pilot provides sufficient justification to
retain all three for full validation. PCHIP is treated as the primary
shape-preserving alternative, cubic spline as a smooth secondary alternative,
and linear interpolation as the baseline.

**Important limitation:** This pilot used only selected segments and the
60-minute and 120-minute intervals. It is not being used to select the final
sampling interval or declare a final winning method. Those decisions will be
made after validation across all eligible elephants, segments, intervals and
starting offsets.


## D5 — Validation population

Date:

Evidence inspected:
- reports/week3_support_audit.csv
- reports/week3_support_summary.csv

Decision:
I selected [common eligible / method-specific] validation cases.

Reason:
[Explain whether every method should be compared on identical withheld fixes.]

Handling of unsupported cases:
Cases with insufficient retained anchors will receive an explicit failure
status. Positions outside the first and last retained anchors will not be
extrapolated.

Limitation:
Using a common set can exclude fixes that the simpler method could otherwise
reconstruct. Method-specific coverage will therefore also be reported.

## D6 — Evaluation metrics and acceptance tolerances

**Decision:** Use median position error and median absolute path-length error as
the two mandatory acceptance criteria.

A method and sampling-interval combination will be classified as acceptable
only when:

- median position error is no greater than 100 metres; and
- median absolute path-length error is no greater than 10%.

Both criteria must pass. A result that passes only one criterion will be
classified as unacceptable.

Median position error represents typical reconstruction accuracy and is less
affected by isolated extreme errors than the mean. Absolute path-length error
is also mandatory because a reconstructed trajectory may have reasonable
pointwise accuracy while cutting across turns and underestimating the distance
travelled.

MAE, RMSE, 95th-percentile position error, signed path-length error,
coverage/failure rate, overshoot and runtime will be reported as diagnostic
metrics. They will be used to explain method behaviour and distinguish between
methods that pass the mandatory criteria, but they will not independently
determine acceptance.

The 100-metre and 10% limits are preliminary engineering design tolerances,
not established biological requirements. A later sensitivity analysis will
test position limits of 50, 100 and 150 metres and path-length limits of 5%,
10% and 15%.




## D7 — Final method and sampling interval

**Decision:** Select [METHOD] interpolation with a [INTERVAL]-minute nominal
GPS sampling interval.

**Evidence inspected:** The full common-eligible validation included all six
elephants, all supported continuous trajectory segments, every valid starting
offset and the 30-, 60-, 120- and 240-minute schedules.

The selected combination produced:

- median position error: [VALUE] metres;
- 95th-percentile position error: [VALUE] metres;
- median absolute path-length error: [VALUE]%;
- median GPS-fix reduction: [VALUE]%;
- animals passing both criteria: [VALUE] out of six; and
- coordinate overshoot: [VALUE]%.

**Reasoning:** [Write your personal reasoning here. Compare the selected
method with the rejected methods and explain the position/path/overshoot
trade-off.]

**What would change my decision:** [State what additional evidence would make
you choose another method, a shorter interval or an animal-specific policy.]

**Limitations:** The result measures reconstruction of withheld 15-minute GPS
fixes. It does not validate the unknown continuous path, exact battery-life
improvement, future elephant movement or every elephant population.





## D8 — Define the scope of the final recommendation

**Decision:** Use a conditional recommendation rather than claiming that
30 minutes is suitable for every elephant-monitoring application.

**Selected scope:** `conditional_policy`

**Recommendation:** Use PCHIP reconstruction with a 30-minute GPS
sampling interval when the objective is broad-scale elephant movement
monitoring and the accepted limits are a median position error of
100 metres and a median absolute path-length error of 10%. Retain the
original 15-minute interval, or investigate an intermediate interval,
when fine-scale movements such as sharp turns, road crossings, fence
crossings or proximity to hazards must be identified.

**Evidence:** PCHIP at 30 minutes produced a median position error of
39.632 metres and a median absolute path-length error of 7.907%, while
reducing the number of retained GPS fixes by 49.894%. All six elephants
passed both project criteria. The results were also almost unchanged
between the two possible 30-minute starting offsets.

**Limitation:** The case-level results showed that some individual
trajectory segments exceeded the overall tolerances, including some
path errors above 10% and isolated position errors of several hundred
metres. Therefore, passing the overall median criteria does not mean
that every individual movement or turn is reconstructed accurately.

**Evidence that would change the decision:** I would select a shorter
sampling interval if the application required reliable detection of
fine-scale or safety-critical movement, if further animals produced
errors above the project tolerances, or if testing showed that an
intermediate interval provided a better accuracy–fix reduction balance.





## D9 — Select the optimisation target

**Decision:** Target the repeated pandas DataFrame processing inside
`reconstruct_case`, beginning with `make_downsampling_mask` and repeated
column construction.

**Evidence:** The profiled experiment required 233.716 seconds and
approximately 280 million function calls. `reconstruct_case` accounted
for 193.844 seconds of cumulative time, approximately 83% of the
profiled runtime. Pandas DataFrame column assignment accounted for
71.787 seconds, while `make_downsampling_mask` accounted for 46.907
seconds. In comparison, interpolation required only 4.044 seconds and
saving predictions required 3.112 seconds.

**Optimisation hypothesis:** Reducing repeated DataFrame operations and
using simpler array-based mask construction should reduce runtime
without changing the sampling intervals, interpolation methods,
validation population or calculated accuracy results.

**Acceptance requirement:** I will retain the optimisation only if a
like-for-like benchmark shows a runtime improvement and the optimised
results remain numerically equivalent to the original results.


## D10 — Accept or reject the optimisation

**Decision:** Accept the optimisation.

**Baseline runtime:** 131.019 seconds

**Optimised runtime:** 125.494 seconds

**Absolute time saved:** 5.525 seconds

**Measured speed-up:** 1.044 times

**Runtime reduction:** 4.22%

**Correctness evidence:** All 19 automated tests passed after the
optimisation. The full experiment still contained 2,138 common cases,
6,414 method-case runs and 4,607,787 prediction rows, with zero
unexpected failures. All position-error, path-error and fix-reduction
results remained unchanged.

**Reason:** The optimisation produced a modest reduction in total
runtime without changing the sampling procedure, interpolation methods,
validation population or numerical results. The changes also preserved
the existing program structure and test behaviour. I therefore accepted
the optimised implementation.

**Limitation:** The before-and-after measurements were each obtained
from a single full run and may contain some variation caused by computer
background activity, caching and OneDrive. Therefore, I will describe
the 4.22% reduction as a measured modest improvement rather than a
guaranteed speed increase on every computer.

## D11 — Freeze the final scientific scope

**Decision:** Freeze the final computational scope and proceed to
documentation and submission preparation.

The final recommendation remains PCHIP reconstruction with a 30-minute
sampling interval for broad-scale elephant movement monitoring. This
produced a median position error of 39.632 metres, a median absolute
path-length error of 7.907% and a median GPS-fix reduction of 49.894%.

No additional interpolation methods, intervals or acceptance criteria
will be introduced after viewing the final results. Changes from this
point will be restricted to correcting genuine defects, improving
documentation, completing testing and preparing the demonstration.

The recommendation remains conditional because individual trajectory
segments can contain larger errors and the dataset does not contain
power-consumption measurements or continuous ground-truth movement.