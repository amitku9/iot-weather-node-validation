# cloud cover vs 06 UTC temperature difference
import pandas as pd

from common import RESULTS, ensure_dirs, load_cloud, load_pairs, stats


def main():
    ensure_dirs()
    d = load_pairs().merge(load_cloud(), on="timestamp_utc", how="left")
    d["resid"] = d.iot_temp - d.imd_temp
    d["sky"] = pd.cut(d.okta, [-1, 2, 5, 8], labels=["clear 0-2", "partly 3-5", "overcast 6-8"])

    x = d[d.month.isin([11, 12, 1]) & d.hour.isin([3, 6, 9, 12])]
    t = (x.groupby(["hour", "month", "sky"], observed=False).resid
         .agg(["mean", "count"]).round(2).reset_index())
    t.to_csv(RESULTS / "residual_by_sky.csv", index=False)
    print(t.to_string(index=False))

    # check: exclude only when cloud <= 5 okta
    alt = (d.timestamp_utc >= "2025-12-01") & (d.hour == 6) & ~(d.okta >= 6)
    rows = []
    for rule, mask in [("simple (paper)", d.contaminated), ("cloud-conditioned", alt)]:
        kept = d[~mask]
        for name, ref, node in [("T", "imd_temp", "iot_temp"), ("RH", "imd_rh", "iot_rh"),
                                ("P", "imd_p", "iot_p")]:
            rows.append({"rule": rule, "excluded": int(mask.sum()), "variable": name,
                         **stats(kept[ref], kept[node])})
    comp = pd.DataFrame(rows)
    comp.round(3).to_csv(RESULTS / "screening_rule_comparison.csv", index=False)
    print("\n", comp.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
