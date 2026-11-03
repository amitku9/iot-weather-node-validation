# common functions - loading data, screening flag, error stats
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

PAIRS_CSV = DATA / "matched_pairs.csv"
CLOUD_XLSX = DATA / "cloud_okta_VIJP_2025-11_to_2026-01.xlsx"

# 06 UTC readings from 1 Dec are affected by sun heating -> excluded
SCREEN_START = pd.Timestamp("2025-12-01")
SCREEN_HOUR = 6

# train before this date, test after
TEST_START = pd.Timestamp("2025-12-01")


def load_pairs():
    # read matched pairs csv and rename columns
    try:
        raw = pd.read_csv(PAIRS_CSV, encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = pd.read_csv(PAIRS_CSV, encoding="cp1252")
    cols = {c: " ".join(str(c).split()) for c in raw.columns}
    raw = raw.rename(columns=cols)

    def col(prefix):
        hits = [c for c in raw.columns if c.startswith(prefix)]
        if len(hits) != 1:
            raise KeyError(f"Expected one column starting with {prefix!r}, found {hits}")
        return hits[0]

    ts = pd.to_datetime(
        raw["Year"].astype(str) + "-" + raw["Month"].astype(str) + "-"
        + raw["Date"].astype(str) + " " + raw["Time (GMT)"].astype(str)
    )
    d = pd.DataFrame({
        "timestamp_utc": ts,
        "iot_bmp_t": raw[col("Temperature BMP280")],
        "iot_p": raw[col("SLP (hPa) IoT")],
        "iot_temp": raw[col("Temperature DHT22")],
        "iot_rh": raw[col("Humidity (%) IoT")],
        "imd_p": raw[col("SLP (hpa) station")],
        "imd_temp": raw[col("Temperature station")],
        "imd_rh": raw[col("Humidity (%) station")],
    })
    d = d.sort_values("timestamp_utc").reset_index(drop=True)
    d["hour"] = d.timestamp_utc.dt.hour
    d["month"] = d.timestamp_utc.dt.month
    d["day"] = d.timestamp_utc.dt.normalize()
    d["contaminated"] = (d.timestamp_utc >= SCREEN_START) & (d.hour == SCREEN_HOUR)
    return d


def load_cloud():
    # read okta sheets (Nov, Dec, Jan)
    sheets = {"NOV 2025": (2025, 11), "DEC 2025": (2025, 12), "JAN 2026": (2026, 1)}
    rows = []
    for sheet, (y, m) in sheets.items():
        df = pd.read_excel(CLOUD_XLSX, sheet_name=sheet, header=None).iloc[3:34]
        ndays = pd.Timestamp(y, m, 1).days_in_month
        for _, r in df.iterrows():
            try:
                day = int(r[0])
            except (TypeError, ValueError):
                continue
            if day > ndays:
                continue
            for j, h in enumerate([0, 3, 6, 9, 12, 15, 18, 21], start=1):
                rows.append({"timestamp_utc": pd.Timestamp(y, m, day, h), "okta": r[j]})
    return pd.DataFrame(rows)


def stats(obs, pred):
    # MAE, RMSE, bias, r
    e = np.asarray(pred) - np.asarray(obs)
    return {
        "n": len(e),
        "MAE": float(np.mean(np.abs(e))),
        "RMSE": float(np.sqrt(np.mean(e ** 2))),
        "bias": float(np.mean(e)),
        "r": float(np.corrcoef(obs, pred)[0, 1]),
    }


def ensure_dirs():
    RESULTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)
