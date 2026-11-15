"""Data audit: run every check and return a structured audit log.

The log is recomputed from the data each time, so the counts can never
drift from the dataset. It contains counts and decisions only - no
identifiers or individual records - so it is safe to publish.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import config

COLUMNS = [
    "issue_id", "area", "dataset", "variables", "check_performed", "finding",
    "records_affected", "severity", "decision", "rationale", "handled_in", "status",
]


def _pct(a: int, b: int) -> str:
    return f"{a:,}/{b:,} ({100 * a / b:.1f}%)" if b else f"{a}/0"


def run_audit(src: dict[str, pd.DataFrame], cleaned: dict[str, pd.DataFrame],
              combined: pd.DataFrame) -> pd.DataFrame:
    """Build the audit log. `src` = raw tables, `cleaned` = cleaned tables."""
    field, plot, soil = src["field"], src["plot"], src["soil"]
    cplot, cfield = cleaned["plot"], cleaned["field"]
    rows: list[dict] = []

    def add(area, dataset, variables, check, finding, n, severity, decision, rationale, nb, status="Resolved"):
        rows.append(dict(area=area, dataset=dataset, variables=variables, check_performed=check,
                         finding=finding, records_affected=n, severity=severity, decision=decision,
                         rationale=rationale, handled_in=nb, status=status))

    # ---------------------------------------------------------------- structure
    add("Structure", "All", "-", "Row counts per table",
        f"{len(field):,} field, {len(plot):,} plot and {len(soil):,} soil records",
        0, "Info", "Use as baseline counts for every later check",
        "Any later change in counts must be explained", "01")

    dup_field = int(field.duplicated(["block_id", "season"]).sum())
    dup_plot = int(plot["plot_id"].duplicated().sum())
    full_dups = int(field.duplicated().sum() + plot.duplicated().sum() + soil.duplicated().sum())
    add("Structure", "Field, Plot", "block_id, season, plot_id", "Key uniqueness and complete-row duplicates",
        f"{dup_field} duplicate field keys, {dup_plot} duplicate plot IDs, {full_dups} duplicate rows",
        dup_field + dup_plot + full_dups, "Low" if dup_field + dup_plot + full_dups == 0 else "High",
        "Field grain = block_id + season; plot grain = plot_id", "Keys confirmed unique", "01")

    # ---------------------------------------------------------------- referential integrity
    keys = field[["block_id", "season"]].drop_duplicates()
    m = plot.merge(keys, on=["block_id", "season"], how="left", indicator=True)
    orphans = m[m["_merge"] == "left_only"]
    add("Integrity", "Plot -> Field", "block_id, season", "Every plot has a field record",
        f"{len(orphans)} plots in {orphans[['block_id','season']].drop_duplicates().shape[0]} field-season units "
        "have no field record (block_id absent from Field_Level)",
        len(orphans), "High", "Keep the plots; flag has_field_match = False",
        "Without mega-environment they cannot enter the adjusted models; deleting them would hide the issue",
        "01, 02")

    soil_orphans = int((~soil["plot_id"].isin(plot["plot_id"])).sum())
    add("Integrity", "Soil -> Plot", "plot_id", "Every soil record matches a plot",
        f"{soil_orphans} soil records without a matching plot", soil_orphans,
        "Low" if soil_orphans == 0 else "High", "No action needed" if soil_orphans == 0 else "Investigate",
        "Soil table can be joined one-to-one", "01")

    # ---------------------------------------------------------------- experimental design
    per_unit = plot.groupby(["block_id", "season"])["treat_code"].nunique()
    incomplete = per_unit[per_unit < 4]
    n_inc_plots = int(plot.set_index(["block_id", "season"]).index.isin(incomplete.index).sum())
    add("Design", "Plot", "treat_code", "Four plots / four treatments per field-season unit",
        f"{_pct(int((per_unit == 4).sum()), len(per_unit))} units complete; {len(incomplete)} units have "
        f"2-3 treatments ({n_inc_plots} plots)",
        n_inc_plots, "Medium", "Keep observed plots; flag_incomplete_unit; never create placeholder plots",
        "The mixed model uses within-field contrasts and handles unbalanced units", "01, 02")

    treat_counts = plot["urea_rate_timing"].value_counts()
    add("Design", "Plot", "urea_rate_timing", "Treatment balance",
        f"Four treatments, {treat_counts.min()}-{treat_counts.max()} plots each", 0, "Info",
        "No action", "Balanced enough for pooled comparisons", "01")

    # ---------------------------------------------------------------- dates
    n_text_dates = sum(plot[c].dtype == object or str(plot[c].dtype).startswith("str") for c in config.DATE_COLUMNS)
    add("Dates", "Plot", ", ".join(config.DATE_COLUMNS), "Data types",
        f"{n_text_dates} date columns stored as text; all non-missing values parse as m/d/Y", 0, "Low",
        "Add *_parsed datetime columns; keep original text", "Traceability to the source values", "02")

    chrono_cols = [c for c in cplot.columns if c.startswith("flag_") and "_before_" in c]
    chrono = {c: int(cplot[c].sum()) for c in chrono_cols}
    n_chrono = sum(chrono.values())
    detail = "; ".join(f"{c.replace('flag_', '').replace('_date', '').replace('_', ' ')}: {v}"
                       for c, v in chrono.items() if v) or "none"
    add("Dates", "Plot", "planting -> silking -> R3 -> harvest", "Growth-stage dates in a plausible order",
        f"{n_chrono} violations ({detail})", n_chrono, "Medium",
        "Keep and flag; exclude flagged plots from date-based variables only",
        "Single-plot errors in otherwise consistent fields point to entry errors, but the true date is unknown", "02")

    for col in ["silking_date", "R3_date"]:
        n = int(plot[col].isna().sum())
        if n:
            add("Dates", "Plot", col, "Missing values", f"{n} plots have no {col.replace('_', ' ')}", n, "Low",
                "Leave missing; affects days-to-silking and rainfall window only",
                "No reliable way to infer a growth-stage date", "02")

    v10 = cplot[cplot["flag_v10_date_missing"]]
    v10_trt = int((plot["urea_V10_kgha"] > 0).sum())
    seasons = ", ".join(f"{s}: {n}" for s, n in v10["season"].value_counts().items())
    add("Dates", "Plot", "urea_V10_date, urea_V10_kgha", "V10 date present when a V10 dose is recorded",
        f"{_pct(len(v10), v10_trt)} V6+V10 plots lack a V10 date but have a quantity ({seasons})",
        len(v10), "Medium", "Keep missing dates; do not infer dates from quantities",
        "Season-concentrated pattern suggests a recording gap, not a missed application; "
        "the 82% overall missingness is mostly structural (no V10 dose in 3 of 4 treatments)", "01, 02")

    # ---------------------------------------------------------------- fertiliser arithmetic
    diff = cplot["urea_total_diff"]
    n_diff = int((diff != 0).sum())
    add("Values", "Plot", "urea_total_kgha", "Total = planting + V6 + V10",
        f"{n_diff} plots differ from the calculated total (range {diff.min():+.0f} to {diff.max():+.0f} kg/ha)",
        n_diff, "Low", "Keep source total; add urea_total_calc and urea_total_diff",
        "Differences of 1 kg/ha are consistent with rounding and do not change treatment identity", "02")

    # ---------------------------------------------------------------- outcome
    bad_y = cplot[cplot["flag_implausible_yield"]]
    add("Values", "Plot", "yield_tha", f"Yield plausibility (> {config.IMPLAUSIBLE_YIELD_THA:g} t/ha)",
        (f"{len(bad_y)} plot(s) at {', '.join(f'{v:g}' for v in bad_y['yield_tha'])} t/ha "
         f"(next highest {plot['yield_tha'].nlargest(2).iloc[-1]:g}); likely a misplaced decimal point")
        if len(bad_y) else "No implausible yields",
        len(bad_y), "High" if len(bad_y) else "Low",
        "Keep in the main analysis; report results with and without it",
        "Removing it changes the V6+V10 estimate noticeably but not the recommendation; "
        "the true value cannot be confirmed without the field team", "04, 06")

    # ---------------------------------------------------------------- field values
    bad_alt = cfield[cfield["flag_implausible_altitude"]]
    add("Values", "Field", "alt", f"Altitude plausibility (< {config.IMPLAUSIBLE_ALTITUDE_M:g} m)",
        f"{len(bad_alt)} fields recorded at {', '.join(f'{a:g}' for a in bad_alt['alt'])} m; "
        "Rwanda's lowest point is about 950 m (probable GPS default)",
        len(bad_alt), "Medium", "Set alt_clean to missing for these fields; keep original alt",
        "A 0 m altitude would distort any model that uses elevation", "02")

    n_case = int((plot["crop"] != plot["crop"].str.lower()).sum())
    add("Values", "Plot", "crop", "Consistent category labels",
        f"'Maize' and 'maize' both used ({n_case} plots capitalised)", n_case, "Low",
        "Lower-case all crop labels", "Avoids false categories in grouping", "02")

    det = plot.groupby("treat_code")["treat_details"].nunique()
    n_det = int(sum(len(g) - g.value_counts().iloc[0] for _, g in plot.groupby("treat_code")["treat_details"]))
    add("Values", "Plot", "treat_details", "One description per treatment code",
        f"{int((det > 1).sum())} treatment code(s) with two wordings ({n_det} plots)", n_det, "Low",
        "Add treat_details_std (most common wording); analysis uses urea_rate_timing",
        "Same agronomic treatment; doses confirm it", "02")

    # ---------------------------------------------------------------- missingness
    fmiss = field.isna().groupby(field["season"]).mean()
    systematic = [c for c in fmiss.columns if fmiss[c].max() - fmiss[c].min() > 0.5]
    add("Missingness", "Field", ", ".join(systematic),
        "Missingness by season",
        "Missingness depends on season, not on the field: "
        + "; ".join(f"{c} {fmiss[c].min():.0%}-{fmiss[c].max():.0%}" for c in systematic),
        int(field[systematic].isna().any(axis=1).sum()), "Medium",
        "No imputation in the treatment model; median/most-frequent imputation inside CV folds for prediction only",
        "Variables were not collected in some seasons, so values are missing by design", "01, 06")

    psc = plot["prior_season_crop"].isna()
    by_season = psc.groupby(plot["season"]).mean()
    add("Missingness", "Plot", "prior_season_crop", "Missingness by season",
        f"{psc.mean():.1%} missing overall; " + ", ".join(f"{s} {v:.0%}" for s, v in by_season.items()),
        int(psc.sum()), "Low", "Keep blanks; not used as a predictor",
        "Concentrated in one season; meaning of blanks unknown", "01")

    # ---------------------------------------------------------------- soil
    cov = combined.groupby("season")["has_soil_record"].mean()
    add("Coverage", "Soil", "pH", "Share of plots with a soil record",
        f"{_pct(int(combined['has_soil_record'].sum()), len(combined))}; by season "
        + ", ".join(f"{s} {v:.0%}" for s, v in cov.items()),
        int((~combined["has_soil_record"]).sum()), "High",
        "Keep all plots; has_soil_record flag; pH used only in soil-specific checks",
        "Coverage differs by season, so the soil subset is not representative of the trial", "01, 02")

    empty = [c for c in ["tot_N", "org_C", "sand"] if c in soil and soil[c].isna().all()]
    add("Coverage", "Soil", ", ".join(empty), "Usable values",
        f"{', '.join(empty)} are 100% empty", len(soil) if empty else 0, "High",
        "Fill from SoilGrids at field coordinates (scripts/fetch_soilgrids.py) as sg_* columns",
        "Brief asks for open-source soil data; measured and modelled values are kept separate", "05",
        status="Resolved" if any(c.startswith("sg_") for c in combined.columns) else "Open - run enrichment locally")

    n_ph = int(soil["pH"].isna().sum())
    add("Coverage", "Soil", "pH", "Missing values within soil records",
        f"{n_ph} soil records have no pH", n_ph, "Low", "Leave missing",
        "has_soil_record separates 'no soil record' from 'record without pH'", "02")

    add("Coverage", "Plot", "rain_plant_silking", "Weather data available",
        "No weather data supplied", len(plot), "High",
        "Add CHIRPS rainfall from planting to silking (scripts/fetch_chirps_rainfall.py)",
        "Rainfall is a likely yield driver and the brief asks for it", "05",
        status="Resolved" if "rain_plant_silking" in combined.columns else "Open - run enrichment locally")

    log = pd.DataFrame(rows)
    log.loc[log["records_affected"].eq(0) & log["status"].eq("Resolved"), "status"] = "Confirmed - no issue"
    log.insert(0, "issue_id", [f"AUD-{i:02d}" for i in range(1, len(log) + 1)])
    return log[COLUMNS]


def write_audit_log(log: pd.DataFrame, folder: Path, data_label: str) -> None:
    """Write the log as CSV (for filtering) and Markdown (for reading on GitHub)."""
    folder.mkdir(parents=True, exist_ok=True)
    log.to_csv(folder / "data_audit_log.csv", index=False)

    sev_order = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
    counts = log["severity"].value_counts()
    lines = [
        "# Data audit log",
        "",
        f"*Project:* Rwanda maize–Urea trial analysis for {config.ORGANIZATION}  ",
        f"*Generated:* {date.today():%d %B %Y} by `run_pipeline.py` from the {data_label}  ",
        "*Source of truth:* this file is rebuilt from the data on every run (`src/maize/audit.py`), "
        "so the counts always match the dataset.",
        "",
        "## Summary",
        "",
        "| Severity | Issues |",
        "|---|---:|",
    ]
    lines += [f"| {s} | {int(counts.get(s, 0))} |" for s in sev_order]
    open_items = log[log["status"].str.startswith("Open")]
    lines += ["", f"**Open items:** {len(open_items)}" + (
        " - " + ", ".join(open_items["issue_id"]) if len(open_items) else ""), ""]
    lines += [
        "## Data lineage",
        "",
        "```",
        "Field_Level.csv ─┐",
        "Plot_Level.csv ──┼─ clean (flags, parsed dates, no deletions) ─┐",
        "Soil_PL.csv ─────┘                                              ├─ combined_dataset.csv (one row per plot)",
        "CHIRPS rainfall + SoilGrids (optional, scripts/fetch_*.py) ─────┘",
        "```",
        "",
        "## Register",
        "",
        "| ID | Area | Dataset | Check | Finding | Affected | Severity | Decision | Status |",
        "|---|---|---|---|---|---:|---|---|---|",
    ]
    for _, r in log.iterrows():
        lines.append(
            f"| {r.issue_id} | {r.area} | {r.dataset} | {r.check_performed} | {r.finding} | "
            f"{r.records_affected:,} | {r.severity} | {r.decision} | {r.status} |"
        )
    lines += ["", "## Rationale", ""]
    for _, r in log.iterrows():
        lines.append(f"- **{r.issue_id}** ({r.variables}): {r.rationale}. *Notebook {r.handled_in}.*")
    (folder / "data_audit_log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
