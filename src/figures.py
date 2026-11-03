# make figures 2, 3, 4 for the paper
# run correction.py before this (fig 4 needs test_predictions.csv)
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import FIGURES, RESULTS, ensure_dirs, load_pairs

plt.rcParams.update({"font.size": 7, "axes.linewidth": 0.6, "font.family": "serif"})
W = 3.45  # IEEE column width, inches
RED, BLUE = "#c0392b", "#1f5fa8"


def fig2(d):
    x = d[d.hour.isin([6, 9]) & (d.timestamp_utc >= "2025-11-01")].copy()
    x["b"] = x.iot_temp - x.imd_temp
    fig, ax = plt.subplots(figsize=(W, 1.75), dpi=600)
    for h, c, mk in [(6, RED, "o"), (9, BLUE, "s")]:
        y = x[x.hour == h]
        ax.plot(y.timestamp_utc, y.b, marker=mk, ms=1.6, lw=0.6, c=c, label=f"{h:02d} UTC")
    ax.axvline(pd.Timestamp("2025-12-01"), c="grey", ls="--", lw=0.5)
    ax.axhline(0, c="k", lw=0.4)
    ax.set_ylabel("IoT $-$ IMD temperature (°C)")
    ax.legend(frameon=False, loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout(pad=0.3)
    fig.savefig(FIGURES / "fig2_radiation_error.png")


def fig3(s):
    fig, ax = plt.subplots(1, 2, figsize=(W, 1.8), dpi=600)
    for i, (ref, node, lab) in enumerate([("imd_temp", "iot_temp", "Temperature (°C)"),
                                          ("imd_p", "iot_p", "Pressure (hPa)")]):
        ax[i].scatter(s[ref], s[node], s=1.2, c=BLUE, alpha=0.45, lw=0)
        lo = min(s[ref].min(), s[node].min())
        hi = max(s[ref].max(), s[node].max())
        ax[i].plot([lo, hi], [lo, hi], "k--", lw=0.5)
        k, c = np.polyfit(s[ref], s[node], 1)
        xx = np.array([lo, hi])
        ax[i].plot(xx, k * xx + c, c=RED, lw=0.8)
        ax[i].set_xlabel("IMD " + lab)
        ax[i].set_ylabel("IoT " + lab)
        ax[i].set_title("(a)" if i == 0 else "(b)", loc="left", fontsize=7)
        sign = "+" if c >= 0 else "-"
        ax[i].text(0.04, 0.84, f"y = {k:.3f}x {sign} {abs(c):.2f}",
                   transform=ax[i].transAxes, fontsize=5.5)
    fig.tight_layout(pad=0.3, w_pad=0.8)
    fig.savefig(FIGURES / "fig3_scatter.png")


def fig4():
    t = pd.read_csv(RESULTS / "test_predictions.csv")
    fig, ax = plt.subplots(1, 2, figsize=(W, 1.85), dpi=600)
    for i, (var, ref, node, lab) in enumerate([("T", "imd_temp", "iot_temp", "Temperature bias (°C)"),
                                               ("RH", "imd_rh", "iot_rh", "RH bias (%)")]):
        g = pd.DataFrame({"a": t[node] - t[ref], "b": t[f"{var}_rolling"] - t[ref],
                          "h": t.hour}).groupby("h").mean()
        ax[i].plot(g.index, g.a, "o-", c=RED, lw=0.8, ms=2, label="Uncorrected")
        ax[i].plot(g.index, g.b, "s-", c=BLUE, lw=0.8, ms=2, label="Rolling correction")
        ax[i].axhline(0, c="grey", lw=0.4, ls="--")
        ax[i].set_xticks(range(0, 24, 6))
        ax[i].set_xlabel("Hour (UTC)")
        ax[i].set_ylabel(lab)
        ax[i].set_title("(a)" if i == 0 else "(b)", loc="left", fontsize=7)
    h, l = ax[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, frameon=False, fontsize=6, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(pad=0.3, w_pad=2.0, rect=(0, 0, 1, 0.9))
    fig.savefig(FIGURES / "fig4_correction.png")


def main():
    ensure_dirs()
    d = load_pairs()
    fig2(d)
    fig3(d[~d.contaminated])
    fig4()
    print("Figures written to", FIGURES)


if __name__ == "__main__":
    main()
