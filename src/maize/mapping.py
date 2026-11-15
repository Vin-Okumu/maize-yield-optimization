"""Maps of the trial fields (Objective 4).

Published maps round coordinates to 2 decimal places (about 1 km) so that
individual farms cannot be located. Pass `precision=None` for an exact,
local-only map.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from . import config, plotting

def field_points(combined: pd.DataFrame, precision: int | None = 2) -> pd.DataFrame:
    fields = (combined[combined["has_field_match"]]
              .groupby(["block_id", "season"], as_index=False)
              .agg(lat=("lat", "first"), lon=("long", "first"), meg_env=("meg_env", "first"),
                   district=("district", "first"), yield_mean=("yield_tha", "median"), plots=("plot_id", "size")))
    if precision is not None:
        fields["lat"] = fields["lat"].round(precision)
        fields["lon"] = fields["lon"].round(precision)
    return fields.drop(columns="block_id")


def interactive_map(combined: pd.DataFrame, path: Path, precision: int | None = 2) -> None:
    pts = field_points(combined, precision)
    data = pts.round({"yield_mean": 2}).to_dict("records")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trial fields by season · Evergreen maize-Urea trial</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 html,body,#map{{height:100%;margin:0;font:14px system-ui,sans-serif}}
 .box{{background:#fcfcfb;color:#0b0b0b;padding:10px 12px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.15);line-height:1.5}}
 .box h3{{margin:0 0 4px;font-size:15px}} .box i{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
 .box small{{color:#52514e}}
</style></head><body><div id="map"></div>
<script>
const pts = {json.dumps(data)};
const colors = {json.dumps(config.SEASON_COLORS)};
const map = L.map('map').setView([-1.95, 29.9], 9);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 13,
  attribution: '&copy; OpenStreetMap contributors'}}).addTo(map);
const layers = {{}};
Object.keys(colors).forEach(s => layers[s] = L.layerGroup().addTo(map));
pts.forEach(p => L.circleMarker([p.lat, p.lon], {{radius: 6, color: '#fcfcfb', weight: 2,
  fillColor: colors[p.season], fillOpacity: .9}})
  .bindTooltip(`<b>Season ${{p.season}}</b><br>${{p.district}} · ${{p.meg_env}}<br>Median yield ${{p.yield_mean}} t/ha (${{p.plots}} plots)`)
  .addTo(layers[p.season]));
const counts = s => pts.filter(p => p.season === s).length;
L.control.layers(null, Object.fromEntries(Object.keys(colors).map(s =>
  [`<i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{colors[s]}}"></i> ${{s}} (${{counts(s)}} fields)`, layers[s]])),
  {{collapsed: false}}).addTo(map);
const info = L.control({{position: 'bottomleft'}});
info.onAdd = () => {{ const d = L.DomUtil.create('div', 'box');
  d.innerHTML = '<h3>Evergreen maize–Urea trial fields</h3>' + pts.length + ' field-seasons, coloured by season<br>' +
  '<small>{"Locations rounded to ~1 km to protect farmers" if precision is not None else "Exact locations - do not share"}</small>'; return d; }};
info.addTo(map);
</script></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def static_map(combined: pd.DataFrame, path: Path, precision: int | None = 2) -> None:
    """Three small maps (one per season) so overlapping sites stay visible."""
    pts = field_points(combined, precision)
    plotting.style()
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6), sharex=True, sharey=True)
    for ax, s in zip(axes, config.SEASONS):
        ax.scatter(pts["lon"], pts["lat"], s=14, color="#d9d7d0", lw=0, zorder=1)
        sub = pts[pts["season"] == s]
        ax.scatter(sub["lon"], sub["lat"], s=30, color=config.SEASON_COLORS[s], edgecolor="#fcfcfb",
                   linewidth=0.8, zorder=3)
        ax.set_title(f"Season {s} · {len(sub)} fields", loc="left", fontsize=11)
        ax.set_aspect("equal")
        ax.set_xlabel("Longitude")
    axes[0].set_ylabel("Latitude")
    axes[0].set_xlim(28.9, 30.9)
    axes[0].set_ylim(-2.75, -1.25)
    fig.suptitle("Trial fields by season", x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.text(0.01, 0.925, "Grey = fields from other seasons. Locations rounded to ~1 km. "
             "Interactive version: 03_Report/maps/trial_fields_map.html", color=plotting.INK2, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
