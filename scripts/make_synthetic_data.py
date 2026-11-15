"""Generate a synthetic version of the Evergreen maize-Urea trial data.

The real trial data is confidential and is not stored in this repository.
This script builds three files with the same columns, value formats and
data-quality problems as the real data, so that every notebook and the
pipeline can run end to end:

    01_Data/sample/Field_Level.csv
    01_Data/sample/Plot_Level.csv
    01_Data/sample/Soil_PL.csv

Nothing in these files comes from a real farmer or field:
* identifiers are freshly generated UUIDs,
* coordinates are random points around district centres,
* yields are simulated from a simple mixed model whose parameters are
  round numbers of the same order as the published results,
* the known data-quality issues (unmatched fields, incomplete
  units, a 10x yield entry error, missing V10 dates in 22A, etc.) are
  injected on purpose so the audit notebook has something to find.

Results computed on this sample will NOT match the published results.

Usage:
    python scripts/make_synthetic_data.py [--seed 2026]
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "01_Data" / "sample"

# Mega-environment -> list of (district, agro-ecological zone, approx centre lat, lon, median altitude)
GEOGRAPHY = {
    "Highlands": [
        ("Burera", "Buberuka highlands", -1.48, 29.80, 2050),
        ("Karongi", "Congo Nile", -2.13, 29.48, 2060),
        ("Nyabihu", "Volcanic cones", -1.60, 29.46, 2450),
        ("Nyamagabe", "Congo Nile", -2.50, 29.50, 2100),
        ("Rubavu", "Volcanic cones", -1.55, 29.44, 2300),
        ("Rutsiro", "Congo Nile", -2.06, 29.55, 2110),
    ],
    "Low-Mid-Dry": [
        ("Gisagara", "Mayaga-Bugesera", -2.47, 29.91, 1400),
        ("Kayonza", "Eastern Ridges", -1.83, 30.47, 1480),
        ("Ngoma", "Eastern Ridges", -2.07, 30.50, 1465),
        ("Rwamagana", "Eastern Ridges", -2.02, 30.34, 1600),
    ],
    "Low-Mid-Wet": [
        ("Huye", "Central Plateau", -2.45, 29.76, 1700),
        ("Karongi", "Lake Kivu", -2.13, 29.32, 1620),
        ("Nyamasheke", "Lake Kivu", -2.35, 29.11, 1570),
        ("Nyanza", "Central Plateau", -2.32, 29.85, 1470),
    ],
    "Transitional": [
        ("Gakenke", "Buberuka highlands", -1.62, 29.65, 1800),
        ("Huye", "Central Plateau", -2.44, 29.76, 1730),
        ("Karongi", "Lake Kivu", -2.14, 29.32, 1715),
        ("Nyamasheke", "Congo Nile", -2.42, 29.20, 1700),
    ],
}

# Fields per season x mega-environment (similar scale to the real trial)
DESIGN = {
    "21A": {"Highlands": 35, "Low-Mid-Dry": 45, "Low-Mid-Wet": 31, "Transitional": 16},
    "22A": {"Highlands": 72, "Low-Mid-Dry": 55, "Low-Mid-Wet": 36, "Transitional": 30},
    "22B": {"Highlands": 35, "Low-Mid-Dry": 15, "Low-Mid-Wet": 10, "Transitional": 19},
}

SEASON_PLANTING = {"21A": "2020-09-20", "22A": "2021-09-20", "22B": "2022-02-05"}

TREATMENTS = {
    "A": dict(label="Urea 0.5Kg/Are(V6)", details="DAP 1Kg/Are + Urea 0.5Kg/Are at V6",
              planting=0, v6=50, v10=0, n=41, effect=0.00),
    "B": dict(label="Urea1kg/Are(Planting+V6)",
              details="DAP 1Kg/Are + Urea 0.5Kg/Are at Planting and Urea 0.5Kg/Are at V6",
              planting=50, v6=50, v10=0, n=64, effect=0.15),
    "C": dict(label="Urea 1kg/Are(V6 + V10)",
              details="DAP 1Kg/Are + Urea 0.5Kg/Are at V6 + Urea 0.5Kg/Are at V10",
              planting=0, v6=50, v10=50, n=64, effect=0.40),
    "D": dict(label="Urea 1kg/Are(V6)", details="DAP 1Kg/Are at planting+ Urea 1Kg/Are at V6",
              planting=0, v6=100, v10=0, n=64, effect=0.55),
}

ME_MEAN = {"Highlands": 4.3, "Low-Mid-Dry": 5.6, "Low-Mid-Wet": 4.1, "Transitional": 4.3}
SEASON_SHIFT = {"21A": 0.0, "22A": 0.6, "22B": 0.3}

PRIOR_CROPS = ["Beans", "sweet_potato", "Beans maize", "irish_potato", "sorghum", "maize",
               "cassava", "fallow", "wheat", "Soya_(soybean)"]


def fmt_date(d: pd.Timestamp | None) -> str | float:
    """Format like the source system: m/d/yyyy without leading zeros."""
    if d is None or pd.isna(d):
        return np.nan
    return f"{d.month}/{d.day}/{d.year}"


def make_fields(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for season, per_me in DESIGN.items():
        for me, n_fields in per_me.items():
            districts = GEOGRAPHY[me]
            for _ in range(n_fields):
                district, agzone, lat0, lon0, alt0 = districts[rng.integers(len(districts))]
                later = season != "21A"  # several variables were not collected after 21A
                rows.append({
                    "block_id": str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)))),
                    "season": season,
                    "district": district,
                    "cell": f"{district}_site_{rng.integers(1, 3)}",
                    "agzone": agzone,
                    "meg_env": me,
                    "lat": round(lat0 + rng.normal(0, 0.05), 6),
                    "long": round(lon0 + rng.normal(0, 0.05), 6),
                    "alt": round(alt0 + rng.normal(0, 60), 2),
                    "landscape_pos": rng.choice(["Hills", "Valley", "Radical_terraces"], p=[0.85, 0.11, 0.04]),
                    "slope_pos": np.nan if (season == "22B" or (later and rng.random() < 0.4))
                    else rng.choice(["Backslope", "Flat", "Shoulder", "Footslope", "Valley", "Summit"],
                                    p=[0.65, 0.12, 0.11, 0.05, 0.04, 0.03]),
                    "fert_rank": rng.choice(["medium", "high", "less_than_medium"], p=[0.88, 0.10, 0.02]),
                    "soil_color": rng.choice(["red_less", "black_less", "red_more", "brown", "grey", "black_more", "yellowish"],
                                             p=[0.53, 0.30, 0.06, 0.05, 0.03, 0.015, 0.015]),
                    "rockness": np.nan if (season == "22B" or (later and rng.random() < 0.4))
                    else rng.choice(["no_rocks", "less_rocky", "much_small_sized_rocks"], p=[0.77, 0.21, 0.02]),
                    "soil_depth": np.nan if (season == "22B" or (later and rng.random() < 0.4))
                    else rng.choice(["deep", "shallow"], p=[0.6, 0.4]),
                    "slope": int(np.clip(rng.normal(10.5, 7), 0, 32)),
                    "trial_follower_gender": np.nan if (season == "21A" and rng.random() < 0.07)
                    else rng.choice(["Male", "Female"], p=[0.54, 0.46]),
                    "trialfield_home_min": np.nan if (later or rng.random() < 0.07)
                    else int(np.clip(rng.lognormal(1.8, 1.0), 1, 90)),
                    "cult_land": np.nan if (season == "21A" and rng.random() < 0.07)
                    else round(float(np.clip(rng.lognormal(3.5, 0.7), 2.5, 240)) * 2) / 2,
                })
    fields = pd.DataFrame(rows)
    # Injected issue: three implausible altitudes (GPS default of ~0 m)
    bad = rng.choice(fields.index[fields["meg_env"].isin(["Low-Mid-Dry", "Low-Mid-Wet"])], 3, replace=False)
    fields.loc[bad, "alt"] = [0.26, 0.26, 0.0]
    return fields


def make_plots(fields: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for _, f in fields.iterrows():
        field_effect = rng.normal(0, 1.3)
        planting = pd.Timestamp(SEASON_PLANTING[f["season"]]) + pd.Timedelta(days=int(rng.integers(-20, 25)))
        compost = float(np.clip(round(rng.normal(10.4, 3.2)), 0, 22))
        seed_var = rng.choice(["MV_605", "MV_403", "MV_507", "MV_505"], p=[0.4, 0.29, 0.21, 0.10])
        seeds = int(np.clip(round(rng.normal(35, 6.8)), 18, 50))
        prior = np.nan if (f["season"] == "22A" and rng.random() < 0.6) else rng.choice(PRIOR_CROPS)
        crop_label = "maize" if f["season"] == "22A" else "Maize"  # injected label inconsistency
        for code, t in TREATMENTS.items():
            v6 = planting + pd.Timedelta(days=int(rng.integers(36, 50)))
            v10 = v6 + pd.Timedelta(days=int(rng.integers(18, 28))) if t["v10"] else None
            silking = planting + pd.Timedelta(days=int(rng.integers(75, 100)))
            r3 = silking + pd.Timedelta(days=int(rng.integers(15, 35)))
            harvest = r3 + pd.Timedelta(days=int(rng.integers(25, 60)))
            total = t["planting"] + t["v6"] + t["v10"]
            yield_tha = (ME_MEAN[f["meg_env"]] + SEASON_SHIFT[f["season"]] + t["effect"]
                         + field_effect + 0.03 * (compost - 10) + rng.normal(0, 0.8))
            rows.append({
                "block_id": f["block_id"],
                "season": f["season"],
                "plot_id": f"{f['block_id']}-{f['season']}-{code}",
                "treat_code": code,
                "treat_details": t["details"],
                "urea_rate_timing": t["label"],
                "crop": crop_label,
                "prior_season_crop": prior,
                "planting_date": fmt_date(planting),
                "compost_tha": compost,
                "compost_quality": rng.choice(["Well_decomposed", "average", "poorly_decomposed"], p=[0.62, 0.32, 0.06]),
                "seed_variety": seed_var,
                "seeds_kgha": seeds,
                "dap_kgha": 100,
                "urea_planting_kgha": t["planting"],
                "germ_count_date": fmt_date(planting + pd.Timedelta(days=int(rng.integers(20, 35)))),
                "germination_rate": int(np.clip(round(rng.normal(85, 8)), 40, 100)),
                "urea_V6_date": fmt_date(v6),
                "urea_V6_kgha": t["v6"],
                "urea_V10_date": fmt_date(v10),
                "urea_V10_kgha": t["v10"],
                "urea_total_kgha": total,
                "N_kgha": t["n"],
                "silking_date": fmt_date(silking),
                "R3_date": fmt_date(r3),
                "harvest_date": fmt_date(harvest),
                "yield_tha": round(float(np.clip(yield_tha, 0.4, 11.5)), 2),
            })
    return pd.DataFrame(rows)


def inject_issues(fields: pd.DataFrame, plots: pd.DataFrame, rng: np.random.Generator):
    """Reproduce the data-quality problems found in the real data."""
    # 1. Two field-season units whose field record is missing (orphan plots)
    orphan_blocks = rng.choice(fields["block_id"].unique(), 2, replace=False)
    fields = fields[~fields["block_id"].isin(orphan_blocks)].copy()

    # 2. Five incomplete units (four lose one plot, one loses two)
    candidates = rng.choice(fields["block_id"].unique(), 5, replace=False)
    drop_idx = []
    for i, block in enumerate(candidates):
        idx = plots.index[plots["block_id"] == block].tolist()
        drop_idx += list(rng.choice(idx, 2 if i == 0 else 1, replace=False))
    plots = plots.drop(index=drop_idx)

    # 3. V10 date missing (quantity still recorded) for most 22A V6+V10 plots
    c22a = plots.index[(plots["treat_code"] == "C") & (plots["season"] == "22A")]
    plots.loc[rng.choice(c22a, min(115, len(c22a)), replace=False), "urea_V10_date"] = np.nan

    # 4. Urea totals off by 1 kg/ha (rounding in the source system)
    idx = rng.choice(plots.index, 160, replace=False)
    plots.loc[idx, "urea_total_kgha"] = plots.loc[idx, "urea_total_kgha"] + rng.choice([-1, 1], 160)

    # 5. Three plots where silking is recorded after R3
    for i in rng.choice(plots.index, 3, replace=False):
        r3 = pd.to_datetime(plots.at[i, "R3_date"], format="%m/%d/%Y")
        plots.at[i, "silking_date"] = fmt_date(r3 + pd.Timedelta(days=int(rng.integers(5, 30))))

    # 6. A handful of missing silking / R3 dates
    plots.loc[rng.choice(plots.index, 9, replace=False), "silking_date"] = np.nan
    plots.loc[rng.choice(plots.index, 4, replace=False), "R3_date"] = np.nan

    # 7. One yield entered with a misplaced decimal point (x10)
    i = rng.choice(plots.index[(plots["treat_code"] == "C") & (plots["season"] == "22B")])
    plots.at[i, "yield_tha"] = round(plots.at[i, "yield_tha"] * 10, 1)

    # 8. Two plots with an alternative wording of the treatment D description
    i = rng.choice(plots.index[plots["treat_code"] == "D"], 2, replace=False)
    plots.loc[i, "treat_details"] = "DAP 1Kg/Are + Urea 1Kg/Are at V6"
    return fields, plots


def make_soil(plots: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Soil sampled for under half of plots, unevenly by season; only pH filled."""
    share = {"21A": 0.75, "22A": 0.25, "22B": 0.40}
    keep = plots[[rng.random() < share[s] for s in plots["season"]]]
    soil = pd.DataFrame({
        "plot_id": keep["plot_id"].to_numpy(),
        "pH": np.round(np.clip(rng.normal(5.7, 0.6, len(keep)), 4.1, 7.2), 2),
        "tot_N": np.nan, "org_C": np.nan, "sand": np.nan,
    })
    soil.loc[rng.choice(soil.index, 2, replace=False), "pH"] = np.nan
    return soil


def main(seed: int) -> None:
    rng = np.random.default_rng(seed)
    fields = make_fields(rng)
    plots = make_plots(fields, rng)
    fields, plots = inject_issues(fields, plots, rng)
    soil = make_soil(plots, rng)

    # Shuffle row order within season so files don't look generated
    fields = fields.sample(frac=1, random_state=seed).sort_values("season", kind="stable")
    plots = plots.sort_values(["season", "block_id", "treat_code"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields.to_csv(OUT_DIR / "Field_Level.csv", index=False)
    plots.to_csv(OUT_DIR / "Plot_Level.csv", index=False)
    soil.to_csv(OUT_DIR / "Soil_PL.csv", index=False)
    print(f"Synthetic data written to {OUT_DIR}: "
          f"{len(fields)} fields, {len(plots)} plots, {len(soil)} soil records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=2026)
    main(parser.parse_args().seed)
