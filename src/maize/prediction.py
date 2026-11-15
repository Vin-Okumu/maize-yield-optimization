"""Yield prediction and yield-driver importance.

Two questions, two feature sets:

1. *Prediction* (Objective 3): can we predict yield for a new field before
   planting? Only information known at planting is used, and whole fields are
   held out in grouped cross-validation so the score reflects unseen fields.
2. *Drivers* (Objective 2a): which variables explain yield? Here management
   variables recorded during the season (e.g. germination rate) are allowed,
   and permutation importance is measured on held-out fields.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config

PREPLANT_CATEGORICAL = ["urea_rate_timing", "season", "meg_env", "landscape_pos", "slope_pos",
                        "soil_color", "rockness"]
PREPLANT_NUMERIC = ["lat", "long", "alt_clean", "soil_depth", "slope", "cult_land"]

DRIVER_CATEGORICAL = PREPLANT_CATEGORICAL + ["seed_variety", "compost_quality", "fert_rank"]
DRIVER_NUMERIC = ["alt_clean", "slope", "cult_land", "compost_tha", "seeds_kgha", "germination_rate",
                  "planting_doy_in_season", "pH"]
EXTERNAL_NUMERIC_PREFIXES = ("sg_", "rain_")

FRIENDLY = {
    "urea_rate_timing": "Urea treatment", "season": "Season", "meg_env": "Mega-environment",
    "landscape_pos": "Landscape position", "slope_pos": "Slope position", "soil_color": "Soil colour",
    "rockness": "Stoniness", "lat": "Latitude", "long": "Longitude", "alt_clean": "Altitude",
    "soil_depth": "Soil depth", "slope": "Slope", "cult_land": "Land cultivated by farmer",
    "seed_variety": "Seed variety", "compost_quality": "Compost quality", "fert_rank": "Farmer fertility rank",
    "compost_tha": "Compost rate", "seeds_kgha": "Seed rate", "germination_rate": "Germination rate",
    "planting_doy_in_season": "Planting date (days after first planting)", "pH": "Soil pH (measured)",
    "rain_plant_silking": "Rainfall planting→silking (CHIRPS)",
}


def _features(df: pd.DataFrame, categorical: list[str], numeric: list[str], external: bool):
    numeric = list(numeric)
    if external:
        numeric += [c for c in df.columns if c.startswith(EXTERNAL_NUMERIC_PREFIXES)]
    categorical = [c for c in categorical if c in df]
    numeric = [c for c in numeric if c in df and pd.to_numeric(df[c], errors="coerce").notna().any()]
    X = df[categorical + numeric].copy()
    for c in categorical:
        X[c] = X[c].astype("object").where(X[c].notna(), np.nan)
    if "soil_depth" in numeric:  # 'deep'/'shallow' in the source; numeric code keeps order
        X["soil_depth"] = X["soil_depth"].map({"shallow": 0, "deep": 1})
    for c in numeric:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    return X, categorical, numeric


def _pipeline(estimator, categorical, numeric) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median")),
                          ("scale", StandardScaler())]), numeric),
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
    ])
    return Pipeline([("pre", pre), ("model", estimator)])


def models() -> dict:
    return {
        "Mean baseline": DummyRegressor(strategy="mean"),
        "Ridge regression": Ridge(alpha=1.0),
        "Random forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                                               random_state=config.RANDOM_STATE, n_jobs=-1),
    }


def cross_validate(df: pd.DataFrame, drop_implausible: bool = False, external: bool = False):
    """Grouped 5-fold CV (whole fields held out). Returns (metrics, out-of-fold predictions)."""
    data = df[df["block_id"].notna()].copy()
    if drop_implausible:
        data = data[~data["flag_implausible_yield"]]
    data = data.reset_index(drop=True)
    X, cat, num = _features(data, PREPLANT_CATEGORICAL, PREPLANT_NUMERIC, external)
    y, groups = data["yield_tha"], data["block_id"]
    cv = GroupKFold(n_splits=config.CV_FOLDS)

    metrics, preds = [], []
    for name, est in models().items():
        oof = np.full(len(data), np.nan)
        for tr, te in cv.split(X, y, groups):
            pipe = _pipeline(est, cat, num).fit(X.iloc[tr], y.iloc[tr])
            oof[te] = pipe.predict(X.iloc[te])
        metrics.append({"model": name, "MAE": mean_absolute_error(y, oof),
                        "RMSE": float(np.sqrt(mean_squared_error(y, oof))), "R2": r2_score(y, oof),
                        "n_plots": len(data), "outlier_excluded": drop_implausible})
        preds.append(pd.DataFrame({"model": name, "observed": y, "predicted": oof,
                                   "season": data["season"], "meg_env": data["meg_env"],
                                   "flag_implausible_yield": data["flag_implausible_yield"]}))
    metrics = pd.DataFrame(metrics).sort_values("RMSE").reset_index(drop=True)
    preds = pd.concat(preds, ignore_index=True)
    preds["error"] = preds["predicted"] - preds["observed"]
    return metrics, preds


def error_by_group(preds: pd.DataFrame, model: str = "Random forest") -> pd.DataFrame:
    p = preds[preds["model"] == model]
    return (p.groupby(["meg_env"], dropna=False)
             .agg(n=("error", "size"), MAE=("error", lambda e: e.abs().mean()),
                  mean_error=("error", "mean"))
             .reset_index())


def driver_importance(df: pd.DataFrame, external: bool = True, n_repeats: int = 10) -> pd.DataFrame:
    """Permutation importance of each original variable, measured on held-out fields.

    Importance = increase in MAE (t/ha) when the variable is shuffled. The
    implausible yield is excluded so one plot does not dominate the scores.
    """
    data = df[df["block_id"].notna() & ~df["flag_implausible_yield"]].reset_index(drop=True)
    X, cat, num = _features(data, DRIVER_CATEGORICAL, DRIVER_NUMERIC, external)
    y, groups = data["yield_tha"], data["block_id"]
    rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                               random_state=config.RANDOM_STATE, n_jobs=-1)
    scores = []
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=config.CV_FOLDS).split(X, y, groups)):
        pipe = _pipeline(rf, cat, num).fit(X.iloc[tr], y.iloc[tr])
        res = permutation_importance(pipe, X.iloc[te], y.iloc[te], scoring="neg_mean_absolute_error",
                                     n_repeats=n_repeats, random_state=config.RANDOM_STATE + fold, n_jobs=-1)
        scores.append(pd.Series(res.importances_mean, index=X.columns))
    imp = pd.concat(scores, axis=1)
    out = pd.DataFrame({
        "variable": imp.index,
        "importance_mae": imp.mean(axis=1).to_numpy(),
        "fold_sd": imp.std(axis=1).to_numpy(),
        "known_before_planting": [c in PREPLANT_CATEGORICAL + PREPLANT_NUMERIC for c in imp.index],
        "share_missing": [float(X[c].isna().mean()) for c in imp.index],
    })
    out["label"] = out["variable"].map(FRIENDLY).fillna(out["variable"])
    return out.sort_values("importance_mae", ascending=False).reset_index(drop=True)
