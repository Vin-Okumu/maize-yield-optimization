"""Turning treatment estimates into advice: economics and the decision-support tool."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config


# --------------------------------------------------------------------------- economics
def value_cost(gains: pd.DataFrame, scenarios=config.PRICE_SCENARIOS) -> pd.DataFrame:
    """Value-cost ratio (VCR) of each 100 kg/ha treatment against the 50 kg/ha baseline.

    VCR = value of extra maize / cost of extra urea. Uses the lower 95% bound too,
    so the reader can see whether the investment still pays in a weak year.
    Labour and transport are not included.
    """
    rows = []
    for s in scenarios:
        for _, g in gains.iterrows():
            extra_urea = config.EXTRA_UREA_KGHA[g["treatment"]]
            cost = extra_urea * s.urea_rwf_per_kg
            value = g["gain_vs_baseline"] * 1000 * s.maize_rwf_per_kg
            value_low = g["ci_low"] * 1000 * s.maize_rwf_per_kg
            rows.append({
                "scenario": s.name, "treatment": g["treatment"], "label": g["label"],
                "urea_rwf_per_kg": s.urea_rwf_per_kg, "maize_rwf_per_kg": s.maize_rwf_per_kg,
                "extra_urea_kgha": extra_urea, "extra_cost_rwf_ha": cost,
                "extra_yield_tha": g["gain_vs_baseline"], "extra_value_rwf_ha": value,
                "net_benefit_rwf_ha": value - cost, "vcr": value / cost if cost else np.nan,
                "vcr_at_ci_low": value_low / cost if cost else np.nan,
                "break_even_gain_tha": cost / (1000 * s.maize_rwf_per_kg),
                "meets_vcr_threshold": (value / cost if cost else 0) >= config.VCR_THRESHOLD,
            })
    return pd.DataFrame(rows)


def break_even_curve(gain_tha: float, urea_prices=np.arange(400, 2401, 50),
                     maize_prices=(200, 250, 300, 350, 400, 450)) -> pd.DataFrame:
    """VCR for treatment D across a grid of urea and maize prices."""
    grid = [(u, m, gain_tha * 1000 * m / (50 * u)) for m in maize_prices for u in urea_prices]
    return pd.DataFrame(grid, columns=["urea_rwf_per_kg", "maize_rwf_per_kg", "vcr"])


# --------------------------------------------------------------------------- decision table
def decision_table(pooled_gains: pd.DataFrame, per_env: pd.DataFrame, interactions: list[dict],
                   scenario: config.PriceScenario = config.PRICE_SCENARIOS[0]) -> pd.DataFrame:
    """One row per mega-environment with the recommended treatment and why.

    Rule (in order):
    1. If treatment effects do not differ by environment (interaction p >= 0.05),
       use the pooled estimate - it is more precise than any single environment.
    2. Recommend the highest-yielding treatment whose gain over the baseline is
       statistically significant AND whose VCR >= threshold at the given prices.
    3. Otherwise recommend the baseline (50 kg/ha at V6).
    4. Name an equivalent alternative when it is not significantly different.
    """
    me_p = next((i["p_value"] for i in interactions if i["interaction"].endswith("meg_env")), 0.0)
    pooled = pooled_gains.set_index("treatment")
    vcr = value_cost(pooled_gains, [scenario]).set_index("treatment")["vcr"]
    eligible = pooled[(pooled["significant"]) & (vcr.reindex(pooled.index) >= config.VCR_THRESHOLD)]
    pick = eligible["gain_vs_baseline"].idxmax() if len(eligible) else config.BASELINE

    rows = []
    for me in config.MEGA_ENVIRONMENTS:
        loc = per_env[per_env["meg_env"] == me].set_index("treatment")
        best_local = loc["adjusted_mean"].idxmax()
        local = loc.loc[pick]
        alt = [t for t in eligible.index if t != pick]
        rows.append({
            "meg_env": me,
            "n_fields": int(loc["n_fields"].iloc[0]),
            "recommended": pick,
            "recommended_label": config.TREATMENT_LABELS[pick],
            "alternative_label": config.TREATMENT_LABELS[alt[0]] if alt else "-",
            "avoid_label": ", ".join(config.TREATMENT_LABELS[t] for t in pooled.index
                                     if not pooled.loc[t, "significant"]),
            "pooled_gain_tha": pooled.loc[pick, "gain_vs_baseline"] if pick in pooled.index else 0.0,
            "local_gain_tha": local["gain_vs_baseline"],
            "local_ci_low": local["ci_low"], "local_ci_high": local["ci_high"],
            "local_best_treatment": config.TREATMENT_LABELS[best_local],
            "local_agrees": best_local == pick,
            "vcr": vcr.get(pick, np.nan),
            "basis": ("pooled estimate (no treatment x environment interaction, p = %.2f)" % me_p)
                     if me_p >= 0.05 else "environment-specific estimate",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- HTML tool
def write_decision_tool(per_env: pd.DataFrame, pooled_gains: pd.DataFrame, interactions: list[dict],
                        path: Path, data_label: str) -> None:
    """Self-contained HTML page: pick an environment and prices, get a recommendation."""
    me_p = next((i["p_value"] for i in interactions if i["interaction"].endswith("meg_env")), np.nan)
    pooled = {r.treatment: dict(gain=r.gain_vs_baseline, lo=r.ci_low, hi=r.ci_high, sig=bool(r.significant))
              for r in pooled_gains.itertuples()}
    local = {}
    for me, g in per_env.groupby("meg_env"):
        local[me] = {r.treatment: dict(gain=r.gain_vs_baseline,
                                       lo=None if pd.isna(r.ci_low) else r.ci_low,
                                       hi=None if pd.isna(r.ci_high) else r.ci_high,
                                       n=int(r.n_fields)) for r in g.itertuples()}
    payload = dict(
        treatments=config.TREATMENTS, labels=config.TREATMENT_LABELS, baseline=config.BASELINE,
        extra=config.EXTRA_UREA_KGHA, pooled=pooled, local=local, me_p=me_p,
        threshold=config.VCR_THRESHOLD,
        scenarios=[dict(name=s.name, urea=s.urea_rwf_per_kg, maize=s.maize_rwf_per_kg, source=s.source)
                   for s in config.PRICE_SCENARIOS],
        org=config.ORGANIZATION, data_label=data_label,
    )
    template = (Path(__file__).parent / "templates" / "decision_tool.html").read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.replace("__PAYLOAD__", json.dumps(payload, default=float)), encoding="utf-8")
