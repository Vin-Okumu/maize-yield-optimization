"""Figures. Every function saves a PNG so the report figures can be regenerated."""

from __future__ import annotations

from pathlib import Path

import sys

import matplotlib

if "ipykernel" not in sys.modules:  # scripts: render off-screen; notebooks keep their backend
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from . import config  # noqa: E402

INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#7a7974", "#e7e5df", "#fcfcfb"


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
        "font.size": 10.5, "axes.titlesize": 13, "axes.titleweight": "bold", "legend.frameon": False,
        "axes.axisbelow": True, "xtick.major.size": 0, "ytick.major.size": 0,
    })


def title(ax, main: str, sub: str | None = None) -> None:
    ax.set_title(main, loc="left", pad=22 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK2, fontsize=10, va="bottom")


def save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _short(t):
    return config.SHORT_LABELS[t]


# --------------------------------------------------------------------------- audit
def missingness_by_season(field: pd.DataFrame, plot: pd.DataFrame, path: Path) -> None:
    style()
    f = field.drop(columns=["block_id", "season"]).isna().groupby(field["season"]).mean()
    p = plot[["prior_season_crop", "urea_V10_date", "silking_date", "R3_date"]].isna().groupby(plot["season"]).mean()
    m = pd.concat([f, p], axis=1)
    m = m.loc[:, m.max() > 0].T
    fig, ax = plt.subplots(figsize=(6.5, 0.42 * len(m) + 1.4))
    im = ax.imshow(m.to_numpy(), cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
        "b", ["#f4f8fd", "#86b6ef", "#1c5cab", "#0d366b"]), vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(m.shape[1]), m.columns)
    ax.set_yticks(range(len(m)), m.index)
    ax.grid(False)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.iat[i, j]
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=9, color="white" if v > .55 else INK)
    title(ax, "Missingness depends on season", "Share of records missing, by variable and season")
    save(fig, path)


# --------------------------------------------------------------------------- EDA
def yield_by_treatment(df: pd.DataFrame, path: Path) -> None:
    style()
    fig, ax = plt.subplots(figsize=(8, 4.6))
    plotted = df[~df["flag_implausible_yield"]]
    for i, t in enumerate(config.TREATMENTS):
        y = plotted.loc[plotted["urea_rate_timing"] == t, "yield_tha"]
        parts = ax.violinplot(y, positions=[i], widths=0.8, showextrema=False)
        for b in parts["bodies"]:
            b.set_facecolor(config.TREATMENT_COLORS[t]); b.set_alpha(0.25); b.set_edgecolor("none")
        q1, med, q3 = np.percentile(y, [25, 50, 75])
        ax.plot([i, i], [q1, q3], color=config.TREATMENT_COLORS[t], lw=5, solid_capstyle="round")
        ax.scatter([i], [med], color=SURFACE, edgecolor=config.TREATMENT_COLORS[t], s=40, zorder=3, lw=2)
        ax.text(i + 0.12, med, f"median {med:.2f}", va="center", fontsize=9, color=INK2)
    ax.set_xticks(range(4), [config.TREATMENT_LABELS[t] for t in config.TREATMENTS], fontsize=9)
    ax.set_ylabel("Grain yield (t/ha)")
    n_out = int(df["flag_implausible_yield"].sum())
    title(ax, "Yield by Urea treatment",
          "Distribution with interquartile range and median" + (f"; {n_out} implausible value not shown" if n_out else ""))
    save(fig, path)


def yield_by_treatment_season(df: pd.DataFrame, path: Path) -> None:
    style()
    d = df[~df["flag_implausible_yield"]]
    g = d.groupby(["season", "urea_rate_timing"], observed=True)["yield_tha"].agg(["mean", "sem", "size"]).reset_index()
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    offsets = np.linspace(-0.27, 0.27, 4)
    for k, t in enumerate(config.TREATMENTS):
        s = g[g["urea_rate_timing"] == t]
        x = np.array([config.SEASONS.index(v) for v in s["season"]]) + offsets[k]
        ax.errorbar(x, s["mean"], yerr=1.96 * s["sem"], fmt="o", ms=7, lw=2, capsize=0,
                    color=config.TREATMENT_COLORS[t], mec=SURFACE, mew=1.5, label=config.TREATMENT_LABELS[t])
    ax.set_xticks(range(3), [f"Season {s}" for s in config.SEASONS])
    ax.set_ylabel("Mean yield (t/ha)")
    ax.legend(ncol=2, loc="upper left", fontsize=9)
    title(ax, "Mean yield by treatment and season", "Raw means with 95% intervals (implausible yield excluded)")
    save(fig, path)


# --------------------------------------------------------------------------- treatment effects
def treatment_gains(gains: pd.DataFrame, path: Path) -> None:
    style()
    g = gains.set_index("treatment").loc[config.TREATMENTS[1:]].reset_index()
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    y = np.arange(len(g))[::-1]
    for yi, r in zip(y, g.itertuples()):
        c = config.TREATMENT_COLORS[r.treatment]
        ax.plot([r.ci_low, r.ci_high], [yi, yi], color=c, lw=3, solid_capstyle="round")
        ax.scatter([r.gain_vs_baseline], [yi], s=80, color=c, edgecolor=SURFACE, lw=2, zorder=3)
        sig = "significant" if r.significant else "not significant"
        ax.text(r.ci_high + 0.03, yi, f"+{r.gain_vs_baseline:.2f} t/ha ({r.gain_pct:+.0f}%) · {sig}",
                va="center", fontsize=9.5, color=INK2)
    ax.axvline(0, color=MUTED, lw=1, ls="--")
    ax.set_yticks(y, g["label"])
    ax.set_xlim(min(-0.15, g["ci_low"].min() - 0.05), g["ci_high"].max() + 0.75)
    ax.set_xlabel("Extra yield over 50 kg/ha at V6 (t/ha)")
    title(ax, "Two strategies clearly beat the 50 kg/ha baseline",
          "Mixed-model estimates with 95% CI; Holm-adjusted significance")
    save(fig, path)


def per_environment_gains(per_env: pd.DataFrame, pooled: pd.DataFrame, path: Path) -> None:
    style()
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9), sharey=True)
    order = ["All (pooled)"] + config.MEGA_ENVIRONMENTS
    for ax, t in zip(axes, config.TREATMENTS[1:]):
        c = config.TREATMENT_COLORS[t]
        p = pooled.set_index("treatment").loc[t]
        rows = [(p.gain_vs_baseline, p.ci_low, p.ci_high)]
        for me in config.MEGA_ENVIRONMENTS:
            r = per_env[(per_env.meg_env == me) & (per_env.treatment == t)]
            rows.append(tuple(r[["gain_vs_baseline", "ci_low", "ci_high"]].iloc[0]) if len(r) else (np.nan,) * 3)
        y = np.arange(len(order))[::-1]
        for k, (yi, (est, lo, hi)) in enumerate(zip(y, rows)):
            ax.plot([lo, hi], [yi, yi], color=c, lw=3 if k == 0 else 2, solid_capstyle="round", alpha=1 if k == 0 else .8)
            ax.scatter([est], [yi], s=70 if k == 0 else 45, color=c if k == 0 else SURFACE, edgecolor=c, lw=2, zorder=3)
        ax.axvline(0, color=MUTED, lw=1, ls="--")
        ax.axhline(len(order) - 1.5, color=GRID, lw=1)
        ax.set_title(config.TREATMENT_LABELS[t], fontsize=10.5, loc="left")
        ax.set_xlabel("Gain vs 50 kg/ha (t/ha)")
        ax.set_yticks(y, order)
    fig.suptitle("Gains over the baseline in each mega-environment", x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.text(0.01, 0.9, "Filled point = pooled estimate (all plots); open points = separate model per environment, implausible yield excluded (95% CI)",
             color=INK2, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def residual_diagnostics(res: pd.DataFrame, path: Path) -> None:
    style()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    ok = ~res["flag_implausible_yield"]
    axes[0].scatter(res.loc[ok, "fitted"], res.loc[ok, "residual"], s=10, alpha=.45, color=config.PALETTE[0], lw=0)
    axes[0].scatter(res.loc[~ok, "fitted"], res.loc[~ok, "residual"], s=40, color=config.PALETTE[7], label="Implausible yield")
    axes[0].axhline(0, color=MUTED, ls="--", lw=1)
    axes[0].set_xlabel("Fitted yield (t/ha)"); axes[0].set_ylabel("Residual (t/ha)")
    axes[0].set_title("Residuals vs fitted", loc="left", fontsize=11)
    if (~ok).any():
        axes[0].legend(loc="upper left")
    osm, osr = stats.probplot(res["residual"], dist="norm", fit=False)
    axes[1].scatter(osm, np.sort(res["residual"]), s=10, alpha=.5, color=config.PALETTE[0], lw=0)
    lim = np.array([osm.min(), osm.max()])
    sd = res.loc[ok, "residual"].std()
    axes[1].plot(lim, lim * sd, color=MUTED, ls="--", lw=1)
    axes[1].set_xlabel("Theoretical quantile"); axes[1].set_ylabel("Residual (t/ha)")
    axes[1].set_title("Normal Q-Q", loc="left", fontsize=11)
    save(fig, path)


# --------------------------------------------------------------------------- prediction
def observed_vs_predicted(preds: pd.DataFrame, path: Path, model: str = "Random forest") -> None:
    style()
    p = preds[(preds["model"] == model)]
    ok = ~p["flag_implausible_yield"]
    fig, ax = plt.subplots(figsize=(6, 5.5))
    ax.scatter(p.loc[ok, "observed"], p.loc[ok, "predicted"], s=12, alpha=.45, color=config.PALETTE[0], lw=0)
    hi = p.loc[ok, ["observed", "predicted"]].to_numpy().max() * 1.05
    ax.plot([0, hi], [0, hi], color=MUTED, ls="--", lw=1)
    ax.set_xlim(0, hi); ax.set_ylim(0, hi)
    ax.set_xlabel("Observed yield (t/ha)"); ax.set_ylabel("Predicted yield (t/ha)")
    note = f"; 1 implausible plot (observed {p.loc[~ok, 'observed'].max():g}) off-scale" if (~ok).any() else ""
    title(ax, f"{model}: predictions for unseen fields", "Out-of-fold predictions, grouped 5-fold CV" + note)
    save(fig, path)


def prediction_errors(preds: pd.DataFrame, path: Path, model: str = "Random forest") -> None:
    style()
    p = preds[(preds["model"] == model) & ~preds["flag_implausible_yield"]]
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    ax.scatter(p["predicted"], p["error"], s=12, alpha=.45, color=config.PALETTE[0], lw=0)
    ax.axhline(0, color=MUTED, ls="--", lw=1)
    bins = pd.cut(p["predicted"], 8)
    trend = p.groupby(bins, observed=True)["error"].mean()
    ax.plot([b.mid for b in trend.index], trend.to_numpy(), color=config.PALETTE[1], lw=2, label="Mean error by bin")
    ax.set_xlabel("Predicted yield (t/ha)"); ax.set_ylabel("Error = predicted − observed (t/ha)")
    ax.legend(loc="upper left")
    title(ax, "Errors grow at the extremes", "The model pulls predictions toward the average yield")
    save(fig, path)


def driver_importance(imp: pd.DataFrame, path: Path, top: int = 12) -> None:
    style()
    d = imp.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.38 * len(d) + 1.5))
    colors = [config.PALETTE[0] if k else config.PALETTE[1] for k in d["known_before_planting"]]
    ax.barh(d["label"], d["importance_mae"], color=colors, height=0.6)
    ax.errorbar(d["importance_mae"], range(len(d)), xerr=d["fold_sd"], fmt="none", ecolor=MUTED, lw=1)
    ax.set_xlabel("Increase in prediction error when shuffled (MAE, t/ha)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=config.PALETTE[0], label="Known before planting"),
                       Patch(color=config.PALETTE[1], label="Recorded during the season")], loc="lower right")
    title(ax, "What drives yield in this trial?", "Permutation importance on held-out fields (mean ± SD across folds)")
    save(fig, path)


# --------------------------------------------------------------------------- economics
def vcr_by_scenario(econ: pd.DataFrame, path: Path) -> None:
    style()
    d = econ[econ["treatment"] != config.TREATMENTS[1]]
    scen = list(dict.fromkeys(d["scenario"]))
    fig, ax = plt.subplots(figsize=(9, 4))
    width = 0.36
    for k, t in enumerate(config.TREATMENTS[2:]):
        s = d[d["treatment"] == t].set_index("scenario").loc[scen]
        x = np.arange(len(scen)) + (k - 0.5) * width
        ax.bar(x, s["vcr"], width=width - 0.04, color=config.TREATMENT_COLORS[t], label=config.TREATMENT_LABELS[t])
        for xi, v in zip(x, s["vcr"]):
            ax.text(xi, v + 0.06, f"{v:.1f}", ha="center", fontsize=9, color=INK2)
    ax.axhline(config.VCR_THRESHOLD, color=MUTED, ls="--", lw=1)
    ax.text(0.5, config.VCR_THRESHOLD, f"VCR {config.VCR_THRESHOLD:g}\nadoption\nthreshold", ha="center", va="center",
            fontsize=8.5, color=MUTED, bbox=dict(facecolor=SURFACE, edgecolor="none", pad=2))
    ax.set_ylim(0, d["vcr"].max() * 1.25)
    ax.set_xticks(range(len(scen)), [s.replace(" (", "\n(") for s in scen], fontsize=9)
    ax.set_ylabel("Value-cost ratio")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    title(ax, "The extra 50 kg of urea pays for itself", "Value of extra maize ÷ cost of extra urea, per hectare")
    save(fig, path)
