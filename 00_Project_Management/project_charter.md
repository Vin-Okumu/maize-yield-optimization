# Project charter

**Project:** Urea rate and timing for maize in Rwanda: trial analysis and extension advisory  
**Client:** Evergreen, Global Research & Development (R&D)  
**Analyst:** Vincent Okumu  
**Version:** 2.0 · November 2026  
**Status:** Analysis complete; external data enrichment pending (see [Open items](#10-open-items))

---

## 1. Background

Evergreen supports smallholder maize farmers in Rwanda through input supply and extension advice. Its current Urea recommendation is 50 kg/ha applied at the V6 stage (six visible leaf collars). Over three seasons (21A, 22A and 22B), Evergreen's R&D team ran an on-farm trial to test whether a higher rate or a different application timing raises yield.

Each participating farmer split one maize field into four plots, and each plot received one of four Urea treatments. Data was collected at three levels:

| Level | Content | Records |
|---|---|---:|
| Field | Location, mega-environment, landscape, soil observations, farmer information | 399 field-seasons |
| Plot | Treatment, inputs, growth-stage dates, grain yield | 1,598 plots |
| Soil | Plot soil measurements (pH only; N, organic C and sand empty) | 736 plots |

## 2. Problem statement

Extension officers give one Urea recommendation across very different growing environments. Evergreen needs evidence on:

* which rate and timing gives the most maize,
* whether that answer changes by environment, and
* whether the extra fertiliser is worth its cost to farmers.

Without this evidence, farmers risk either under-fertilising or paying for Urea that doesn't pay back.

## 3. Objectives

| # | Objective | Success measure |
|---|---|---|
| 1 | Identify the highest-yielding Urea rate–timing combination in each mega-environment, and test whether the differences are statistically significant | Adjusted treatment means with 95% CIs; multiple-comparison-corrected tests; per-environment results |
| 2a | Identify the most important drivers of maize yield, including variables added from open data | Ranked driver list measured on held-out fields |
| 2b | Recommend where each combination should be used, and give Evergreen a decision-support tool | Decision rule + interactive tool usable by non-analysts |
| 3 | Build a yield-prediction model and report its quality honestly | Grouped cross-validation (whole fields held out); MAE, RMSE and R² against a baseline |
| 4 | Map the trial fields, distinguishing seasons | Static and interactive maps |
| + | Test whether the recommendation is profitable *(added scope)* | Value-cost ratio under realistic price scenarios |

### Treatments

| Code | Treatment (source label) | Urea rate | Timing |
|---|---|---:|---|
| A | `Urea 0.5Kg/Are(V6)` (current practice, baseline) | 50 kg/ha | All at V6 |
| B | `Urea1kg/Are(Planting+V6)` | 100 kg/ha | Half at planting, half at V6 |
| C | `Urea 1kg/Are(V6 + V10)` | 100 kg/ha | Half at V6, half at V10 |
| D | `Urea 1kg/Are(V6)` | 100 kg/ha | All at V6 |

All plots also received DAP at 100 kg/ha at planting.

## 4. Scope

**In scope**

* Audit, cleaning and integration of the three source tables
* Enrichment with CHIRPS rainfall (planting to silking) and SoilGrids soil properties
* Treatment-effect analysis (mixed-effects models), per-environment and per-season checks
* Yield-driver analysis and yield prediction
* Partial-budget economics (value-cost ratio)
* Decision-support tool, field maps, analysis report and summary deck

**Out of scope**

* Collecting new field data or re-measuring yields
* Labour, transport and risk-preference costs (noted as a limitation of the economics)
* Recommendations for crops other than maize or fertilisers other than Urea
* Deploying the tool on Evergreen's systems

## 5. Stakeholders

| Stakeholder | Interest | Role (RACI) |
|---|---|---|
| Evergreen R&D lead | Sound evidence for the recommendation | **A**ccountable, approves findings |
| Data analyst (Vincent Okumu) | Delivers the analysis | **R**esponsible |
| Field / M&E team | Data collection protocols, explaining anomalies | **C**onsulted (data queries in the audit log) |
| Agronomists | Agronomic plausibility of results | **C**onsulted |
| Extension officers | A clear rule they can apply | **I**nformed (decision tool, deck) |
| Farmers | Higher, profitable yields | Ultimate beneficiaries |

## 6. Deliverables

| # | Deliverable | Location in repository |
|---|---|---|
| 1 | Final combined dataset (one row per plot) | `01_Data/processed/combined_dataset.csv` *(confidential, generated locally)* |
| 2 | Analysis report | [`03_Report/analysis_report.md`](../03_Report/analysis_report.md) |
| 3 | Analysis scripts | [`src/maize/`](../src/maize), [`run_pipeline.py`](../run_pipeline.py), [`02_Notebooks/`](../02_Notebooks) |
| 4 | Map of trial fields by season | [`03_Report/figures/trial_fields_map.png`](../03_Report/figures/trial_fields_map.png), [`03_Report/maps/trial_fields_map.html`](../03_Report/maps/trial_fields_map.html) |
| 5 | Soil file filled from SoilGrids | `01_Data/external/Soil_PL_filled.csv` *(generated by [`scripts/fetch_soilgrids.py`](../scripts/fetch_soilgrids.py))* |
| + | Data audit log | [`01_Data/audit/data_audit_log.md`](../01_Data/audit/data_audit_log.md) |
| + | Decision-support tool | [`03_Report/decision_tool/index.html`](../03_Report/decision_tool/index.html) |
| + | Summary deck | [`03_Report/reports/Maize_Yield_Client_Deck.pptx`](../03_Report/reports/Maize_Yield_Client_Deck.pptx) |

## 7. Approach and milestones

| Phase | Milestone | Output | Notebook |
|---|---|---|---|
| 1. Audit | Every data-quality issue found, counted and logged | Audit log | 01 |
| 2. Prepare | Clean, flagged, integrated dataset; nothing deleted silently | Combined dataset | 02 |
| 3. Explore | Patterns by treatment, season, environment; field map | EDA figures, maps | 03 |
| 4. Estimate | Treatment effects with mixed models; interactions; sensitivity | Effect tables | 04 |
| 5. Enrich | Rainfall and soil added from open data | External data files | 05 |
| 6. Predict | Yield model validated on unseen fields; driver ranking | Model comparison, drivers | 06 |
| 7. Advise | Economics, decision rule and tool, report and deck | Report, tool, deck | 07 |

## 8. Assumptions

1. **Treatments were applied as recorded.** Where the V10 date is missing but a V10 quantity is recorded (115 plots, all in 22A), the application is assumed to have happened.
2. **The 50.1 t/ha yield is an entry error** (probably 5.01). It is kept in the main analysis and every key result is also reported without it.
3. **Mega-environment is the right unit for targeting advice.** It is the stratification Evergreen used when designing the trial.
4. **Missing field variables are missing by design.** Several were not collected in later seasons, so they are not imputed in the treatment models.
5. **Prices.** The economics uses trial-period (2022) and current (2026) Rwandan prices from published sources, with subsidised and unsubsidised Urea. The decision tool lets users enter their own prices.
6. **SoilGrids and CHIRPS are adequate proxies.** They are modelled or satellite-derived at 250 m and 5 km resolution, so they describe the area around a field, not the plot itself.

## 9. Constraints and risks

| Risk / constraint | Impact | Mitigation |
|---|---|---|
| Trial data is confidential | Data cannot be published or uploaded to external services | Data stays in `01_Data/raw/` (git-ignored); repository ships a synthetic sample; published maps round coordinates to ~1 km |
| Soil measured on only 46% of plots, unevenly by season | Soil-based conclusions could be biased | Soil pH used only in soil-specific checks; SoilGrids used for full coverage |
| One implausible yield (50.1 t/ha) | Inflates variance; shifts the V6+V10 estimate | Sensitivity analysis with and without it |
| SoilGrids / CHIRPS services unavailable or slow | Enrichment delayed | Cached, resumable scripts with alternative access routes |
| Treatment × environment effects are hard to detect with ~65–140 fields per environment | Small local differences could be missed | Report per-environment estimates with CIs alongside the pooled result |
| Yield-only advice may not be profitable | Farmers lose money | Value-cost ratio with a 2.0 adoption threshold |

## 10. Open items

| Item | Owner | Next step |
|---|---|---|
| Run CHIRPS rainfall enrichment | Analyst | `python scripts/fetch_chirps_rainfall.py` on a machine with internet access, then re-run the pipeline |
| Run SoilGrids enrichment | Analyst | `python scripts/fetch_soilgrids.py` (about 5 requests per minute; cached) |
| Confirm the 50.1 t/ha record and the 3 plots where R3 is recorded before silking | Field / M&E team | Check paper forms or enumerator notes |
| Confirm whether V10 Urea was applied in 22A | Field / M&E team | Check distribution records |

## 11. Approval

| Role | Name | Date |
|---|---|---|
| R&D lead, Evergreen | | |
| Analyst | Vincent Okumu | |

---

<sub>**Use of AI tools.** Claude (Anthropic) was used to review the repository, refactor the notebook code into the `src/maize` pipeline, write tests and draft documentation. All analytical choices and results were checked by the analyst.</sub>
