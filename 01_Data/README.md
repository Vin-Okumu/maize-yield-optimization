# Data

The trial data belongs to Evergreen and is **confidential**. It is not stored in this repository.

| Folder | Contents | In git? |
|---|---|---|
| `raw/` | The three source files from Evergreen: `Field_Level.csv`, `Plot_Level.csv`, `Soil_PL.csv` | **No** (git-ignored) |
| `sample/` | **Synthetic** stand-ins with the same columns, formats and data-quality problems | Yes |
| `processed/` | Cleaned tables and `combined_dataset.csv` (one row per plot), written by `run_pipeline.py` | No |
| `external/` | CHIRPS rainfall and SoilGrids extracts written by `scripts/fetch_*.py` | No |
| `audit/` | [Data audit log](audit/data_audit_log.md): counts and decisions only, no records | Yes |

## Running with the real data

Copy the three source files into `01_Data/raw/`. The pipeline and notebooks detect them automatically and write results to `03_Report/`.

## Running without it

Everything runs on the synthetic sample:

```bash
python scripts/make_synthetic_data.py   # recreate the sample (already committed)
python run_pipeline.py --data sample    # results go to outputs_sample/ (git-ignored)
```

The sample was **generated, not derived from records**. It has new IDs, random coordinates around district centres, and yields simulated from a simple model. Its numbers will not match the published results.

See the [data dictionary](data_dictionary.md) for every column.
