# Rounds: three Tableau dashboards, click by click

You'll need Tableau Public (free) or Tableau Desktop, and the CSVs in this folder. Budget about 30 minutes per dashboard. To rebuild the CSVs, run `python src/tableau_exports.py`.

**Colors to use everywhere:** High `#C0392B` · Medium `#F2A541` · Low `#9BC53D` · Normal `#4C9F70` · Rounds `#1F4E79` (navy) · NEWS2 `#C0392B` (red) · Missing `#D5D8DC` (grey) · Measure next `#F1C40F` (yellow).

**Before you start, two settings that save pain:**
- In the data source tab, check every ID or code column (`ZIP`, `FIPS`, `Facility ID`) is a **String** (click the little "#" icon above the column and choose String). Otherwise Tableau drops the leading zeros.
- When you drag a number onto Columns/Rows and it shows `SUM(...)`, that's fine. Each file already has one row per thing being plotted.

---

## Dashboard 1: Patient Priority ("who do I check first?")

**Files:** `d1_patient_priority.csv` (40 rows, one per bed) and `d1_patient_vitals_long.csv` (240 rows, one per bed × vital).
**What it shows:** a de-identified 40-bed night ward where about 40% of vitals haven't been charted yet. Rounds ranks the beds and says which vital to take next. Patient labels like `PT-1021` are fictional, and all predictions are out-of-fold (no patient was scored by a model that saw them during training).

### 1A. Connect
1. **Connect → To a File → Text file →** `d1_patient_priority.csv`.
2. Top menu **Data → New Data Source → Text file →** `d1_patient_vitals_long.csv`.

### 1B. Sheet "Priority list" (source: d1_patient_priority)
1. Rename Sheet 1 to **Priority list** (double-click the tab).
2. Drag **Priority_rank** to **Rows**. Right-click it → **Dimension**, then right-click again → **Discrete** (it turns blue).
3. Drag **Bed**, **Patient**, **Rounds_risk**, **Missing_vitals**, and **Next_measurement** to **Rows**, in that order, to the right of Priority_rank.
4. Drag **P_High** to **Text** on the Marks card. Right-click it on Marks → **Format** → Numbers → **Percentage**, 0 decimals.
5. Drag **Rounds_risk** to **Color** on the Marks card. Click Color → Edit Colors and set High/Medium/Low/Normal to the hex codes above.
6. Change the Marks dropdown from Automatic to **Square** so each P(High) cell fills with its risk color.
7. Drag **NEWS2_risk_today** to Rows as well, after Rounds_risk. This shows judges the standard score's answer right next to ours.
8. Right-click **Priority_rank** → **Sort** → Ascending.

### 1C. Sheet "Vitals grid" (source: d1_patient_vitals_long)
1. New worksheet, renamed **Vitals grid**. Select the `d1_patient_vitals_long` data source at the top left.
2. Create a calculated field (**Analysis → Create Calculated Field**) named **Cell**:
   ```
   IF [Is_next] = "Measure next" THEN "Measure next"
   ELSEIF [Status] = "Missing" THEN "Missing"
   ELSE "Charted" END
   ```
3. Drag **Vital** to **Columns**. Right-click it → **Sort → Sort by Field → Vital_order, Minimum, Ascending**. That gives RR → SpO2 → BP → HR → ACVPU → Temp, the measurement priority order.
4. Drag **Bed** to **Rows**. Right-click → **Sort → Sort by Field → Priority_rank, Minimum, Ascending**.
5. Marks type: **Square**. Drag **Cell** to **Color** and set Charted = white, Missing = grey `#D5D8DC`, Measure next = yellow `#F1C40F`.
6. Drag **Value** to **Label**. Missing cells stay blank, so the grey squares read as "not measured."

### 1D. KPI tiles (source: d1_patient_priority), one small sheet each
- **Beds:** drag `Bed` to Text, then right-click → Measure → **Count (Distinct)** → 40.
- **Flagged High by Rounds:** create a calculated field `High flag = IIF([Rounds_risk]="High",1,0)`, then drag SUM(High flag) to Text.
- **Vitals not yet charted:** SUM(`Missing_count`).
- **High-risk patients NEWS2 would miss tonight:** create a calculated field `NEWS2 miss = IIF([NEWS2_would_miss]="Yes",1,0)`, then SUM to Text. (In this ward, **Bed 11** is truly High risk. NEWS2 calls them **Low** because RR, SpO2, BP, and HR are all missing. Rounds ranks them #10 with P(High) 0.80.)
For each tile, click Text on the Marks card → "…" and type a label above the number. Make the font about 28pt.

### 1E. Assemble
1. **Dashboard → New Dashboard**, Size → **Automatic**.
2. Put the four KPI tiles across the top using a **Horizontal** layout container. Below them, put **Priority list** on the left (55% width) and **Vitals grid** on the right.
3. **Click-to-highlight:** **Dashboard → Actions → Add Action → Highlight**. Source: Priority list. Target: Vitals grid. Run on: **Select**. Target highlighting: **Selected Fields → Bed**. Now clicking a bed lights up its row of vitals.
4. Add a filter: on the Priority list sheet, right-click **Rounds_risk** → Show Filter. In the dashboard, make it apply to related sheets.
5. Title: **"Rounds: who to check first, and what to measure next"**. Add a text box: *"Fictional bed and patient labels. Real de-identified vitals from the Track 1 dataset, with about 40% hidden to mimic a night round. All predictions are out-of-fold."*
6. **Don't** show `True_risk_validation_only` on the dashboard. That's only for you to check against.

---

## Dashboard 2: NEWS2 vs Rounds as vitals go missing

**File:** `d2_missingness_curves.csv` (48 rows: 2 methods × 6 missingness levels × 4 alert rules). `d2_missingness_runs.csv` holds every individual run, if you want error bars.
**What it shows:** each vital is hidden at random with probability 0%, 10%, … 50%. That's repeated 5 times × 5 cross-validation folds (all 1,000 patients each time), then averaged.

**Alert rules (`alert_rule` column):**
- `Top 20% / Top 28% / Top 35% alerted`: **matched alert rates**. Both methods raise exactly the same number of alerts (the riskiest X% of patients by NEWS2 total, or by Rounds' P(High)), so the comparison is fair. Use **Top 28%** as the default view, because 28% of patients are truly High risk.
- `Default threshold (High)`: each method used as-is (NEWS2 ≥ 7 vs Rounds predicting "High"). This is what happens on a real ward.

### 2A. Connect and set up the filter
1. Connect → Text file → `d2_missingness_curves.csv`.
2. Drag **missing_pct** to Columns. Right-click → **Dimension**, then right-click → **Continuous** (it turns green, which gives you a smooth line axis).
3. Drag **alert_rule** to **Filters**, select only **Top 28% alerted**, and click OK. Then right-click the filter → **Show Filter**, and in its dropdown arrow choose **Single Value (dropdown)**. Right-click the filter again → **Apply to Worksheets → All Using This Data Source**.

### 2B. Sheet "Recall"
1. Rows: **recall**. Right-click → Format → Percentage.
2. Drag **method** to **Color** (Rounds navy, NEWS2 red). Marks type: **Line**, and click Shape/Path to turn on markers.
3. Click Color → Markers → **All** to show points.
4. Edit the axis title to *"High-risk patients caught"* and the x-axis to *"% of vitals missing"*.
5. Optional annotation: right-click the Rounds point at 50% → **Annotate → Mark** → *"91.6% vs 81.0%"*.

### 2C. Sheet "Precision"
Duplicate the Recall sheet (right-click the tab → Duplicate) and swap **recall** for **precision** on Rows.
> Note for judges: when the alert rate equals the share of truly High-risk patients (Top 28%), precision and recall are mathematically almost identical. That's expected, not a bug. Switch the filter to Top 20% or Top 35% to see them separate.

### 2D. Sheet "False alerts"
Duplicate again and use **false_alerts_per_100** on Rows. Title: *"False alarms per 100 patients"*. Optionally make a fourth duplicate with **missed_high_per_100** titled *"High-risk patients missed per 100"*. That's the one that matters most clinically.

### 2E. Assemble
1. New Dashboard. Put the **alert_rule** dropdown at the top right.
2. Lay out three tiles side by side (Recall | Precision | False alerts), with Missed-per-100 underneath if you made it.
3. Add a text box with the key numbers (out-of-fold, average of 25 runs):

| % vitals missing | Matched alerts (top 28%): NEWS2 recall | Rounds recall | Default thresholds: NEWS2 recall | Rounds recall |
|---|---|---|---|---|
| 0% | 100% | 98.6% | 100% | 98.6% |
| 30% | 86.8% | 95.5% | 81.7% | 94.5% |
| 50% | 81.0% | 91.6% | 58.8% | 91.6% |

   Headline: *"With half the vitals missing, NEWS2 at its normal threshold misses 4 in 10 high-risk patients. Rounds misses fewer than 1 in 10."*
4. Be honest in a footnote: *"With all vitals measured, NEWS2 is the ceiling: the labels are NEWS2. Rounds' value is when vitals are missing. At matched alert rates, Rounds raises 2.4 false alerts per 100 patients at 50% missingness vs 5.4 for NEWS2. At default thresholds, NEWS2 raises no false alerts but misses far more patients."*

---

## Dashboard 3: National failure-to-rescue map

**Files:** `d3_hospitals.csv` (2,316 hospitals) and `d3_states.csv` (51 rows).
**Measure:** CMS **ISCMR, Inpatient Surgical Complications Mortality Rate**, the current replacement for PSI-04 "failure to rescue". It's deaths per 1,000 surgical patients who developed a serious, treatable complication, July 2023 to June 2025. This is **hospital-level public data, separate from the patient model**, so say so in a subtitle.

### 3A. Connect
1. Connect → Text file → `d3_hospitals.csv`. In the data source grid, set **ZIP**, **FIPS**, and **Facility ID** to **String**.
2. Click the type icon on **ZIP** → **Geographic Role → ZIP Code/Postcode**. On **State** → Geographic Role → **State/Province**.
3. Data → New Data Source → `d3_states.csv`, and set **State** → Geographic Role → State/Province.

### 3B. Sheet "State map" (source: d3_states)
1. Double-click **State**, and Tableau draws a map.
2. Change Marks to **Map** (filled). Drag **excess_deaths_per_year** to **Color**, then Edit Colors → Red sequential.
3. Drag **FTR_rate_weighted**, **hospitals**, and **hospitals_worse_than_national** to **Tooltip**.
4. Title: *"Excess failure-to-rescue deaths per year, vs. the best 25% of hospitals"*.

### 3C. Sheet "Hospital map" (source: d3_hospitals)
1. Double-click **ZIP** to get one dot per hospital.
2. Drag **FTR_rate** to **Color**: Edit Colors → **Red-Blue Diverging**, reversed so red means high. Click Advanced → Center **53**, which is roughly the national average.
3. Drag **FTR_cases** to **Size** (bigger dot = more patients).
4. Drag **Hospital**, **City**, **FTR_rate**, **Lower Estimate**, **Higher Estimate**, **FTR_vs_national**, **Help_ASAP_score**, and **SVI_overall** to **Tooltip**.
5. Show filters for **FTR_vs_national**, **Rural**, **SVI_quartile**, and **State** (right-click each → Show Filter).

### 3D. Sheet "Who it hits" (source: d3_hospitals), two bar charts
1. Create calculated fields:
   - `Worse flag = IIF([FTR_vs_national] = "Worse Than the National Rate", 1, 0)`
   - `% worse than national = AVG([Worse flag])` (format as a percentage)
   - `Excess deaths per year = SUM([Excess_deaths_2yr]) / 2`
2. **Vulnerability bar:** Columns **SVI_quartile**, Rows **% worse than national**. Expect 6.6% → 18.8%. Title: *"Hospitals in the most vulnerable counties are 2.8× as likely to fail at rescue"*. Right-click "nan" (unmatched counties) → Exclude.
3. **Response bar** (duplicate the sheet): swap in **Help_quartile**. Expect 17.8% for slowest help vs 5.6% for fastest. Title: *"Where patients wait for help, more aren't rescued"*.
4. Optional third bar: **Rural** vs Urban with **Excess deaths per year**.

### 3E. KPI tiles (source: d3_hospitals)
- **≈3,387 excess deaths per year:** the `Excess deaths per year` field on Text.
- **272 hospitals worse than national:** SUM(Worse flag).
- **2,316 hospitals rated:** CNTD(Facility ID).

### 3F. Assemble
1. New Dashboard. KPI tiles go on top, the State map at the large left, and the Hospital map at the right (or use a **sheet-swap**: show one map at a time with a parameter, or just put them on two dashboard tabs).
2. Put the two bars underneath.
3. **Filter action:** Dashboard → Actions → Add Action → **Filter**. Source: State map. Targets: Hospital map and both bars. Run on: **Select**. Fields: **Selected Fields**, State → State. Since these are two data sources, map the field explicitly. Clicking a state now zooms the hospital dots and bars to that state.
4. Subtitle: *"Hospital-level CMS data (ISCMR, successor to PSI-04), Jul 2023 to Jun 2025. Separate from the patient-level Rounds validation. Associations, not causes."*

---

## Publishing
1. **File → Save to Tableau Public As…** and give each dashboard a name (or put all three in one workbook as tabs; a **Story** works nicely for the video).
2. Open the published page and copy the URL.
3. Send it back here, and I'll add it to the README.
