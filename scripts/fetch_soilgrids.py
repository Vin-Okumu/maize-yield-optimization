"""Fill the empty soil variables (tot_N, org_C, sand) from SoilGrids 2.0.

Run on a machine with internet access, after the raw data is in 01_Data/raw/:

    python scripts/fetch_soilgrids.py

Outputs (both picked up or referenced by the pipeline):
    01_Data/external/soilgrids_soil.csv        one row per field-season, sg_* columns
    01_Data/external/Soil_PL_filled.csv        Soil_PL layout for every plot, with tot_N, org_C
                                               and sand filled from SoilGrids (brief deliverable 5)

SoilGrids (ISRIC) predicts soil properties at ~250 m. Values are averaged over 0-30 cm,
weighted by layer thickness (0-5, 5-15, 15-30 cm). These are *modelled* values, so they
are kept in sg_* columns, separate from the measured pH.

The public REST API allows about 5 requests per minute, so the script de-duplicates
locations, waits between calls and caches every answer - it can be stopped and restarted.
If the REST service is down, the same layers can be read from the ISRIC WCS service
(https://maps.isric.org) or Google Earth Engine (projects/soilgrids-isric).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maize import config, data  # noqa: E402

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["nitrogen", "soc", "sand", "clay", "phh2o"]
DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
CACHE = config.EXTERNAL_DIR / "cache" / "soilgrids"
WAIT_SECONDS = 13


def query(lat: float, lon: float, retries: int = 4) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{lat:.4f}_{lon:.4f}.json"
    if f.exists():
        return json.loads(f.read_text())
    params = [("lon", lon), ("lat", lat), ("value", "mean")]
    params += [("property", p) for p in PROPERTIES] + [("depth", d) for d in DEPTHS]
    url = URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                payload = json.load(r)
            f.write_text(json.dumps(payload))
            time.sleep(WAIT_SECONDS)
            return payload
        except Exception as e:  # noqa: BLE001 - network errors vary
            wait = WAIT_SECONDS * (attempt + 2)
            print(f"  {lat:.4f},{lon:.4f}: {e!s:.80} - retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"SoilGrids did not answer for {lat},{lon}")


def to_topsoil(payload: dict) -> dict:
    """Thickness-weighted 0-30 cm mean, converted to conventional units by the API's d_factor."""
    out = {}
    for layer in payload["properties"]["layers"]:
        factor = layer["unit_measure"]["d_factor"]
        vals, wts = [], []
        for d in layer["depths"]:
            v = d["values"].get("mean")
            if v is not None and d["label"] in DEPTHS:
                vals.append(v / factor)
                wts.append(DEPTHS[d["label"]])
        out[layer["name"]] = float(np.average(vals, weights=wts)) if vals else np.nan
    return {
        "sg_nitrogen_g_kg": out.get("nitrogen"),   # cg/kg / 100 -> g/kg
        "sg_soc_g_kg": out.get("soc"),             # dg/kg / 10  -> g/kg
        "sg_sand_pct": out.get("sand"),            # g/kg / 10   -> %
        "sg_clay_pct": out.get("clay"),            # g/kg / 10   -> %
        "sg_ph_h2o": out.get("phh2o"),
    }


def main() -> None:
    src = data.load_sources("raw")
    fields = src["field"][["block_id", "season", "lat", "long"]].rename(columns={"long": "lon"})
    fields["lat_r"], fields["lon_r"] = fields["lat"].round(4), fields["lon"].round(4)
    locs = fields[["lat_r", "lon_r"]].drop_duplicates().reset_index(drop=True)
    eta = len([1 for _, r in locs.iterrows()
               if not (CACHE / f"{r.lat_r:.4f}_{r.lon_r:.4f}.json").exists()]) * WAIT_SECONDS / 60
    print(f"{len(fields)} field-seasons, {len(locs)} unique locations (about {eta:.0f} min for uncached ones)")

    rows = []
    for i, r in locs.iterrows():
        rows.append({"lat_r": r.lat_r, "lon_r": r.lon_r, **to_topsoil(query(r.lat_r, r.lon_r))})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(locs)} locations")
    sg = fields.merge(pd.DataFrame(rows), on=["lat_r", "lon_r"], how="left")
    sg = sg.drop(columns=["lat_r", "lon_r", "lat", "lon"])
    config.EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    sg.to_csv(config.EXTERNAL_DIR / "soilgrids_soil.csv", index=False)

    # Brief deliverable: soil table for every plot with the three empty variables filled
    plots = src["plot"][["plot_id", "block_id", "season"]].merge(sg, on=["block_id", "season"], how="left")
    soil = plots[["plot_id"]].merge(src["soil"][["plot_id", "pH"]], on="plot_id", how="left")
    soil["tot_N"] = plots["sg_nitrogen_g_kg"] / 10   # g/kg -> %
    soil["org_C"] = plots["sg_soc_g_kg"] / 10        # g/kg -> %
    soil["sand"] = plots["sg_sand_pct"]
    soil["source_pH"] = np.where(soil["pH"].notna(), "measured (Soil_PL)", "not available")
    soil["source_tot_N_org_C_sand"] = "SoilGrids 2.0, 0-30 cm weighted mean"
    soil.round(3).to_csv(config.EXTERNAL_DIR / "Soil_PL_filled.csv", index=False)
    print("Saved soilgrids_soil.csv and Soil_PL_filled.csv in", config.EXTERNAL_DIR)


if __name__ == "__main__":
    main()
