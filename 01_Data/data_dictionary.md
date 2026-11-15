# Data dictionary

## Field level (`Field_Level.csv`): one row per field per season

| Column | Description | Type / values |
|---|---|---|
| `block_id` | Field identifier | text (UUID) |
| `season` | Rwandan growing season: A = Sept–Feb, B = Feb–July | 21A, 22A, 22B |
| `district`, `cell` | Administrative location (district > cell) | text |
| `agzone` | Agro-ecological zone (several per mega-environment) | text |
| `meg_env` | Mega-environment: the grouping used to target advice | Highlands, Low-Mid-Dry, Low-Mid-Wet, Transitional |
| `lat`, `long` | Field coordinates (decimal degrees, WGS84). **Sensitive** | number |
| `alt` | Elevation (m) | number |
| `landscape_pos` | Landform the field sits on | Hills, Valley, Radical_terraces |
| `slope_pos` | Position on the hillslope | Summit, Shoulder, Backslope, Footslope, Flat, Valley |
| `fert_rank` | Farmer's own rating of field fertility | less_than_medium, medium, high |
| `soil_color` | Visual soil colour | red_less, red_more, black_less, black_more, brown, grey, yellowish |
| `rockness` | Visible stones and pebbles | no_rocks, less_rocky, much_small_sized_rocks |
| `soil_depth` | Visual soil depth | shallow, deep |
| `slope` | Field slope (%) | integer |
| `trial_follower_gender` | Gender of the farmer running the trial. **Sensitive** | Male, Female |
| `trialfield_home_min` | Walking time from home to field (minutes) | integer |
| `cult_land` | Total land the farmer cultivates (unit not stated in the source; values suggest ares) | number |

## Plot level (`Plot_Level.csv`): one row per plot (four plots per field)

| Column | Description | Type / values |
|---|---|---|
| `plot_id` | Plot identifier (`block_id`-`season`-`treat_code`) | text |
| `treat_code` | Treatment code | A, B, C, D |
| `treat_details` | Full treatment description including DAP | text |
| `urea_rate_timing` | Urea rate and timing (the treatment used in analysis) | see below |
| `crop`, `prior_season_crop` | Crop this season; crop(s) grown the previous season | text |
| `planting_date`, `germ_count_date`, `silking_date`, `R3_date`, `harvest_date` | Growth-stage dates (R3 = milk stage) | m/d/yyyy text |
| `compost_tha`, `compost_quality` | Compost applied (t/ha) and its visual quality | number; text |
| `seed_variety`, `seeds_kgha` | Maize variety and seed rate (kg/ha) | text; number |
| `germination_rate` | Share of seeds that emerged (%) | number |
| `dap_kgha` | DAP applied at planting (kg/ha) | number |
| `urea_planting_kgha`, `urea_V6_kgha`, `urea_V10_kgha` | Urea applied at planting / V6 / V10 (kg/ha) | number |
| `urea_V6_date`, `urea_V10_date` | Urea application dates | m/d/yyyy text |
| `urea_total_kgha`, `N_kgha` | Total Urea and total nitrogen applied (kg/ha) | number |
| `yield_tha` | **Grain yield (t/ha): main outcome** | number |

| `urea_rate_timing` | Code | Meaning |
|---|---|---|
| `Urea 0.5Kg/Are(V6)` | A | 50 kg/ha, all at V6 (baseline, current practice) |
| `Urea1kg/Are(Planting+V6)` | B | 100 kg/ha, half at planting, half at V6 |
| `Urea 1kg/Are(V6 + V10)` | C | 100 kg/ha, half at V6, half at V10 |
| `Urea 1kg/Are(V6)` | D | 100 kg/ha, all at V6 |

V6 and V10 are the vegetative stages with six and ten visible leaf collars. 1 kg/are = 100 kg/ha.

## Soil (`Soil_PL.csv`): one row per sampled plot

| Column | Description | Note |
|---|---|---|
| `plot_id` | Plot identifier | 736 of 1,598 plots |
| `pH` | Soil pH (measured) | 2 missing |
| `tot_N`, `org_C`, `sand` | Total N (%), organic carbon (%), sand (%) | Empty in source; filled from SoilGrids in `external/Soil_PL_filled.csv` |

## Columns added by the pipeline (`combined_dataset.csv`)

| Column | Meaning |
|---|---|
| `*_parsed` | Date columns converted to dates (originals kept) |
| `flag_<late>_before_<early>` | Growth-stage dates out of order |
| `flag_v10_date_missing` | V10 dose recorded but no V10 date |
| `flag_implausible_yield` | Yield above 20 t/ha (probable entry error) |
| `flag_implausible_altitude`, `alt_clean` | Altitude below 900 m flagged; `alt_clean` sets those to missing |
| `flag_incomplete_unit` | Field-season with fewer than four plots |
| `has_field_match`, `has_soil_record` | Whether the plot joined to a field / soil record |
| `field_season_id` | `block_id` + season: grouping for the mixed models |
| `treat_details_std` | One standard description per treatment code |
| `urea_total_calc`, `urea_total_diff` | Recomputed Urea total and difference from the source total |
| `days_planting_to_silking`, `days_silking_to_r3`, `planting_doy_in_season` | Derived timing variables |
| `rain_plant_silking` | CHIRPS rainfall from planting to silking (mm), after running `scripts/fetch_chirps_rainfall.py` |
| `sg_nitrogen_g_kg`, `sg_soc_g_kg`, `sg_sand_pct`, `sg_clay_pct`, `sg_ph_h2o` | SoilGrids 0–30 cm estimates, after running `scripts/fetch_soilgrids.py` |
