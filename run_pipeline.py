"""Run the full analysis end to end.

    python run_pipeline.py                 # real data if 01_Data/raw/ has the files, else the synthetic sample
    python run_pipeline.py --data sample   # force the synthetic sample (outputs go to outputs_sample/)
    python run_pipeline.py --fast          # skip the slow permutation-importance step

Steps: prepare data -> audit log -> treatment effects -> per-environment results
-> prediction -> yield drivers -> economics & decision tool -> maps -> figures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evergreen maize-Urea trial analysis pipeline")
    parser.add_argument("--data", choices=["raw", "sample"], help="data source (default: auto)")
    parser.add_argument("--fast", action="store_true", help="skip permutation importance")
    args = parser.parse_args()
    if args.data:
        os.environ["MAIZE_DATA"] = args.data

    from maize import advisory, analysis, audit, config, data, mapping, plotting, prediction

    mode = config.data_mode()
    out = config.output_paths(mode)
    label = "confidential trial data" if mode == "raw" else "synthetic sample data"
    t0 = time.time()

    def step(msg: str) -> None:
        print(f"[{time.time() - t0:5.1f}s] {msg}", flush=True)

    step(f"Data source: {label} ({data.source_dir(mode).relative_to(ROOT)})")

    # 1. Prepare -----------------------------------------------------------------
    src = data.load_sources(mode)
    cleaned, combined = data.build_combined(mode)
    cleaned["field"].to_csv(out.processed / "field_clean.csv", index=False)
    cleaned["plot"].to_csv(out.processed / "plot_clean.csv", index=False)
    cleaned["soil"].to_csv(out.processed / "soil_clean.csv", index=False)
    combined[data.public_columns(combined)].to_csv(out.processed / "combined_dataset.csv", index=False)
    data.sanity_summary(combined).to_csv(out.tables / "combined_dataset_checks.csv", index=False)
    step(f"Combined dataset: {combined.shape[0]} plots x {combined.shape[1]} columns")

    # 2. Audit ---------------------------------------------------------------------
    log = audit.run_audit(src, cleaned, combined)
    audit.write_audit_log(log, out.audit, label)
    plotting.missingness_by_season(src["field"], src["plot"], out.figures / "missingness_by_season.png")
    step(f"Audit log: {len(log)} checks")

    # 3. Treatment effects -------------------------------------------------------------
    df = data.analysis_frame(combined)
    te = analysis.treatment_effects(df)
    te["adjusted_means"].to_csv(out.tables / "adjusted_means.csv", index=False)
    te["pairwise"].to_csv(out.tables / "pairwise_comparisons.csv", index=False)
    te["gains"].to_csv(out.tables / "gains_vs_baseline.csv", index=False)
    te["variance"].to_csv(out.tables / "variance_components.csv", index=False)
    interactions = [analysis.interaction_test(df, "meg_env"), analysis.interaction_test(df, "season")]
    import pandas as pd
    pd.DataFrame(interactions).to_csv(out.tables / "interaction_tests.csv", index=False)
    sens = analysis.outlier_sensitivity(df)
    sens.to_csv(out.tables / "outlier_sensitivity.csv", index=False)
    drivers_lmm = analysis.agronomic_drivers(df)
    drivers_lmm.to_csv(out.tables / "agronomic_drivers_mixed_model.csv", index=False)
    step("Treatment-effect models done")

    per_env = analysis.per_environment(df)
    per_env.to_csv(out.tables / "per_environment_effects.csv", index=False)
    per_env_x = analysis.per_environment(df[~df["flag_implausible_yield"]].copy())
    per_env_x.to_csv(out.tables / "per_environment_effects_excl_implausible.csv", index=False)
    step("Per-environment models done")

    # 4. Prediction & drivers ------------------------------------------------------------
    metrics, preds = prediction.cross_validate(combined)
    metrics_x, preds_x = prediction.cross_validate(combined, drop_implausible=True)
    pd.concat([metrics, metrics_x]).to_csv(out.tables / "model_comparison.csv", index=False)
    prediction.error_by_group(preds).to_csv(out.tables / "prediction_error_by_environment.csv", index=False)
    step("Prediction models done")
    imp = None
    if not args.fast:
        imp = prediction.driver_importance(combined)
        imp.to_csv(out.tables / "driver_importance.csv", index=False)
        step("Driver importance done")

    # 5. Economics & decision support ---------------------------------------------------------
    econ = advisory.value_cost(te["gains"])
    econ.to_csv(out.tables / "economics_value_cost.csv", index=False)
    d_gain = te["gains"].set_index("treatment").loc[config.RECOMMENDED, "gain_vs_baseline"]
    advisory.break_even_curve(d_gain).to_csv(out.tables / "economics_vcr_grid.csv", index=False)
    decision = advisory.decision_table(te["gains"], per_env_x, interactions)
    decision.to_csv(out.tables / "decision_table.csv", index=False)
    advisory.write_decision_tool(per_env_x, te["gains"], interactions, out.tools / "index.html", label)
    step("Economics and decision tool done")

    # 6. Maps -----------------------------------------------------------------------------
    mapping.interactive_map(combined, out.maps / "trial_fields_map.html", precision=2)
    mapping.static_map(combined, out.figures / "trial_fields_map.png", precision=2)
    if mode == "raw":  # exact-location map stays local (git-ignored)
        mapping.interactive_map(combined, out.processed / "trial_fields_map_exact.html", precision=None)

    # 7. Figures ----------------------------------------------------------------------------
    plotting.yield_by_treatment(df, out.figures / "yield_by_treatment.png")
    plotting.yield_by_treatment_season(df, out.figures / "yield_by_treatment_and_season.png")
    plotting.treatment_gains(te["gains"], out.figures / "treatment_gains_vs_baseline.png")
    plotting.per_environment_gains(per_env_x, te["gains"], out.figures / "per_environment_gains.png")
    plotting.residual_diagnostics(analysis.residual_frame(df), out.figures / "residual_diagnostics.png")
    plotting.observed_vs_predicted(preds, out.figures / "rf_observed_vs_predicted.png")
    plotting.prediction_errors(preds, out.figures / "rf_prediction_errors.png")
    plotting.vcr_by_scenario(econ, out.figures / "value_cost_ratio.png")
    if imp is not None:
        plotting.driver_importance(imp, out.figures / "driver_importance.png")
    step("Figures saved")

    # 8. Headline numbers (used by the README / report) ---------------------------------------------
    g = te["gains"].set_index("treatment")
    m = te["adjusted_means"].set_index("treatment")
    summary = {
        "data": label,
        "plots": int(len(combined)), "plots_in_model": te["n_obs"], "field_seasons_in_model": te["n_groups"],
        "adjusted_means": m["adjusted_mean"].round(3).to_dict(),
        "gains": g[["gain_vs_baseline", "ci_low", "ci_high", "gain_pct", "p_holm"]].round(4).to_dict("index"),
        "c_vs_d_p_holm": float(te["pairwise"].query(
            "treatment_a == 'Urea 1kg/Are(V6 + V10)' and treatment_b == 'Urea 1kg/Are(V6)'")["p_holm"].iloc[0]),
        "interactions": {i["interaction"]: round(float(i["p_value"]), 4) for i in interactions},
        "model_comparison": metrics.round(3).to_dict("records"),
        "model_comparison_excl_implausible": metrics_x.round(3).to_dict("records"),
        "economics": econ[econ["treatment"] == config.RECOMMENDED][["scenario", "vcr", "net_benefit_rwf_ha"]]
        .round(2).to_dict("records"),
    }
    (out.tables / "headline_results.json").write_text(json.dumps(summary, indent=2, default=float))
    step(f"Done. Outputs in {out.figures.parent.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
