"""Add CHIRPS rainfall from planting to silking for every plot (`rain_plant_silking`).

Run from the repository root on a machine with internet access:

    python scripts/fetch_chirps_rainfall.py                  # NOAA ERDDAP (default; needs only pandas)
    python scripts/fetch_chirps_rainfall.py --source iridl   # IRI Data Library (needs xarray + netCDF4)

or from notebook 05, which calls `run()` directly.

Output: 01_Data/external/chirps_rain_plant_silking.csv  (plot_id, rain_plant_silking, days_plant_silking)
The pipeline picks this file up automatically on the next run.

Data: CHIRPS v2.0 daily, 0.05° (~5.5 km). Funk et al. (2015), Scientific Data 2:150066.
Rainfall is summed from the planting date to the silking date (both inclusive) at the
grid cell nearest each field. Plots without a silking date are left missing.
Every download is cached in 01_Data/external/cache/chirps, so re-runs are instant and an
interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maize import config, data  # noqa: E402

CACHE = config.EXTERNAL_DIR / "cache" / "chirps"
OUTPUT = config.EXTERNAL_DIR / "chirps_rain_plant_silking.csv"
GRID = 0.05  # CHIRPS cell size (degrees); cell centres sit at x.x25 / x.x75

ERDDAP = ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/chirps20GlobalDailyP05.csv"
          "?precip[({start}T00:00:00Z):1:({end}T00:00:00Z)][({lat:.3f})][({lon:.3f})]")
IRIDL = ("https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.daily-improved/.global/.0p05/.prcp/"
         "X/28.8/31.0/RANGEEDGES/Y/-2.9/-1.0/RANGEEDGES/T/({start})/({end})/RANGEEDGES/data.nc")


# --------------------------------------------------------------------------- inputs
def plot_windows(mode: str | None = None) -> pd.DataFrame:
    """Planting-to-silking window and location for every plot."""
    _, combined = data.build_combined(mode)
    w = combined[["plot_id", "lat", "long", "planting_date_parsed", "silking_date_parsed"]].rename(
        columns={"long": "lon", "planting_date_parsed": "start", "silking_date_parsed": "end"})
    # snap each field to its CHIRPS cell centre, so fields in the same cell share one download
    w["cell_lat"] = (np.floor(w["lat"] / GRID) * GRID + GRID / 2).round(3)
    w["cell_lon"] = (np.floor(w["lon"] / GRID) * GRID + GRID / 2).round(3)
    return w


# --------------------------------------------------------------------------- sources
def _download(url: str, dest: Path, retries: int = 3) -> Path:
    for attempt in range(retries):
        try:
            tmp = dest.with_suffix(".part")
            req = urllib.request.Request(url, headers={"User-Agent": "maize-yield-optimization/2.0"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(dest)
            return dest
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise RuntimeError(f"Download failed after {retries} attempts: {url}\n{e}") from e
            time.sleep(5 * (attempt + 1))
    return dest


def daily_rain_erddap(cells: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                      verbose: bool = True) -> pd.DataFrame:
    """Daily rainfall (mm) per CHIRPS cell. Rows = dates, columns = cell index."""
    CACHE.mkdir(parents=True, exist_ok=True)
    series = {}
    for i, c in cells.iterrows():
        f = CACHE / f"erddap_{c.cell_lat:.3f}_{c.cell_lon:.3f}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
        if not f.exists():
            url = ERDDAP.format(start=f"{start:%Y-%m-%d}", end=f"{end:%Y-%m-%d}", lat=c.cell_lat, lon=c.cell_lon)
            _download(url, f)
        # ERDDAP CSV: header row, units row, then data
        df = pd.read_csv(f, skiprows=[1])
        s = pd.Series(pd.to_numeric(df["precip"], errors="coerce").to_numpy(),
                      index=pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize())
        series[i] = s
        if verbose and ((i + 1) % 25 == 0 or i + 1 == len(cells)):
            print(f"  CHIRPS: {i + 1}/{len(cells)} cells")
    return pd.DataFrame(series)


def daily_rain_iridl(cells: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                     verbose: bool = True) -> pd.DataFrame:
    import xarray as xr  # pip install xarray netCDF4

    CACHE.mkdir(parents=True, exist_ok=True)
    nc = CACHE / f"iridl_rwanda_{start:%Y%m%d}_{end:%Y%m%d}.nc"
    if not nc.exists():
        url = IRIDL.format(start=f"{start:%d %b %Y}", end=f"{end:%d %b %Y}").replace(" ", "%20")
        if verbose:
            print("  Downloading", url)
        _download(url, nc)
    ds = xr.open_dataset(nc, decode_times=False)
    units = str(ds["T"].attrs.get("units", "days since 1960-01-01")).lower()
    t = ds["T"].values.astype(float)
    if "since" in units:
        origin = pd.Timestamp(units.split("since")[1].strip().split(" ")[0])
        times = origin + pd.to_timedelta(t, unit="D")
    else:  # julian_day
        times = pd.to_datetime(t - 2440587.5, unit="D")
    da = ds["prcp"].assign_coords(T=pd.DatetimeIndex(times).normalize())
    out = {i: da.sel(Y=c.cell_lat, X=c.cell_lon, method="nearest").to_series() for i, c in cells.iterrows()}
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- totals
def window_totals(rain: pd.DataFrame, w: pd.DataFrame, key: pd.Series) -> np.ndarray:
    """Sum daily rain (rows = days, columns = location index) over each plot's window."""
    rain = rain.copy()
    rain.index = pd.to_datetime(rain.index).normalize()
    rain = rain[~rain.index.duplicated()].sort_index()
    cum = rain.fillna(0).cumsum()
    totals = []
    for (_, r), k in zip(w.iterrows(), key):
        if pd.isna(r["start"]) or pd.isna(r["end"]) or r["end"] < r["start"] or pd.isna(k):
            totals.append(np.nan)
            continue
        before = cum[k].loc[:r["start"] - pd.Timedelta(days=1)]
        totals.append(cum[k].loc[:r["end"]].iloc[-1] - (before.iloc[-1] if len(before) else 0.0))
    return np.round(totals, 1)


def run(source: str = "erddap", mode: str | None = None, verbose: bool = True) -> pd.DataFrame:
    """Download (or read from cache) CHIRPS rainfall and write the output file. Returns it."""
    w = plot_windows(mode)
    w = w[w["lat"].notna()]
    start = w["start"].min().normalize()
    end = w["end"].max().normalize()
    cells = w[["cell_lat", "cell_lon"]].drop_duplicates().reset_index(drop=True)
    if verbose:
        print(f"CHIRPS: {len(w)} plots, {len(cells)} grid cells, {start:%Y-%m-%d} to {end:%Y-%m-%d} "
              f"(source: {source})")

    fetch = {"erddap": daily_rain_erddap, "iridl": daily_rain_iridl}[source]
    rain = fetch(cells, start, end, verbose)

    key = w[["cell_lat", "cell_lon"]].merge(cells.reset_index(), on=["cell_lat", "cell_lon"], how="left")["index"]
    w["rain_plant_silking"] = window_totals(rain, w, key.to_numpy())
    w["days_plant_silking"] = (w["end"] - w["start"]).dt.days

    out = w[["plot_id", "rain_plant_silking", "days_plant_silking"]]
    config.EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False)
    if verbose:
        print(f"Saved {OUTPUT}: {out['rain_plant_silking'].notna().sum()} plots with rainfall")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Add CHIRPS planting-to-silking rainfall")
    ap.add_argument("--source", choices=["erddap", "iridl"], default="erddap")
    ap.add_argument("--data", choices=["raw", "sample"], help="data source (default: auto)")
    args = ap.parse_args()
    print(run(args.source, args.data)["rain_plant_silking"].describe().round(1))
