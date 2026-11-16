"""Project paths, treatment definitions and analysis settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "01_Data"
RAW_DIR = DATA_DIR / "raw"            # real trial data: local only, never committed
SAMPLE_DIR = DATA_DIR / "sample"      # synthetic stand-in committed to the repo
EXTERNAL_DIR = DATA_DIR / "external"  # CHIRPS / SoilGrids extracts (local only)
SOURCE_FILES = ("Field_Level.csv", "Plot_Level.csv", "Soil_PL.csv")

ORGANIZATION = "Evergreen"

# Treatments in analysis order; the 50 kg/ha treatment is the reference level.
TREATMENTS = [
    "Urea 0.5Kg/Are(V6)",
    "Urea1kg/Are(Planting+V6)",
    "Urea 1kg/Are(V6 + V10)",
    "Urea 1kg/Are(V6)",
]
BASELINE = TREATMENTS[0]
RECOMMENDED = "Urea 1kg/Are(V6)"

TREATMENT_LABELS = {
    "Urea 0.5Kg/Are(V6)": "A: 50 kg/ha, all at V6",
    "Urea1kg/Are(Planting+V6)": "B: 100 kg/ha, planting + V6",
    "Urea 1kg/Are(V6 + V10)": "C: 100 kg/ha, V6 + V10",
    "Urea 1kg/Are(V6)": "D: 100 kg/ha, all at V6",
}
SHORT_LABELS = {
    "Urea 0.5Kg/Are(V6)": "A · 50 kg V6",
    "Urea1kg/Are(Planting+V6)": "B · 100 kg Plant+V6",
    "Urea 1kg/Are(V6 + V10)": "C · 100 kg V6+V10",
    "Urea 1kg/Are(V6)": "D · 100 kg V6",
}
# Extra urea (kg/ha) each treatment uses compared with the 50 kg/ha baseline
EXTRA_UREA_KGHA = {t: (0 if t == BASELINE else 50) for t in TREATMENTS}

SEASONS = ["21A", "22A", "22B"]
MEGA_ENVIRONMENTS = ["Highlands", "Low-Mid-Dry", "Low-Mid-Wet", "Transitional"]

DATE_COLUMNS = [
    "planting_date", "germ_count_date", "urea_V6_date", "urea_V10_date",
    "silking_date", "R3_date", "harvest_date",
]

# Yield above this is treated as a probable entry error in sensitivity checks.
# Real maize yields in Rwanda rarely exceed ~12 t/ha.
IMPLAUSIBLE_YIELD_THA = 20.0
IMPLAUSIBLE_ALTITUDE_M = 900.0  # Rwanda's lowest point is about 950 m

RANDOM_STATE = 42
CV_FOLDS = 5

# Colour slots (validated categorical palette, fixed order)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TREATMENT_COLORS = dict(zip(TREATMENTS, PALETTE[:4]))
SEASON_COLORS = dict(zip(SEASONS, PALETTE[:3]))


@dataclass(frozen=True)
class PriceScenario:
    """Prices used for the value-cost ratio (VCR) analysis, in Rwandan francs (RWF)."""
    name: str
    urea_rwf_per_kg: float
    maize_rwf_per_kg: float
    source: str


PRICE_SCENARIOS = [
    PriceScenario(
        "Trial period, subsidised urea (2022)", 754, 237,
        "Urea farmer price RWF 754/kg after subsidy (AGRA Price & Policy Monitor, Aug 2022); "
        "maize farm-gate floor RWF 237/kg (MINICOM, Feb 2022)",
    ),
    PriceScenario(
        "Trial period, unsubsidised urea (2022)", 1257, 237,
        "Urea market price RWF 1,257/kg before subsidy (AGRA, Aug 2022); maize RWF 237/kg",
    ),
    PriceScenario(
        "Current, subsidised urea (2026)", 1090, 400,
        "Urea farmer price RWF 1,090/kg after 45% subsidy (New Times, Jul 2026); "
        "maize farm-gate minimum RWF 400/kg (MINICOM, 2024)",
    ),
]
VCR_THRESHOLD = 2.0  # common rule of thumb for smallholder adoption


def data_mode() -> str:
    """Return 'raw' when the real data is present locally, otherwise 'sample'.

    Override with the environment variable MAIZE_DATA=raw|sample.
    """
    forced = os.environ.get("MAIZE_DATA", "").strip().lower()
    if forced in {"raw", "sample"}:
        return forced
    return "raw" if all((RAW_DIR / f).exists() for f in SOURCE_FILES) else "sample"


@dataclass(frozen=True)
class OutputPaths:
    processed: Path
    audit: Path
    figures: Path
    tables: Path
    maps: Path
    tools: Path

    def make(self) -> "OutputPaths":
        for p in (self.processed, self.audit, self.figures, self.tables, self.maps, self.tools):
            p.mkdir(parents=True, exist_ok=True)
        return self


def output_paths(mode: str | None = None) -> OutputPaths:
    """Results always go to the repository's report folders, whichever data source is used.

    The published results come from the synthetic sample. Anyone running with the confidential
    data in 01_Data/raw/ will overwrite them with real-data results, so don't commit those.
    """
    return OutputPaths(
        processed=DATA_DIR / "processed",
        audit=DATA_DIR / "audit",
        figures=ROOT / "03_Report" / "figures",
        tables=ROOT / "03_Report" / "tables",
        maps=ROOT / "03_Report" / "maps",
        tools=ROOT / "03_Report" / "decision_tool",
    ).make()
