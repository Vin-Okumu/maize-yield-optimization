"""Treatment-effect analysis with linear mixed-effects models.

Plots in the same field share soil, management and weather, so each model
includes a random intercept for the field-season unit. Treatment effects
are therefore estimated mostly from within-field contrasts.

All statsmodels calls go through `_fit`, which returns a small `MixedFit`
object; everything else works with plain numpy / pandas.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

from . import config

TREAT = "urea_rate_timing"
BASE_FORMULA = f"yield_tha ~ C({TREAT}) + C(season) + C(meg_env)"


@dataclass
class MixedFit:
    fe_params: pd.Series            # fixed-effect estimates
    cov_fe: pd.DataFrame            # covariance of fixed effects
    llf: float                      # log-likelihood
    fitted: pd.Series               # fitted values (fixed + random parts)
    resid: pd.Series                # residuals
    design: Callable[[pd.DataFrame], np.ndarray]  # builds X for new data
    n_obs: int
    n_groups: int
    group_var: float
    resid_var: float


def _fit(df: pd.DataFrame, formula: str, reml: bool = True) -> MixedFit:
    """Fit a random-intercept model (groups = field_season_id) with statsmodels."""
    import statsmodels.formula.api as smf
    from patsy import build_design_matrices

    result = smf.mixedlm(formula, data=df, groups=df["field_season_id"]).fit(reml=reml)
    names = result.fe_params.index
    design_info = result.model.data.design_info

    def design(new: pd.DataFrame) -> np.ndarray:
        return np.asarray(build_design_matrices([design_info], new, return_type="dataframe")[0])

    return MixedFit(
        fe_params=result.fe_params,
        cov_fe=result.cov_params().loc[names, names],
        llf=float(result.llf),
        fitted=pd.Series(result.fittedvalues, index=df.index),
        resid=pd.Series(result.resid, index=df.index),
        design=design,
        n_obs=int(result.nobs),
        n_groups=len(result.model.group_labels),
        group_var=float(result.cov_re.iloc[0, 0]),
        resid_var=float(result.scale),
    )


# --------------------------------------------------------------------------- helpers
def _with_treatment(df: pd.DataFrame, treatment: str) -> pd.DataFrame:
    new = df.copy()
    new[TREAT] = pd.Categorical([treatment] * len(new), categories=config.TREATMENTS)
    return new


def _mean_design(fit: MixedFit, df: pd.DataFrame, treatment: str) -> np.ndarray:
    """Average design row with every plot set to `treatment` (marginal / adjusted mean)."""
    return fit.design(_with_treatment(df, treatment)).mean(axis=0)


def _contrast(fit: MixedFit, vec: np.ndarray) -> tuple[float, float]:
    est = float(vec @ fit.fe_params.to_numpy())
    se = float(np.sqrt(max(vec @ fit.cov_fe.to_numpy() @ vec, 0.0)))
    return est, se


def _holm(p: pd.Series) -> pd.Series:
    """Holm step-down adjustment (same as statsmodels multipletests 'holm')."""
    order = np.argsort(p.to_numpy())
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p.iloc[idx])
        adj[idx] = min(running, 1.0)
    return pd.Series(adj, index=p.index)


# --------------------------------------------------------------------------- main analyses
def treatment_effects(df: pd.DataFrame, formula: str = BASE_FORMULA, reml: bool = True) -> dict:
    """Adjusted means, gains vs baseline and Holm-adjusted pairwise comparisons."""
    fit = _fit(df, formula, reml=reml)
    treatments = [t for t in config.TREATMENTS if (df[TREAT] == t).any()]
    rows_x = {t: _mean_design(fit, df, t) for t in treatments}

    means = []
    for t in treatments:
        est, se = _contrast(fit, rows_x[t])
        means.append({"treatment": t, "label": config.TREATMENT_LABELS[t],
                      "n_plots": int((df[TREAT] == t).sum()), "adjusted_mean": est, "se": se,
                      "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se})
    means = pd.DataFrame(means)

    pairs = []
    for a, b in combinations(treatments, 2):
        est, se = _contrast(fit, rows_x[b] - rows_x[a])
        z = est / se if se > 0 else np.nan
        pairs.append({"treatment_a": a, "treatment_b": b,
                      "label": f"{config.SHORT_LABELS[b]} vs {config.SHORT_LABELS[a]}",
                      "difference_b_minus_a": est, "se": se,
                      "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se,
                      "p_value": 2 * norm.sf(abs(z))})
    pairs = pd.DataFrame(pairs)
    pairs["p_holm"] = _holm(pairs["p_value"])
    pairs["significant"] = pairs["p_holm"] < 0.05

    base = means.set_index("treatment").loc[config.BASELINE, "adjusted_mean"]
    gains = pairs[pairs["treatment_a"] == config.BASELINE].rename(
        columns={"treatment_b": "treatment", "difference_b_minus_a": "gain_vs_baseline"})
    gains["gain_pct"] = 100 * gains["gain_vs_baseline"] / base
    gains = gains[["treatment", "gain_vs_baseline", "se", "ci_low", "ci_high", "gain_pct",
                   "p_value", "p_holm", "significant"]]
    gains.insert(1, "label", gains["treatment"].map(config.TREATMENT_LABELS))

    variance = pd.DataFrame({
        "component": ["Between fields (random intercept)", "Within field (residual)"],
        "variance": [fit.group_var, fit.resid_var],
    })
    variance["share"] = variance["variance"] / variance["variance"].sum()
    return {"fit": fit, "adjusted_means": means, "pairwise": pairs, "gains": gains,
            "variance": variance, "n_obs": fit.n_obs, "n_groups": fit.n_groups}


def interaction_test(df: pd.DataFrame, by: str) -> dict:
    """Likelihood-ratio test: do treatment effects differ by `by` (meg_env or season)?"""
    others = [v for v in ("season", "meg_env") if v != by]
    base = _fit(df, BASE_FORMULA, reml=False)
    full = _fit(df, f"yield_tha ~ C({TREAT}) * C({by}) + " + " + ".join(f"C({o})" for o in others), reml=False)
    lr = 2 * (full.llf - base.llf)
    dof = len(full.fe_params) - len(base.fe_params)
    return {"interaction": f"Treatment x {by}", "lr_statistic": lr, "df": dof, "p_value": chi2.sf(lr, dof)}


def per_environment(df: pd.DataFrame) -> pd.DataFrame:
    """Best treatment in each mega-environment (Objective 1a).

    A separate model per mega-environment (treatment + season, random field
    intercept). Reports each treatment's gain over the baseline and whether
    the top treatment beats the runner-up (Holm-adjusted across that ME's
    six comparisons).
    """
    rows = []
    for me in config.MEGA_ENVIRONMENTS:
        sub = df[df["meg_env"] == me].copy()
        if sub.empty:
            continue
        formula = f"yield_tha ~ C({TREAT})" + (" + C(season)" if sub["season"].nunique() > 1 else "")
        res = treatment_effects(sub, formula)
        means = res["adjusted_means"].set_index("treatment")["adjusted_mean"]
        ranked = means.sort_values(ascending=False)
        best, runner = ranked.index[0], ranked.index[1]
        pw = res["pairwise"]
        pair = pw[((pw.treatment_a == best) & (pw.treatment_b == runner)) |
                  ((pw.treatment_a == runner) & (pw.treatment_b == best))].iloc[0]
        gains = res["gains"].set_index("treatment")
        for t in config.TREATMENTS:
            g = gains.loc[t] if t in gains.index else None
            rows.append({
                "meg_env": me, "n_fields": sub["field_season_id"].nunique(), "n_plots": len(sub),
                "treatment": t, "label": config.TREATMENT_LABELS[t],
                "adjusted_mean": means.get(t, np.nan), "rank": int(ranked.index.get_loc(t)) + 1,
                "gain_vs_baseline": 0.0 if g is None else g["gain_vs_baseline"],
                "ci_low": np.nan if g is None else g["ci_low"],
                "ci_high": np.nan if g is None else g["ci_high"],
                "p_holm_vs_baseline": np.nan if g is None else g["p_holm"],
                "is_best": t == best,
                "best_vs_runner_up_diff": abs(pair["difference_b_minus_a"]) if t == best else np.nan,
                "best_vs_runner_up_p_holm": pair["p_holm"] if t == best else np.nan,
            })
    return pd.DataFrame(rows)


def outlier_sensitivity(df: pd.DataFrame) -> pd.DataFrame:
    """Treatment gains with and without implausible yields."""
    with_all = treatment_effects(df)["gains"].set_index("treatment")
    without = treatment_effects(df[~df["flag_implausible_yield"]].copy())["gains"].set_index("treatment")
    out = pd.DataFrame({
        "label": with_all["label"],
        "gain_all_plots": with_all["gain_vs_baseline"],
        "p_holm_all_plots": with_all["p_holm"],
        "gain_without_implausible": without["gain_vs_baseline"],
        "p_holm_without_implausible": without["p_holm"],
    })
    out["change"] = out["gain_without_implausible"] - out["gain_all_plots"]
    return out.reset_index()


def agronomic_drivers(df: pd.DataFrame, predictors: list[str] | None = None) -> pd.DataFrame:
    """Mixed model adding management variables; coefficients per unit change."""
    predictors = predictors or ["compost_tha", "seeds_kgha", "dap_kgha", "germination_rate"]
    predictors = [p for p in predictors if p in df and df[p].notna().any()]
    sub = df.dropna(subset=predictors).copy()
    formula = BASE_FORMULA + " + " + " + ".join(predictors)
    fit = _fit(sub, formula)
    rows = []
    for p in predictors:
        est, se = float(fit.fe_params[p]), float(np.sqrt(fit.cov_fe.loc[p, p]))
        rows.append({"variable": p, "effect_per_unit": est, "se": se,
                     "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se,
                     "p_value": 2 * norm.sf(abs(est / se)), "n_obs": fit.n_obs})
    return pd.DataFrame(rows)


def residual_frame(df: pd.DataFrame) -> pd.DataFrame:
    fit = _fit(df, BASE_FORMULA)
    return pd.DataFrame({"fitted": fit.fitted, "residual": fit.resid,
                         "flag_implausible_yield": df["flag_implausible_yield"]})
