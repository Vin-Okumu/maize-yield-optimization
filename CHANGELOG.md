# Changelog

## 2.0.2 · November 2026

- **All published results now come from the synthetic sample.** README, analysis report, project charter, data documents, client deck, notebooks, figures, tables, map, decision tool and audit log were regenerated or updated so every number matches the notebook outputs.
- Notebook and pipeline outputs are always written to the repository's report folders (no separate `outputs_sample/` folder).
- Enrichment downloads in notebook 05 are switched off for the synthetic sample, whose coordinates are made up.
- The mixed model drops variables that take a single value (DAP in the synthetic sample) instead of reporting a meaningless estimate.

## 2.0.0 · November 2026

A restructure to bring the project to a professional, reproducible standard.

### Data handling
- **Removed the confidential trial data from the repository and its history.** The real files now live only in the git-ignored `01_Data/raw/`.
- Added a **synthetic sample** (`01_Data/sample/`, `scripts/make_synthetic_data.py`) with the same columns and data-quality problems, so everything runs without the real data.
- Published maps round coordinates to ~1 km; the exact map is generated locally only.
- Replaced the client codebook with an original [data dictionary](01_Data/data_dictionary.md).

### New documents
- [Project charter](00_Project_Management/project_charter.md): objectives, scope, stakeholders, assumptions, risks, deliverables.
- [Data audit log](01_Data/audit/data_audit_log.md): 22 checks, regenerated from the data on every run. New findings: implausible altitudes (0 m GPS defaults), inconsistent crop labels, two wordings of one treatment.
- [Analysis report](03_Report/analysis_report.md) covering every objective of the brief.

### New analysis
- Best treatment **per mega-environment**, with Holm-corrected tests.
- **Yield drivers** via permutation importance on held-out fields.
- **Economics**: value-cost ratio and net benefit under three published price scenarios.
- **Decision-support tool** (offline HTML) and decision rule.
- **Field map** by season (static PNG + interactive HTML).
- **CHIRPS rainfall** (`rain_plant_silking`) and **SoilGrids** enrichment scripts with caching, retries and rate limiting.

### Code
- Notebook logic moved into the `src/maize` package. `run_pipeline.py` rebuilds every output; notebooks are shorter and call the package.
- All figures are saved by code (`03_Report/figures/`), and all result tables by the pipeline (`03_Report/tables/`).
- Added `pytest` tests (run on the synthetic sample).
- The prediction model now uses altitude with 0 m errors removed (`alt_clean`) and an ordinal soil-depth code. Previously soil depth was silently dropped because its text values could not be converted to numbers. Model scores barely change (Random Forest MAE 1.285 → 1.289).

### Fixes
- Broken README links (deck file name, repository name, environment file).
- `environment.yml` rewritten: it was UTF-16 encoded, targeted the `base` environment and contained a local Windows path. Added `requirements.txt`.
- `LICENSE` was empty; now contains the MIT licence.
- `.gitignore` pointed to non-existent folders; now protects `01_Data/raw`, `processed` and `external`.
- Consistent organisation name (Evergreen) across README, notebooks, report and deck.
- Renamed `02_data_cleaning_&_integration.ipynb` → `02_data_cleaning_and_integration.ipynb`.

## 1.0.0 · 2026

Initial analysis: data audit, cleaning, EDA, mixed-effects treatment model, Random Forest yield prediction, advisory notebook and client deck.
