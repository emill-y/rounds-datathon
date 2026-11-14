# Rounds: catching deteriorating patients when vitals are incomplete
Datathon for Social Good 2025 · Track 1: Public Health Risk

**Problem.** In US hospitals, about 3,400 surgical patients a year die from treatable complications beyond what the best-performing hospitals achieve (CMS failure-to-rescue measure, 2023–2025). These deaths concentrate in socially vulnerable and rural communities, and in hospitals where patients wait longest for help. On busy wards vitals get skipped or guessed, and the standard warning score (NEWS2) quietly stops working.

**What we built.** *Rounds* is a model that predicts a patient's risk level from whatever vitals were actually measured, plus a data-driven "60-second check" telling nurses which vitals to take first.

**Key results (5-fold cross-validation, held-out patients)**
| Vitals measured | NEWS2 catches High-risk | Rounds catches High-risk |
|---|---|---|
| 2 of 6 | 27% | 86% |
| 3 of 6 | 63% | 92% |
| RR + SpO2 + BP only | 91% | **97%** (0 called Low/Normal) |

- The dataset's labels are NEWS2 itself (98.7% match), so we evaluate on the realistic problem of missing vitals instead of rebuilding the formula.
- A guessed respiratory rate ("18") drops NEWS2 accuracy from 98.7% to 82.6%.
- Hospital model (CMS + CDC SVI + HRSA + HCAHPS) predicts failure-to-rescue rate with R² 0.23 vs 0 for a mean baseline.

## Reproduce
[Open in Colab](https://colab.research.google.com/github/emill-y/rounds-datathon/blob/main/Rounds_Track1.ipynb), then Runtime → Run all. The notebook downloads its data from this repo's `data/` folder, so you don't upload anything. Runtime is about 1 minute.

| Data (`data/`) | Source |
|---|---|
| Health_Risk_Dataset.csv | Datathon Track 1 (Apache 2.0) |
| Complications_and_Deaths-Hospital.csv* | data.cms.gov/provider-data |
| Hospital_General_Information.csv | data.cms.gov/provider-data |
| HCAHPS-Hospital.csv* | data.cms.gov/provider-data |
| SVI_2022_US_COUNTY.csv | CDC/ATSDR Social Vulnerability Index 2022 |
| BCD_HPSA_FCT_DET_PC.csv* | data.hrsa.gov (Shortage Areas, Primary Care) |

\* Trimmed to the measures and columns we use so they fit on GitHub (the raw HCAHPS file is about 170 MB). `python src/make_trimmed_data.py <raw_dir> data` rebuilds them from the original downloads.

`src/` has the same analysis as plain scripts, plus `next_vital.py`, an adaptive measurement policy we tested and rejected. `tableau/` has the dashboard extracts and build guide. `outputs/` has the figures.

## Limitations
Labels are a formula, not outcomes. There are 1,000 patients, no demographics, and no time series. Pulse-oximeter bias on darker skin affects any SpO2-based score. Missingness is tested exhaustively rather than observed. Hospital findings are associations, not causes. See notebook sections 9 and 11.
