# Data audit log

*Project:* Rwanda maize–Urea trial analysis for Evergreen  
*Generated:* 15 November 2026 by `run_pipeline.py` from the confidential trial data  
*Source of truth:* this file is rebuilt from the data on every run (`src/maize/audit.py`), so the counts always match the dataset.

## Summary

| Severity | Issues |
|---|---:|
| High | 5 |
| Medium | 5 |
| Low | 10 |
| Info | 2 |

**Open items:** 2 - AUD-20, AUD-22

## Data lineage

```
Field_Level.csv ─┐
Plot_Level.csv ──┼─ clean (flags, parsed dates, no deletions) ─┐
Soil_PL.csv ─────┘                                              ├─ combined_dataset.csv (one row per plot)
CHIRPS rainfall + SoilGrids (optional, scripts/fetch_*.py) ─────┘
```

## Register

| ID | Area | Dataset | Check | Finding | Affected | Severity | Decision | Status |
|---|---|---|---|---|---:|---|---|---|
| AUD-01 | Structure | All | Row counts per table | 399 field, 1,598 plot and 736 soil records | 0 | Info | Use as baseline counts for every later check | Confirmed - no issue |
| AUD-02 | Structure | Field, Plot | Key uniqueness and complete-row duplicates | 0 duplicate field keys, 0 duplicate plot IDs, 0 duplicate rows | 0 | Low | Field grain = block_id + season; plot grain = plot_id | Confirmed - no issue |
| AUD-03 | Integrity | Plot -> Field | Every plot has a field record | 5 plots in 2 field-season units have no field record (block_id absent from Field_Level) | 5 | High | Keep the plots; flag has_field_match = False | Resolved |
| AUD-04 | Integrity | Soil -> Plot | Every soil record matches a plot | 0 soil records without a matching plot | 0 | Low | No action needed | Confirmed - no issue |
| AUD-05 | Design | Plot | Four plots / four treatments per field-season unit | 396/401 (98.8%) units complete; 5 units have 2-3 treatments (14 plots) | 14 | Medium | Keep observed plots; flag_incomplete_unit; never create placeholder plots | Resolved |
| AUD-06 | Design | Plot | Treatment balance | Four treatments, 397-401 plots each | 0 | Info | No action | Confirmed - no issue |
| AUD-07 | Dates | Plot | Data types | 7 date columns stored as text; all non-missing values parse as m/d/Y | 0 | Low | Add *_parsed datetime columns; keep original text | Confirmed - no issue |
| AUD-08 | Dates | Plot | Growth-stage dates in a plausible order | 3 violations (R3 before silking: 3) | 3 | Medium | Keep and flag; exclude flagged plots from date-based variables only | Resolved |
| AUD-09 | Dates | Plot | Missing values | 9 plots have no silking date | 9 | Low | Leave missing; affects days-to-silking and rainfall window only | Resolved |
| AUD-10 | Dates | Plot | Missing values | 6 plots have no R3 date | 6 | Low | Leave missing; affects days-to-silking and rainfall window only | Resolved |
| AUD-11 | Dates | Plot | V10 date present when a V10 dose is recorded | 115/401 (28.7%) V6+V10 plots lack a V10 date but have a quantity (22A: 115) | 115 | Medium | Keep missing dates; do not infer dates from quantities | Resolved |
| AUD-12 | Values | Plot | Total = planting + V6 + V10 | 162 plots differ from the calculated total (range -1 to +1 kg/ha) | 162 | Low | Keep source total; add urea_total_calc and urea_total_diff | Resolved |
| AUD-13 | Values | Plot | Yield plausibility (> 20 t/ha) | 1 plot(s) at 50.1 t/ha (next highest 10.9); likely a misplaced decimal point | 1 | High | Keep in the main analysis; report results with and without it | Resolved |
| AUD-14 | Values | Field | Altitude plausibility (< 900 m) | 3 fields recorded at 0.26, 0.26, 0 m; Rwanda's lowest point is about 950 m (probable GPS default) | 3 | Medium | Set alt_clean to missing for these fields; keep original alt | Resolved |
| AUD-15 | Values | Plot | Consistent category labels | 'Maize' and 'maize' both used (1089 plots capitalised) | 1,089 | Low | Lower-case all crop labels | Resolved |
| AUD-16 | Values | Plot | One description per treatment code | 1 treatment code(s) with two wordings (2 plots) | 2 | Low | Add treat_details_std (most common wording); analysis uses urea_rate_timing | Resolved |
| AUD-17 | Missingness | Field | Missingness by season | Missingness depends on season, not on the field: slope_pos 0%-100%; rockness 0%-100%; soil_depth 0%-100%; trialfield_home_min 7%-100% | 281 | Medium | No imputation in the treatment model; median/most-frequent imputation inside CV folds for prediction only | Resolved |
| AUD-18 | Missingness | Plot | Missingness by season | 28.8% missing overall; 21A 0%, 22A 60%, 22B 0% | 460 | Low | Keep blanks; not used as a predictor | Resolved |
| AUD-19 | Coverage | Soil | Share of plots with a soil record | 736/1,598 (46.1%); by season 21A 25%, 22A 69%, 22B 24% | 862 | High | Keep all plots; has_soil_record flag; pH used only in soil-specific checks | Resolved |
| AUD-20 | Coverage | Soil | Usable values | tot_N, org_C, sand are 100% empty | 736 | High | Fill from SoilGrids at field coordinates (scripts/fetch_soilgrids.py) as sg_* columns | Open - run enrichment locally |
| AUD-21 | Coverage | Soil | Missing values within soil records | 2 soil records have no pH | 2 | Low | Leave missing | Resolved |
| AUD-22 | Coverage | Plot | Weather data available | No weather data supplied | 1,598 | High | Add CHIRPS rainfall from planting to silking (scripts/fetch_chirps_rainfall.py) | Open - run enrichment locally |

## Rationale

- **AUD-01** (-): Any later change in counts must be explained. *Notebook 01.*
- **AUD-02** (block_id, season, plot_id): Keys confirmed unique. *Notebook 01.*
- **AUD-03** (block_id, season): Without mega-environment they cannot enter the adjusted models; deleting them would hide the issue. *Notebook 01, 02.*
- **AUD-04** (plot_id): Soil table can be joined one-to-one. *Notebook 01.*
- **AUD-05** (treat_code): The mixed model uses within-field contrasts and handles unbalanced units. *Notebook 01, 02.*
- **AUD-06** (urea_rate_timing): Balanced enough for pooled comparisons. *Notebook 01.*
- **AUD-07** (planting_date, germ_count_date, urea_V6_date, urea_V10_date, silking_date, R3_date, harvest_date): Traceability to the source values. *Notebook 02.*
- **AUD-08** (planting -> silking -> R3 -> harvest): Single-plot errors in otherwise consistent fields point to entry errors, but the true date is unknown. *Notebook 02.*
- **AUD-09** (silking_date): No reliable way to infer a growth-stage date. *Notebook 02.*
- **AUD-10** (R3_date): No reliable way to infer a growth-stage date. *Notebook 02.*
- **AUD-11** (urea_V10_date, urea_V10_kgha): Season-concentrated pattern suggests a recording gap, not a missed application; the 82% overall missingness is mostly structural (no V10 dose in 3 of 4 treatments). *Notebook 01, 02.*
- **AUD-12** (urea_total_kgha): Differences of 1 kg/ha are consistent with rounding and do not change treatment identity. *Notebook 02.*
- **AUD-13** (yield_tha): Removing it changes the V6+V10 estimate noticeably but not the recommendation; the true value cannot be confirmed without the field team. *Notebook 04, 06.*
- **AUD-14** (alt): A 0 m altitude would distort any model that uses elevation. *Notebook 02.*
- **AUD-15** (crop): Avoids false categories in grouping. *Notebook 02.*
- **AUD-16** (treat_details): Same agronomic treatment; doses confirm it. *Notebook 02.*
- **AUD-17** (slope_pos, rockness, soil_depth, trialfield_home_min): Variables were not collected in some seasons, so values are missing by design. *Notebook 01, 06.*
- **AUD-18** (prior_season_crop): Concentrated in one season; meaning of blanks unknown. *Notebook 01.*
- **AUD-19** (pH): Coverage differs by season, so the soil subset is not representative of the trial. *Notebook 01, 02.*
- **AUD-20** (tot_N, org_C, sand): Brief asks for open-source soil data; measured and modelled values are kept separate. *Notebook 05.*
- **AUD-21** (pH): has_soil_record separates 'no soil record' from 'record without pH'. *Notebook 02.*
- **AUD-22** (rain_plant_silking): Rainfall is a likely yield driver and the brief asks for it. *Notebook 05.*
