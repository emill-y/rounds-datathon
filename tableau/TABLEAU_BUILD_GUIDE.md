# Rounds: Tableau dashboard build guide (about 60–90 min)

Build this in Tableau Public (free). You'll make two dashboards: **"The Rescue Gap"** for hospital administrators and **"The 60-Second Check"** for nurse managers. Publish both, then put the link in the README and slides.

## 0. Connect the data (5 min)
Use **Connect → Text file** and add all five CSVs from this folder as separate data sources. There's no need to join them in Tableau, because the joins are already done in the notebook.

| File | Rows | One row = |
|---|---|---|
| `tableau_counties.csv` | 1,011 | a US county with at least one rated hospital |
| `tableau_hospitals.csv` | 2,316 | a hospital |
| `tableau_patients.csv` | 1,000 | a Track 1 patient, with Rounds' out-of-fold probabilities |
| `tableau_by_number_of_vitals.csv` | 24 | model × how many vitals were measured |
| `tableau_vital_combinations.csv` | 252 | model × a specific combination of vitals |

**Important:** in `tableau_counties.csv` and `tableau_hospitals.csv`, right-click **FIPS → Change Data Type → String**, then set **Geographic Role → County**. If Tableau dropped the leading zeros (for example "1001" instead of "01001"), create a calculated field `FIPS5 = RIGHT("0" + STR([FIPS]), 5)` and use that instead.

Colors to use everywhere: High `#C0392B`, Medium `#F2A541`, Low `#9BC53D`, Normal `#4C9F70`, Rounds `#1F4E79`, NEWS2 `#C0392B` (dashed).

---
## Dashboard 1: "The Rescue Gap" (hospital administrators)

**Sheet 1a: KPI tiles.** Use text sheets. Big numbers:
- `SUM([Excess_deaths]) / 2` → **≈3,400 excess deaths per year** (source: tableau_hospitals)
- Count of hospitals where `FTR_vs_national = "Worse Than the National Rate"` → **272**
- Subtitle: "vs. the best-performing 25% of US hospitals · CMS ISCMR, Jul 2023–Jun 2025"

**Sheet 1b: County map.** Source: tableau_counties.
- Double-click FIPS (County role) to get a filled map.
- Color = `SUM(excess_deaths_2yr)`, sequential red. Tooltip: County, ST, hospitals, FTR_rate_weighted, SVI_overall, Help_ASAP_score.
- Filter: `Rural` (0/1), shown as a single-value toggle labeled "Rural counties only."

**Sheet 1c: Vulnerability bar.** Source: tableau_hospitals.
- Columns = `SVI_quartile`. Rows = calculated field `Pct Worse = AVG(IIF([FTR_vs_national]="Worse Than the National Rate",1,0))`, formatted as a percentage.
- Expect about 6.6% (Q1) rising to 18.8% (Q4). Title: "Hospitals in the most vulnerable communities are 2.8× as likely to fail at rescue."

**Sheet 1d: Response-time bar.** Same as 1c but Columns = `Help_quartile`. Expect 17.8% for "slowest help" down to 5.6% for "fastest help." Title: "Where patients wait for help, more patients aren't rescued."

**Sheet 1e: Hospital scatter.** X = `Help_ASAP_score`, Y = `FTR_rate`, Size = `FTR_cases`, Color = `SVI_overall`. Add a trend line. Tooltip includes Facility Name. Filter on State.

**Layout:** KPI tiles across the top, the map on the left (about 60% width), and 1c/1d stacked on the right, with the scatter below. Add a State filter that applies to all sheets using this data source.

---
## Dashboard 2: "The 60-Second Check" (nurse managers)

**Sheet 2a: The core result (line chart).** Source: tableau_by_number_of_vitals.
- Columns = `n_vitals` (dimension, discrete). Rows = `high_recall` (format as %). Color = `model`.
- Filter out "Majority class" (or keep it as a grey floor). Make NEWS2 a dashed red line and Rounds a thick navy line.
- Annotate the point at n_vitals = 2: "NEWS2 catches 27% of high-risk patients · Rounds catches 86%."

**Sheet 2b: Dangerous misses.** Same as 2a but Rows = `dangerous_miss`. Title: "High-risk patients wrongly called Low or Normal."

**Sheet 2c: Which vitals to take first.** Source: tableau_vital_combinations, filtered to model = "Rounds".
- Rows = `vitals`, Columns = `high_recall`, sorted descending. Add an `n_vitals` quick filter (single value, slider), defaulting to 3.
- Highlight `RR+SpO2+BP` (97% caught, 0 dangerous misses).

**Sheet 2d: Patient explorer.** Source: tableau_patients.
- X = `Respiratory_Rate`, Y = `Oxygen_Saturation`, Color = `Risk_Level`, Size = `P_High`.
- Parameters let users filter by Heart_Rate and Systolic_BP ranges. Tooltip shows all vitals, NEWS2_total, and P_High.

**Sheet 2e: Guessed RR callout (text).** "Charting RR as '18' without counting it drops NEWS2 accuracy from 98.7% to 82.6%. Leaving it blank and letting Rounds account for it keeps 96.8% of high-risk patients flagged." (These numbers come from `outputs/guessed_rr_experiment.csv`.)

**Layout:** 2a and 2b side by side on top, 2c bottom-left, 2d bottom-right, and the callout as a banner.

---
## Optional: story points (great for the video)
Use a Tableau **Story** with 4 points: (1) KPI and map, "3,400 people a year"; (2) vulnerability and response-time bars, "who it hits"; (3) the 2a line chart, "the standard score breaks when vitals are missing"; (4) 2c, "RR → SpO2 → BP: the 60-second check."

## Publish
File → Save to Tableau Public. Copy the URL into the README and onto the last slide.
