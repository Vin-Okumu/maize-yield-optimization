"""Add CHIRPS rainfall from planting to silking for every plot (`rain_plant_silking`).

Run on a machine with internet access, after the raw data is in 01_Data/raw/:

    python scripts/fetch_chirps_rainfall.py            # IRI Data Library subset (small download)
    python scripts/fetch_chirps_rainfall.py --source chc   # fallback: daily GeoTIFFs from UCSB CHC

Output: 01_Data/external/chirps_rain_plant_silking.csv  (plot_id, rain_plant_silking, ...)
The pipeline picks this file up automatically on the next run.

Data: CHIRPS v2.0 daily, 0.05° (~5.5 km). Funk et al. (2015), Scientific Data 2:150066.
Rainfall is summed from the planting date to the silking date (both inclusive) at the
grid cell nearest each field. Plots without a silking date are left missing.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from maize import config, data  # noqa: E402

CACHE = config.EXTERNAL_DIR / "cache" / "chirps"
BBOX = dict(west=28.8, east=31.0, south=-2.9, north=-1.0)  # Rwanda plus margin
IRIDL = ("https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.daily-improved/.global/.0p05/.prcp/"
         "X/{west}/{east}/RANGEEDGES/Y/{south}/{north}/RANGEEDGES/"
         "T/({start})/({end})/RANGEEDGES/data.nc")
CHC = ("https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_daily/tifs/p05/{y}/"
       "chirps-v2.0.{y}.{m:02d}.{d:02d}.tif.gz")


def plot_windows() -> pd.DataFrame:
    _, combined = data.build_combined("raw")
    w = combined[["plot_id", "lat", "long", "planting_date_parsed", "silking_date_parsed",
                  "flag_silking_date_before_planting_date"]].copy()
    w = w.rename(columns={"long": "lon", "planting_date_parsed": "start", "silking_date_parsed": "end"})
    return w


def daily_series_iridl(start: pd.Timestamp, end: pd.Timestamp) -> "xarray.DataArray":
    import xarray as xr  # pip install xarray netCDF4

    CACHE.mkdir(parents=True, exist_ok=True)
    nc = CACHE / f"chirps_rwanda_{start:%Y%m%d}_{end:%Y%m%d}.nc"
    if not nc.exists():
        url = IRIDL.format(**BBOX, start=f"{start:%d %b %Y}", end=f"{end:%d %b %Y}").replace(" ", "%20")
        print("Downloading", url)
        with urllib.request.urlopen(url, timeout=600) as r, open(nc, "wb") as f:
            shutil.copyfileobj(r, f)
    ds = xr.open_dataset(nc, decode_times=False)
    da = ds["prcp"]
    # IRI time axes come as "days since <date>" or as Julian days; convert either way
    units = str(ds["T"].attrs.get("units", "days since 1960-01-01")).lower()
    t = ds["T"].values.astype(float)
    if "since" in units:
        origin = pd.Timestamp(units.split("since")[1].strip().split(" ")[0])
        times = origin + pd.to_timedelta(t, unit="D")
    else:  # julian_day
        times = pd.to_datetime(t - 2440587.5, unit="D")
    da = da.assign_coords(T=pd.DatetimeIndex(times).normalize())
    return da.rename({"X": "lon", "Y": "lat", "T": "time"})


def daily_series_chc(start: pd.Timestamp, end: pd.Timestamp, points: pd.DataFrame) -> pd.DataFrame:
    """Fallback: read one Africa daily GeoTIFF per day; returns rain per (point, day)."""
    import rasterio  # pip install rasterio

    CACHE.mkdir(parents=True, exist_ok=True)
    out = {}
    for day in pd.date_range(start, end, freq="D"):
        tif = CACHE / f"{day:%Y%m%d}.tif"
        if not tif.exists():
            gz = tif.with_suffix(".tif.gz")
            urllib.request.urlretrieve(CHC.format(y=day.year, m=day.month, d=day.day), gz)
            with gzip.open(gz, "rb") as fi, open(tif, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            gz.unlink()
        with rasterio.open(tif) as src:
            vals = [v[0] for v in src.sample(zip(points["lon"], points["lat"]))]
        out[day] = np.where(np.array(vals) < 0, np.nan, vals)
    return pd.DataFrame(out, index=points.index).T  # rows = days, cols = point index


def window_totals(rain: pd.DataFrame, w: pd.DataFrame, key: pd.Series) -> np.ndarray:
    """Sum daily rain (rows = days, columns = location index) over each plot's window."""
    rain = rain.copy()
    rain.index = pd.to_datetime(rain.index).normalize()
    cum = rain.fillna(0).cumsum()
    totals = []
    for (_, r), k in zip(w.iterrows(), key):
        if pd.isna(r["start"]) or pd.isna(r["end"]) or r["end"] < r["start"]:
            totals.append(np.nan)
            continue
        before = cum[k].loc[:r["start"] - pd.Timedelta(days=1)]
        totals.append(cum[k].loc[:r["end"]].iloc[-1] - (before.iloc[-1] if len(before) else 0.0))
    return np.round(totals, 1)


def main(source: str) -> None:
    w = plot_windows()
    start, end = w["start"].min(), w["end"].max()
    pts = w[["lat", "lon"]].round(3).drop_duplicates().reset_index(drop=True)
    print(f"{len(w)} plots, {len(pts)} unique locations, {start:%Y-%m-%d} to {end:%Y-%m-%d}")

    if source == "iridl":
        da = daily_series_iridl(start, end)
        series = {}
        for i, p in pts.iterrows():
            s = da.sel(lat=p["lat"], lon=p["lon"], method="nearest").to_series()
            series[i] = s
        rain = pd.DataFrame(series)
    else:
        rain = daily_series_chc(start, end, pts)
    key = w[["lat", "lon"]].round(3).merge(pts.reset_index(), on=["lat", "lon"], how="left")["index"]
    w["rain_plant_silking"] = window_totals(rain, w, key)
    w["days_plant_silking"] = (w["end"] - w["start"]).dt.days

    config.EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    out = config.EXTERNAL_DIR / "chirps_rain_plant_silking.csv"
    w[["plot_id", "rain_plant_silking", "days_plant_silking"]].to_csv(out, index=False)
    print(f"Saved {out} ({w['rain_plant_silking'].notna().sum()} plots with rainfall)")
    print(w["rain_plant_silking"].describe().round(1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["iridl", "chc"], default="iridl")
    main(ap.parse_args().source)
