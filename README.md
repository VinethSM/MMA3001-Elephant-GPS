# Elephant GPS Sampling-Accuracy Optimisation

## Project overview

This MMA3001 project investigates how reducing the frequency of elephant GPS collar recordings affects movement-path reconstruction accuracy.

The supplied reduced dataset contains 60,000 GPS observations from six elephants. Its modal and median recording interval is 15 minutes. The project simulates less frequent 30, 60, 120 and 240-minute sampling schedules and reconstructs the withheld locations using linear interpolation, natural cubic-spline interpolation and PCHIP interpolation.

GPS-fix reduction is used only as a proxy for reduced collar resource use. The dataset does not contain battery or power-consumption measurements, so this project does not claim an exact improvement in battery life.

## Engineering question

Which simulated GPS sampling interval provides the greatest reduction in recorded fixes while remaining within the project-defined position and path-accuracy limits, and which interpolation method provides the best balance of accuracy, robustness and physically reasonable behaviour?

## Final recommendation

The final recommendation is:

- **Sampling interval:** 30 minutes
- **Reconstruction method:** PCHIP
- **Median position error:** 39.632 m
- **Median absolute path-length error:** 7.907%
- **Median GPS-fix reduction:** 49.894%
- **Coordinate overshoots:** 0
- **Animals passing both mandatory criteria:** 6 out of 6

PCHIP at 30 minutes was selected because it passed both mandatory criteria, produced the lowest median position error of the three methods at this interval and did not produce coordinate overshoots.

This recommendation is intended for broad-scale movement monitoring under the assumptions and tolerances used in this project. The original 15-minute interval, or a separately validated shorter interval, should be retained when fine-scale or safety-critical movement information is required.

## Acceptance criteria

The following project-defined criteria were fixed before the full validation experiment:

- Median position error must be no greater than 100 m.
- Median absolute path-length error must be no greater than 10%.
- Both criteria must be satisfied for all six elephants.

These are working engineering tolerances for comparing the tested alternatives. They are not claimed to be universal wildlife-monitoring standards.

## Data

The project uses the supplied reduced workbook:

```text
data/raw/Elephant_GPS_Reduced_60000.xlsx
```

The workbook contains:

- 60,000 GPS fixes;
- six elephants;
- 10,000 consecutive observations per elephant;
- timestamps;
- elephant identifiers;
- latitude and longitude coordinates in decimal degrees;
- a modal and median source interval of 15 minutes.

The source audit found:

- no missing required values;
- no duplicate elephant-timestamp events;
- no invalid coordinates;
- no timestamp or calendar inconsistencies;
- 70 original recording gaps longer than 30 minutes;
- six jump-and-return spatial-spike candidates.

After removing the six documented spikes, the cleaned reference contained 59,994 observations and 77 continuous trajectory segments.

The 15-minute observations are treated as the available high-frequency reference. They are recorded GPS observations and are not continuous ground truth for the elephant's complete movement between fixes.

## Data source and privacy

The original dataset is publicly available from Dryad:

<https://doi.org/10.5061/dryad.m905qfv85>

The source dataset is provided under CC0 reuse conditions.

The supplied reduced workbook and generated exact-coordinate files are excluded from the public GitHub repository. They must be provided separately or downloaded and prepared before running the complete workflow. De-identified results, summary tables and suitable figures are retained in the public repository.

## Inputs and outputs

### Primary inputs

| Input | Meaning |
|---|---|
| Animal identifier | Identifies the elephant associated with each observation |
| Timestamp | Date and time of the GPS observation |
| Latitude | WGS84 latitude in decimal degrees |
| Longitude | WGS84 longitude in decimal degrees |
| Sampling interval | Simulated interval of 30, 60, 120 or 240 minutes |
| Starting offset | Determines which observations become retained anchors; every valid offset is tested automatically |
| Reconstruction method | Linear, natural cubic spline or PCHIP |

`SegmentID` is not manually entered. It is generated automatically so that reconstruction cannot cross a recording gap longer than 30 minutes.

### Main outputs

The workflow produces:

- a cleaned high-frequency reference dataset;
- continuous trajectory segment identifiers;
- simulated retained and withheld observations;
- reconstructed coordinates for eligible withheld observations;
- position-error and path-length-error measurements;
- GPS-fix-reduction measurements;
- method and interval comparison tables;
- sensitivity and failure-case figures;
- a final method and sampling-interval recommendation;
- automated test and HTML source-code documentation.

Invalid coordinates, missing required values, duplicate events and unsupported sampling settings are detected by validation checks. Movement values are not calculated across segment boundaries.

## Computational workflow

The main stages are:

1. Audit and validate the supplied workbook.
2. Parse and sort timestamps and coordinates.
3. Inspect and remove only the six documented jump-and-return spikes.
4. Start a new trajectory segment after each gap longer than 30 minutes.
5. Calculate elapsed time, movement distance, speed and local planar coordinates.
6. Simulate reduced 30, 60, 120 and 240-minute sampling schedules.
7. Test every valid starting offset.
8. Reconstruct eligible withheld observations using linear, cubic and PCHIP interpolation.
9. Compare reconstructed positions with the withheld 15-minute observations.
10. Calculate accuracy, robustness, failure and computational-performance metrics.
11. Select the method and interval using the predefined acceptance criteria.

Only observations strictly between retained anchors are scored. Points outside the first and last anchors are excluded because estimating them would require extrapolation.

A common-eligible validation population is used so that the interpolation methods are compared using the same supported cases.

## Validation scale

The full validation experiment contained:

- 2,138 common supported cases;
- 6,414 method-case evaluations;
- 4,607,787 reconstructed prediction rows;
- zero unexpected failed common cases.

The validation systematically withheld eligible 15-minute observations and compared their recorded positions with positions reconstructed from the retained anchors. This is not a random 80/20 train-test split, and no elephant was permanently held out as an independent external test subject.

## Results

### Comparison at the 30-minute interval

| Method | Median position error (m) | Median absolute path error (%) | Median fix reduction (%) | Coordinate overshoots (%) | Mandatory criteria |
|---|---:|---:|---:|---:|---|
| Linear | 40.786 | 8.180 | 49.894 | 0.000 | Pass |
| Cubic | 42.615 | 5.275 | 49.894 | 32.696 | Pass |
| PCHIP | 39.632 | 7.907 | 49.894 | 0.000 | Pass |

Although cubic interpolation had the lowest median path error, it produced coordinate overshoots in approximately 32.7% of cases. PCHIP provided the lowest median position error without overshoot, making it the preferred overall method.

### Sampling-interval decisions

| Interval | Approximate fix reduction | Result |
|---:|---:|---|
| 30 minutes | 49.894% | All three methods passed both criteria |
| 60 minutes | 74.840% | All methods failed the 10% path-error criterion |
| 120 minutes | 87.319% | All methods failed both mandatory criteria |
| 240 minutes | 93.561% | All methods failed both mandatory criteria |

The longer intervals reduced more GPS fixes, but the resulting reconstruction errors were too large under the predefined criteria.

## Repository structure

```text
MMA3001_project/
├── data/
│   ├── raw/                 # Private supplied workbook
│   └── processed/           # Private cleaned coordinate data
├── docs/                    # Generated HTML source-code documentation
├── figures/                 # Public de-identified figures
├── notebooks/               # Audit, exploration and decision notebooks
├── private_figures/         # Exact-coordinate figures excluded from Git
├── reports/                 # Audits, decisions, summaries and test report
├── src/                     # Reusable Python source code
├── tests/                   # Automated pytest tests
├── .gitignore
├── README.md
└── requirements.txt
```

## Installation

The project was developed using Python 3.14.7 on Windows.

From the project root, create and activate the virtual environment:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Confirm that the environment is working:

```powershell
python --version
python -m pip check
```

## Quick demonstration

Run the short demonstration using:

```powershell
python -m src.demo
```

The demonstration runs PCHIP reconstruction at the selected 30-minute interval on one suitable de-identified trajectory segment. It is intended for the presentation and does not replace the full validation study.

Source modules should be run with `python -m`. For example, use `python -m src.demo` rather than `python src/demo.py`.

## Reproduce the workflow

The raw workbook must first be placed in `data/raw`.

Run the data audit:

```powershell
python -m src.data_audit
```

Run preprocessing:

```powershell
python -m src.preprocessing
```

Run all automated tests:

```powershell
python -m pytest -q
```

Run the complete validation experiment:

```powershell
python -m src.validation
```

The full experiment evaluates 6,414 method-case combinations and creates more than 4.6 million prediction rows, so it takes longer than the quick demonstration.

## Test report

Generate the self-contained HTML test report using:

```powershell
python -m pytest -q --html=reports\test_report.html --self-contained-html
```

Open it on Windows using:

```powershell
Start-Process .\reports\test_report.html
```

The final test suite contains 19 tests.

## Source-code documentation

Generate the HTML documentation using:

```powershell
python -m pdoc src -o docs
```

Open the documentation using:

```powershell
Start-Process .\docs\src.html
```

## Optimisation and performance

The full validation workflow was timed before and after reducing repeated sorting and DataFrame construction.

| Measurement | Result |
|---|---:|
| Baseline runtime | 131.019 s |
| Optimised runtime | 125.494 s |
| Time saved | 5.525 s |
| Runtime reduction | 4.22% |
| Speed-up | 1.044× |

All 19 tests continued to pass, and the scientific results remained unchanged after optimisation.

Profiling showed that repeated Pandas data handling inside the reconstruction workflow was the main computational bottleneck. The interpolation calculations themselves were not the main source of runtime. The measured improvement was modest and is limited by the use of one before-and-after timing measurement on the same computer.

## Important limitations

- The study uses a reduced dataset containing six elephants, so the result should not automatically be generalised to all elephants, habitats or collar systems.
- The 15-minute GPS observations are an empirical reference rather than continuous movement ground truth.
- No elephant was reserved as a completely independent external test animal.
- GPS-fix reduction is only a proxy for possible resource savings.
- Battery life, transmission energy and hardware behaviour were not measured.
- The 100 m and 10% acceptance limits are project-defined working tolerances rather than universal standards.
- Large gaps and the ends of trajectory segments are not reconstructed.
- PCHIP reconstruction cannot recover unobserved fine-scale movement that occurs between recorded fixes.
- The public repository excludes exact-coordinate data for privacy and responsible data handling.

## AI-use disclosure

ChatGPT/Codex was used to support project planning, code scaffolding, troubleshooting, interpretation of outputs and documentation development. AI-generated suggestions were checked by running the code, inspecting the outputs, comparing numerical results and using automated tests.

The student remained responsible for the project scope, acceptance criteria, preprocessing decisions, selection of the validation population, final PCHIP 30-minute recommendation and all submitted claims. A detailed AI-use reflection is included in the written project documentation.