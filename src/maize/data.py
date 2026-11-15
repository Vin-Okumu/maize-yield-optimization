"""Loading, cleaning and integrating the field, plot and soil tables.

Principles (see the data audit log for the evidence behind each step):
* the source tables are never modified in place;
* nothing is deleted or imputed silently - problems are flagged in new columns;
* every join is validated (many plots -> one field) and keeps all plots.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config


# --------------------------------------------------------------------------- loading
def source_dir(mode: str | None = None) -> Path:
    return config.RAW_DIR if (mode or config.data_mode()) == "raw" else config.SAMPLE_DIR


def load_sources(mode: str | None = None) -> dict[str, pd.DataFrame]:
    """Load the three source tables exactly as delivered."""
    folder = source_dir(mode)
    missing = [f for f in config.SOURCE_FILES if not (folder / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing {missing} in {folder}. Put the confidential trial files in 01_Data/raw/ "
            "or run `python scripts/make_synthetic_data.py` to create the synthetic sample."
        )
    return {
        "field": pd.read_csv(folder / "Field_Level.csv"),
        "plot": pd.read_csv(folder / "Plot_Level.csv"),
        "soil": pd.read_csv(folder / "Soil_PL.csv"),
    }


# --------------------------------------------------------------------------- cleaning
def _strip_text(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = out.columns.str.strip()
    for col in out.select_dtypes(include=["object", "string"]).columns:
        out[col] = out[col].str.strip()
    return out


def clean_field(field: pd.DataFrame) -> pd.DataFrame:
    """Standardise text and flag implausible altitudes (kept, not overwritten)."""
    out = _strip_text(field)
    out["flag_implausible_altitude"] = out["alt"] < config.IMPLAUSIBLE_ALTITUDE_M
    out["alt_clean"] = out["alt"].where(~out["flag_implausible_altitude"])
    return out


def clean_plot(plot: pd.DataFrame) -> pd.DataFrame:
    """Parse dates, standardise labels and add data-quality flags."""
    out = _strip_text(plot)

    # Labels: 'Maize' vs 'maize'; two wordings of treatment D's description
    out["crop"] = out["crop"].str.lower()
    out["treat_details_std"] = out.groupby("treat_code")["treat_details"].transform(
        lambda s: s.mode().iloc[0]
    )

    # Dates: keep the original text, add parsed columns
    for col in config.DATE_COLUMNS:
        out[f"{col}_parsed"] = pd.to_datetime(out[col], format="%m/%d/%Y", errors="coerce")
        new_failures = out[col].notna() & out[f"{col}_parsed"].isna()
        if new_failures.any():
            raise ValueError(f"{new_failures.sum()} unparseable values in {col}")

    # Chronology checks (missing dates are not counted as violations)
    pairs = [
        ("planting_date", "germ_count_date"), ("planting_date", "urea_V6_date"),
        ("planting_date", "silking_date"), ("silking_date", "R3_date"),
        ("R3_date", "harvest_date"), ("planting_date", "harvest_date"),
    ]
    for early, late in pairs:
        out[f"flag_{late}_before_{early}"] = (
            out[f"{late}_parsed"] < out[f"{early}_parsed"]
        ).fillna(False)

    # Fertiliser arithmetic: keep source total, add calculated total and difference
    out["urea_total_calc"] = out[["urea_planting_kgha", "urea_V6_kgha", "urea_V10_kgha"]].sum(axis=1)
    out["urea_total_diff"] = out["urea_total_kgha"] - out["urea_total_calc"]

    # V10 date missing although a V10 quantity was recorded
    out["flag_v10_date_missing"] = out["urea_V10_kgha"].gt(0) & out["urea_V10_date"].isna()

    # Yield entry errors (kept; excluded only in sensitivity checks)
    out["flag_implausible_yield"] = out["yield_tha"] > config.IMPLAUSIBLE_YIELD_THA

    # Derived timing variables
    out["days_planting_to_silking"] = (out["silking_date_parsed"] - out["planting_date_parsed"]).dt.days
    out["days_silking_to_r3"] = (out["R3_date_parsed"] - out["silking_date_parsed"]).dt.days
    out["planting_doy_in_season"] = (
        out["planting_date_parsed"]
        - out.groupby("season")["planting_date_parsed"].transform("min")
    ).dt.days
    return out


def clean_soil(soil: pd.DataFrame) -> pd.DataFrame:
    out = _strip_text(soil)
    # tot_N, org_C and sand arrive completely empty; keep them so the enrichment can fill them
    return out


# --------------------------------------------------------------------------- integration
def integrate(field: pd.DataFrame, plot: pd.DataFrame, soil: pd.DataFrame,
              external: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Combine plot, field and soil data into one analysis table (one row per plot)."""
    n = len(plot)
    combined = plot.merge(field, on=["block_id", "season"], how="left",
                          validate="many_to_one", indicator="_field_merge")
    combined["has_field_match"] = combined.pop("_field_merge").eq("both")

    combined = combined.merge(soil, on="plot_id", how="left", validate="one_to_one",
                              indicator="_soil_merge")
    combined["has_soil_record"] = combined.pop("_soil_merge").eq("both")

    combined["field_season_id"] = combined["block_id"] + "_" + combined["season"]
    plots_per_unit = combined.groupby("field_season_id")["plot_id"].transform("size")
    combined["flag_incomplete_unit"] = plots_per_unit < 4

    for name, ext in (external or {}).items():
        keys = [k for k in ("plot_id", "block_id", "season") if k in ext.columns]
        keys = ["plot_id"] if "plot_id" in keys else keys
        ext = ext.drop_duplicates(keys)
        overlap = [c for c in ext.columns if c in combined.columns and c not in keys]
        combined = combined.drop(columns=overlap).merge(ext, on=keys, how="left", validate="many_to_one")

    assert len(combined) == n, "integration changed the number of plots"
    assert combined["plot_id"].is_unique
    return combined


def load_external() -> dict[str, pd.DataFrame]:
    """Pick up enrichment files created by scripts/fetch_*.py, if they exist."""
    out = {}
    rain = config.EXTERNAL_DIR / "chirps_rain_plant_silking.csv"
    soil = config.EXTERNAL_DIR / "soilgrids_soil.csv"
    if rain.exists():
        out["rainfall"] = pd.read_csv(rain)[["plot_id", "rain_plant_silking"]]
    if soil.exists():
        sg = pd.read_csv(soil)
        out["soilgrids"] = sg[["block_id", "season"] + [c for c in sg.columns if c.startswith("sg_")]]
    return out


def build_combined(mode: str | None = None) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Full preparation: load -> clean -> integrate. Returns (cleaned tables, combined)."""
    src = load_sources(mode)
    cleaned = {
        "field": clean_field(src["field"]),
        "plot": clean_plot(src["plot"]),
        "soil": clean_soil(src["soil"]),
    }
    combined = integrate(cleaned["field"], cleaned["plot"], cleaned["soil"], load_external())
    return cleaned, combined


def analysis_frame(combined: pd.DataFrame, drop_implausible: bool = False) -> pd.DataFrame:
    """Plots usable for treatment-effect models: field context present, treatment ordered."""
    df = combined[combined["has_field_match"] & combined["meg_env"].notna()].copy()
    if drop_implausible:
        df = df[~df["flag_implausible_yield"]]
    df["urea_rate_timing"] = pd.Categorical(df["urea_rate_timing"], categories=config.TREATMENTS)
    return df.reset_index(drop=True)


def public_columns(combined: pd.DataFrame) -> list[str]:
    """Columns of the combined dataset, minus helper columns."""
    return [c for c in combined.columns if not c.startswith("_")]


def sanity_summary(combined: pd.DataFrame) -> pd.DataFrame:
    """Final structural checks on the combined dataset."""
    checks = {
        "Rows (plots)": len(combined),
        "Columns": combined.shape[1],
        "Duplicate plot_id": int(combined["plot_id"].duplicated().sum()),
        "Missing yield": int(combined["yield_tha"].isna().sum()),
        "Missing treatment": int(combined["urea_rate_timing"].isna().sum()),
        "Plots without field record": int((~combined["has_field_match"]).sum()),
        "Plots with soil record": int(combined["has_soil_record"].sum()),
        "Plots in incomplete units": int(combined["flag_incomplete_unit"].sum()),
        "Implausible yields flagged": int(combined["flag_implausible_yield"].sum()),
    }
    return pd.DataFrame({"check": list(checks.keys()), "result": list(checks.values())})
