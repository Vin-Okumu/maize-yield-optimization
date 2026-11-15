"""Fill the empty soil variables (tot_N, org_C, sand) from SoilGrids 2.0.

Run from the repository root on a machine with internet access:

    python scripts/fetch_soilgrids.py                 # ISRIC REST API (default; needs only the standard library)
    python scripts/fetch_soilgrids.py --source vrt    # read the global rasters directly (needs rasterio)

or from notebook 05, which calls `run()` directly.

Outputs:
    01_Data/external/soilgrids_soil.csv     one row per field-season, sg_* columns (used by the pipeline)
    01_Data/external/Soil_PL_filled.csv     Soil_PL layout for every plot with tot_N, org_C and sand
                                            filled from SoilGrids (brief deliverable 5)

SoilGrids (ISRIC) predicts soil properties at ~250 m. Values are averaged over 0-30 cm,
weighted by layer thickness (0-5, 5-15, 15-30 cm). They are *modelled* values, so they are
kept in sg_* columns, separate from the measured pH.

The REST API allows about 5 requests per minute, so the script de-duplicates locations
(to ~100 m), waits between calls and caches every answer: it can be stopped and restarted.
If the REST service is down or too slow, use --source vrt, which reads the same layers from
ISRIC's cloud-optimised rasters (https://files.isric.org/soilgrids/latest/data/).
"""

from __future__ import annotations

import argparse
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
VRT = "/vsicurl/https://files.isric.org/soilgrids/latest/data/{prop}/{prop}_{depth}_mean.vrt"
PROPERTIES = ["nitrogen", "soc", "sand", "clay", "phh2o"]
D_FACTOR = {"nitrogen": 100, "soc": 10, "sand": 10, "clay": 10, "phh2o": 10}  # mapped -> conventional units
DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
CACHE = config.EXTERNAL_DIR / "cache" / "soilgrids"
WAIT_SECONDS = 12
PRECISION = 3  # ~110 m; SoilGrids cells are 250 m


# --------------------------------------------------------------------------- REST source
def query_rest(lat: float, lon: float, retries: int = 4) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{lat:.{PRECISION}f}_{lon:.{PRECISION}f}.json"
    if f.exists():
        return json.loads(f.read_text())
    params = [("lon", lon), ("lat", lat), ("value", "mean")]
    params += [("property", p) for p in PROPERTIES] + [("depth", d) for d in DEPTHS]
    url = URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "maize-yield-optimization/2.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                payload = json.load(r)
            f.write_text(json.dumps(payload))
            time.sleep(WAIT_SECONDS)
            return payload
        except Exception as e:  # noqa: BLE001 - network errors vary
            if attempt == retries - 1:
                raise RuntimeError(f"SoilGrids REST did not answer for {lat},{lon}: {e}. "
                                   "Try again later or use source='vrt'.") from e
            wait = WAIT_SECONDS * (attempt + 2)
            print(f"  {lat},{lon}: {str(e)[:80]} - retrying in {wait}s")
            time.sleep(wait)
    return {}


def topsoil_from_rest(payload: dict) -> dict:
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
    return out


# --------------------------------------------------------------------------- VRT source
def topsoil_from_vrt(locs: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Sample the global SoilGrids rasters at each location (needs rasterio)."""
    import rasterio
    from rasterio.warp import transform

    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / "vrt_samples.csv"
    if cache.exists():
        cached = pd.read_csv(cache)
        if len(cached.merge(locs, on=["lat_r", "lon_r"])) == len(locs):
            return cached
    out = locs.copy()
    with rasterio.Env(GDAL_HTTP_TIMEOUT="60", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for prop in PROPERTIES:
            layers = []
            for depth, thick in DEPTHS.items():
                with rasterio.open(VRT.format(prop=prop, depth=depth)) as src:
                    xs, ys = transform("EPSG:4326", src.crs, locs["lon_r"].tolist(), locs["lat_r"].tolist())
                    vals = np.array([v[0] for v in src.sample(zip(xs, ys))], dtype=float)
                    vals[vals == src.nodata] = np.nan
                    layers.append((vals / D_FACTOR[prop], thick))
            stack = np.vstack([v for v, _ in layers])
            weights = np.array([t for _, t in layers], dtype=float)[:, None]
            out[prop] = np.nansum(stack * weights, axis=0) / np.sum(weights * ~np.isnan(stack), axis=0)
            if verbose:
                print(f"  SoilGrids raster: {prop} done")
    out.to_csv(cache, index=False)
    return out


# --------------------------------------------------------------------------- main
def run(source: str = "rest", mode: str | None = None, verbose: bool = True) -> pd.DataFrame:
    """Fetch SoilGrids for every field, write both output files and return the field-level table."""
    src = data.load_sources(mode)
    fields = src["field"][["block_id", "season", "lat", "long"]].dropna(subset=["lat", "long"])
    fields = fields.assign(lat_r=fields["lat"].round(PRECISION), lon_r=fields["long"].round(PRECISION))
    locs = fields[["lat_r", "lon_r"]].drop_duplicates().reset_index(drop=True)

    if source == "rest":
        todo = sum(not (CACHE / f"{r.lat_r:.{PRECISION}f}_{r.lon_r:.{PRECISION}f}.json").exists()
                   for r in locs.itertuples())
        if verbose:
            print(f"SoilGrids: {len(fields)} field-seasons, {len(locs)} locations, {todo} not yet cached "
                  f"(about {todo * WAIT_SECONDS / 60:.0f} min at the API's rate limit)")
        rows = []
        for i, r in locs.iterrows():
            rows.append({"lat_r": r.lat_r, "lon_r": r.lon_r, **topsoil_from_rest(query_rest(r.lat_r, r.lon_r))})
            if verbose and ((i + 1) % 10 == 0 or i + 1 == len(locs)):
                print(f"  SoilGrids: {i + 1}/{len(locs)} locations")
        topsoil = pd.DataFrame(rows)
    else:
        if verbose:
            print(f"SoilGrids: {len(locs)} locations from the global rasters")
        topsoil = topsoil_from_vrt(locs, verbose)

    topsoil = topsoil.rename(columns={"nitrogen": "sg_nitrogen_g_kg", "soc": "sg_soc_g_kg", "sand": "sg_sand_pct",
                                      "clay": "sg_clay_pct", "phh2o": "sg_ph_h2o"})
    sg = fields.merge(topsoil, on=["lat_r", "lon_r"], how="left").drop(columns=["lat_r", "lon_r", "lat", "long"])
    config.EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    sg.round(3).to_csv(config.EXTERNAL_DIR / "soilgrids_soil.csv", index=False)

    # Brief deliverable: soil table for every plot with the three empty variables filled
    plots = src["plot"][["plot_id", "block_id", "season"]].merge(sg, on=["block_id", "season"], how="left")
    soil = plots[["plot_id"]].merge(src["soil"][["plot_id", "pH"]], on="plot_id", how="left")
    soil["tot_N"] = plots["sg_nitrogen_g_kg"].to_numpy() / 10   # g/kg -> %
    soil["org_C"] = plots["sg_soc_g_kg"].to_numpy() / 10        # g/kg -> %
    soil["sand"] = plots["sg_sand_pct"].to_numpy()
    soil["source_pH"] = np.where(soil["pH"].notna(), "measured (Soil_PL)", "not available")
    soil["source_tot_N_org_C_sand"] = "SoilGrids 2.0, 0-30 cm weighted mean"
    soil.round(3).to_csv(config.EXTERNAL_DIR / "Soil_PL_filled.csv", index=False)
    if verbose:
        print(f"Saved soilgrids_soil.csv and Soil_PL_filled.csv in {config.EXTERNAL_DIR}")
    return sg


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Fill tot_N, org_C and sand from SoilGrids")
    ap.add_argument("--source", choices=["rest", "vrt"], default="rest")
    ap.add_argument("--data", choices=["raw", "sample"], help="data source (default: auto)")
    args = ap.parse_args()
    print(run(args.source, args.data).describe().round(2))
