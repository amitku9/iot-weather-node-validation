# validation stats (Table 1, Table 2, hourly bias, pressure check)
import json

import numpy as np
import pandas as pd

from common import RESULTS, ensure_dirs, load_pairs, stats

VARS = [("Temperature (degC)", "imd_temp", "iot_temp"),
        ("Relative humidity (%)", "imd_rh", "iot_rh"),
        ("Pressure (hPa)", "imd_p", "iot_p")]


NODE_LAT, NODE_LON = 26.856, 75.812


def partial_r(y, x, control):
    # partial correlation of y and x, removing control
    def resid(v):
        A = np.column_stack([np.ones(len(control)), control])
        return v - A @ np.linalg.lstsq(A, v, rcond=None)[0]
    return float(np.corrcoef(resid(np.asarray(y)), resid(np.asarray(x)))[0, 1])


def solar_elevation(ts, lat=NODE_LAT, lon=NODE_LON):
    # sun elevation angle (NOAA formula)
    g = 2 * np.pi / 365 * (ts.dayofyear - 1 + (ts.hour - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                    - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    ha = np.radians((ts.hour * 60 + ts.minute + eqt + 4 * lon) / 4 - 180)
    la = np.radians(lat)
    return float(np.degrees(np.arcsin(np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha))))


def main():
    ensure_dirs()
    d = load_pairs()
    s = d[~d.contaminated]
    out = {}

    # table 1
    rows = []
    for label, data in [("screened", s), ("all", d)]:
        for name, ref, node in VARS:
            st = stats(data[ref], data[node])
            rows.append({"variable": name, "dataset": label, **st, "R2": st["r"] ** 2})
    t1 = pd.DataFrame(rows)
    t1.round(3).to_csv(RESULTS / "table1_validation.csv", index=False)
    print("Table I\n", t1.round(3).to_string(index=False))

    # table 2 - monthly means
    g = s.groupby("month")
    t2 = pd.DataFrame({
        "n": g.size(),
        "node_T": g.iot_temp.mean(),
        "imd_T": g.imd_temp.mean(),
        "dT": g.iot_temp.mean() - g.imd_temp.mean(),
        "dRH": g.iot_rh.mean() - g.imd_rh.mean(),
        "dP": g.iot_p.mean() - g.imd_p.mean(),
    }).reindex([9, 10, 11, 12, 1])
    t2.round(2).to_csv(RESULTS / "table2_monthly.csv")
    print("\nTable II\n", t2.round(2).to_string())

    # bias by hour
    hb = pd.DataFrame({
        "T_bias": (s.iot_temp - s.imd_temp).groupby(s.hour).mean(),
        "RH_bias": (s.iot_rh - s.imd_rh).groupby(s.hour).mean(),
        "n": s.groupby("hour").size(),
    })
    hb.round(2).to_csv(RESULTS / "hourly_bias.csv")
    print("\nHourly bias (screened)\n", hb.round(2).to_string())

    # regression line
    k, c = np.polyfit(s.imd_temp, s.iot_temp, 1)
    out["temp_ols"] = {"slope": k, "intercept": c, "crosses_1to1_at": c / (1 - k)}

    # pressure bias - check against pressure level and die temp
    pb = s.iot_p - s.imd_p
    kp_level, _ = np.polyfit(s.imd_p, pb, 1)
    kp_temp, _ = np.polyfit(s.iot_bmp_t, pb, 1)
    out["pressure_bias"] = {
        "vs_pressure_level": {"slope_hPa_per_hPa": kp_level, "r": pb.corr(s.imd_p)},
        "vs_die_temp": {"slope_hPa_per_C": kp_temp, "r": pb.corr(s.iot_bmp_t)},
        "partial_r_die_temp_given_pressure": partial_r(pb, s.iot_bmp_t, s.imd_p),
        "partial_r_pressure_given_die_temp": partial_r(pb, s.imd_p, s.iot_bmp_t),
    }

    # sun angle around 1 Dec
    out["solar_elevation_deg"] = {
        t: {"06UTC": solar_elevation(pd.Timestamp(f"{t} 06:00")),
            "09UTC": solar_elevation(pd.Timestamp(f"{t} 09:00"))}
        for t in ["2025-11-01", "2025-11-30", "2025-12-01", "2025-12-21", "2026-01-15"]}

    # height correction for 21 m
    adj = d.imd_p * (np.exp(9.80665 * 21 / (287.05 * (d.imd_temp + 273.15))) - 1)
    out["hydrostatic_21m_hPa"] = {"mean": adj.mean(), "min": adj.min(), "max": adj.max()}

    # 06 UTC problem numbers
    res = d.iot_temp - d.imd_temp
    bmp = d.iot_bmp_t - d.imd_temp
    h6 = d.hour == 6
    out["radiation"] = {
        "pairs_excluded": int(d.contaminated.sum()),
        "dht22_06utc_mean": {m: res[h6 & (d.month == m)].mean() for m in [11, 12, 1]},
        "bmp280_06utc_mean": {m: bmp[h6 & (d.month == m)].mean() for m in [11, 12, 1]},
        "dec_06utc_days_over_2C": int((res[h6 & (d.month == 12)] > 2).sum()),
        "dec_06utc_days": int((h6 & (d.month == 12)).sum()),
        "max_contaminated_residual": res[d.contaminated].max(),
    }
    out["pairs"] = {"total": len(d), "screened": len(s)}

    with open(RESULTS / "validation_numbers.json", "w") as f:
        json.dump(out, f, indent=1, default=float)
    print("\n", json.dumps(out, indent=1, default=lambda x: round(float(x), 3)))


if __name__ == "__main__":
    main()
