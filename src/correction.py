# correction models - train Sep-Nov, test Dec-Jan
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from common import RESULTS, TEST_START, ensure_dirs, load_pairs

SEED = 42
WINDOW_DAYS = 14
N_BOOT = 2000
FEATURES = ["iot_temp", "iot_rh", "hsin", "hcos"]


def day_block_ci(y, raw, pred, days, rng):
    # bootstrap CI, resample full days
    df = pd.DataFrame({"y": y, "a": raw, "b": pred, "d": days})
    groups = []
    for day, g in df.groupby("d"):
        groups.append(g)
    reductions = []
    for _ in range(N_BOOT):
        s = pd.concat([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        reductions.append((s.a - s.y).abs().mean() - (s.b - s.y).abs().mean())
    return np.percentile(reductions, [2.5, 97.5])


def rolling_predict(full, test, target):
    preds = []
    for day, g in test.groupby("day"):
        w = full[(full.day < day) & (full.day >= day - pd.Timedelta(days=WINDOW_DAYS))]
        m = LinearRegression().fit(w[FEATURES], w[target])
        preds.append(pd.Series(m.predict(g[FEATURES]), index=g.index))
    return pd.concat(preds).loc[test.index]


def main():
    ensure_dirs()
    rng = np.random.default_rng(SEED)
    rng_rf = np.random.default_rng(SEED + 1)
    d = load_pairs()
    d = d[~d.contaminated].copy()
    d["hsin"] = np.sin(2 * np.pi * d.hour / 24)
    d["hcos"] = np.cos(2 * np.pi * d.hour / 24)
    train, test = d[d.timestamp_utc < TEST_START], d[d.timestamp_utc >= TEST_START]
    print(f"train n={len(train)}  test n={len(test)}  test days={test.day.nunique()}")

    rows, extras, keep = [], {}, test[["timestamp_utc", "hour", "imd_temp", "iot_temp",
                                       "imd_rh", "iot_rh"]].copy()
    for var, target, raw in [("T", "imd_temp", "iot_temp"), ("RH", "imd_rh", "iot_rh")]:
        y, base = test[target], test[raw]
        static = LinearRegression().fit(train[[raw]], train[target])
        rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                                   random_state=SEED, n_jobs=-1).fit(train[FEATURES], train[target])
        cand = {
            "None": base,
            "Offset (Sep-Nov)": base - (train[raw] - train[target]).mean(),
            "Linear, static": pd.Series(static.predict(test[[raw]]), index=test.index),
            "Linear, rolling 14-day": rolling_predict(d, test, target),
            "Random forest": pd.Series(rf.predict(test[FEATURES]), index=test.index),
        }
        keep[f"{var}_rolling"] = cand["Linear, rolling 14-day"]
        base_mae = (base - y).abs().mean()
        for name, p in cand.items():
            e = p - y
            # separate rng for RF
            gen = rng_rf if name == "Random forest" else rng
            lo, hi = (np.nan, np.nan) if name == "None" else \
                day_block_ci(y.values, base.values, p.values, test.day.values, gen)
            rows.append({"variable": var, "strategy": name, "MAE": e.abs().mean(),
                         "RMSE": np.sqrt((e ** 2).mean()), "bias": e.mean(),
                         "dMAE_pct": 100 * (e.abs().mean() - base_mae) / base_mae,
                         "reduction_CI_low": lo, "reduction_CI_high": hi})
        extras[f"{var}_static_model"] = {"slope": float(static.coef_[0]),
                                         "intercept": float(static.intercept_)}

    extras["test_below_train_min_pct"] = float(100 * (test.iot_temp < train.iot_temp.min()).mean())
    t3 = pd.DataFrame(rows)
    t3.round(3).to_csv(RESULTS / "table3_correction.csv", index=False)
    keep.to_csv(RESULTS / "test_predictions.csv", index=False)
    with open(RESULTS / "correction_extras.json", "w") as f:
        json.dump(extras, f, indent=1)
    print(t3.round(3).to_string(index=False))
    print(json.dumps(extras, indent=1))


if __name__ == "__main__":
    main()
