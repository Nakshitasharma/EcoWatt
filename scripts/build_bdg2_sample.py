"""Rebuild the included, attributed BDG2 electricity meter subset.

Requires the BDG2 repository clone in data/bdg2_source. The app itself only
needs the compact derived CSV in data/bdg2_education_sample.csv.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "data/bdg2_source/data/meters/cleaned/electricity_cleaned.csv"
target = ROOT / "data/bdg2_education_sample.csv"
meter = "Panther_education_Teofila"
if not source.exists():
    raise SystemExit("Fetch BDG2 and place its cleaned electricity file at " + str(source))
frame = pd.read_csv(source, usecols=["timestamp", meter]).dropna(subset=[meter])
frame.columns = ["timestamp", "consumption_kwh"]
frame.to_csv(target, index=False)
print(f"Wrote {len(frame):,} measured hourly records to {target}")
