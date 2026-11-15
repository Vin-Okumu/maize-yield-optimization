"""Tests run on the synthetic sample, so they work on any machine.

    pytest -q
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maize import advisory, audit, config, data, prediction  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    src = data.load_sources("sample")
    cleaned, combined = data.build_combined("sample")
    return src, cleaned, combined


def test_integration_keeps_every_plot(prepared):
    src, _, combined = prepared
    assert len(combined) == len(src["plot"])
    assert combined["plot_id"].is_unique
    assert not any(c.startswith("_") for c in data.public_columns(combined))


def test_cleaning_flags_known_issues(prepared):
    _, cleaned, combined = prepared
    plot = cleaned["plot"]
    assert plot["flag_implausible_yield"].sum() == 1
    assert plot["flag_v10_date_missing"].sum() > 0
    assert (~combined["has_field_match"]).sum() > 0
    assert cleaned["field"]["flag_implausible_altitude"].sum() == 3
    assert set(plot["crop"].unique()) == {"maize"}


def test_audit_log_has_no_identifiers(prepared):
    src, cleaned, combined = prepared
    log = audit.run_audit(src, cleaned, combined)
    assert list(log.columns) == audit.COLUMNS
    assert log["issue_id"].is_unique
    text = log.to_csv()
    for block in src["field"]["block_id"].head(50):
        assert block not in text


def test_value_cost_ratio_arithmetic():
    gains = pd.DataFrame({"treatment": [config.RECOMMENDED], "label": ["D"],
                          "gain_vs_baseline": [0.5], "ci_low": [0.3], "ci_high": [0.7]})
    s = config.PriceScenario("test", urea_rwf_per_kg=500, maize_rwf_per_kg=250, source="-")
    row = advisory.value_cost(gains, [s]).iloc[0]
    # 500 kg extra maize x 250 RWF = 125,000; 50 kg urea x 500 RWF = 25,000
    assert row["vcr"] == pytest.approx(5.0)
    assert row["net_benefit_rwf_ha"] == pytest.approx(100_000)
    assert row["break_even_gain_tha"] == pytest.approx(0.1)


def test_grouped_cv_never_mixes_fields(prepared):
    _, _, combined = prepared
    metrics, preds = prediction.cross_validate(combined)
    assert set(metrics["model"]) == {"Mean baseline", "Ridge regression", "Random forest"}
    assert preds["predicted"].notna().all()
    rf = metrics.set_index("model").loc["Random forest", "MAE"]
    base = metrics.set_index("model").loc["Mean baseline", "MAE"]
    assert rf < base


def test_treatment_model_recovers_simulated_effect(prepared):
    pytest.importorskip("statsmodels")
    from maize import analysis
    _, _, combined = prepared
    df = data.analysis_frame(combined, drop_implausible=True)
    gains = analysis.treatment_effects(df)["gains"].set_index("treatment")
    # the synthetic data was simulated with a +0.55 t/ha effect for treatment D
    assert 0.35 < gains.loc[config.RECOMMENDED, "gain_vs_baseline"] < 0.75


def test_sample_contains_no_real_identifiers():
    raw_plot = config.RAW_DIR / "Plot_Level.csv"
    if not raw_plot.exists():
        pytest.skip("real data not present")
    real = set(pd.read_csv(raw_plot)["plot_id"])
    fake = set(pd.read_csv(config.SAMPLE_DIR / "Plot_Level.csv")["plot_id"])
    assert not real & fake
    real_xy = pd.read_csv(config.RAW_DIR / "Field_Level.csv")[["lat", "long"]].round(4)
    fake_xy = pd.read_csv(config.SAMPLE_DIR / "Field_Level.csv")[["lat", "long"]].round(4)
    assert real_xy.merge(fake_xy).empty
    assert np.isfinite(fake_xy.to_numpy()).all()
