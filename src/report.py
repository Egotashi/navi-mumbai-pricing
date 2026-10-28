"""Build the dashboard (dashboard/index.html) and the report figures (docs/figures/).

The dashboard is a single self-contained HTML file: listing-level data is
embedded as compact arrays so every filter recomputes the benchmarks in the
browser, with no server or network calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FIG = ROOT / "docs" / "figures"
DASH = ROOT / "dashboard"

ZONE_COLOR = {"North": "#2a78d6", "Central": "#eb6834", "South": "#1baf7a"}
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"


def dashboard_data(df: pd.DataFrame) -> dict:
    nodes = sorted(df["node"].unique())
    node_idx = {n: i for i, n in enumerate(nodes)}
    status_code = {"Ready to move": 1, "Under Construction": 2}
    rows = [
        [node_idx[r.node], int(r.bhk), int(round(r.area_sqft)), int(round(r.price_per_sqft)),
         status_code.get(r.status, 0)]
        for r in df.itertuples()
    ]
    metrics = json.loads((OUT / "model_metrics.json").read_text())
    premiums = pd.read_csv(OUT / "node_premiums_controlled.csv")
    fv = pd.read_csv(OUT / "fair_value_screen.csv")
    edges = np.arange(-0.6, 0.65, 0.05)
    hist, _ = np.histogram(fv["gap_pct"].clip(-0.6, 0.599), bins=edges)
    amen = pd.read_csv(OUT / "amenity_premiums.csv")
    return {
        "nodes": nodes,
        "zones": {n: z for n, z in df.groupby("node")["zone"].first().items()},
        "rows": rows,
        "premiums": premiums.round(4).to_dict(orient="records"),
        "metrics": metrics,
        "hedonic": json.loads((OUT / "hedonic_coefficients.json").read_text()),
        "fair_value_hist": {"edges": edges.round(2).tolist(), "counts": hist.tolist(),
                            "n": int(len(fv))},
        "amenities": amen.round(4).to_dict(orient="records"),
        "sources": df["source"].value_counts().to_dict(),
    }


def build_dashboard(data: dict) -> Path:
    template = (DASH / "template.html").read_text()
    payload = json.dumps(data, separators=(",", ":"))
    html = template.replace("/*__DATA__*/null", payload)
    out = DASH / "index.html"
    out.write_text(html)
    return out


def _style(ax):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def figures(df: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK})

    # 1. Median price per sq ft by node, with interquartile range.
    g = df.groupby("node").agg(
        n=("price_per_sqft", "size"), zone=("zone", "first"),
        p25=("price_per_sqft", lambda s: s.quantile(0.25)),
        med=("price_per_sqft", "median"),
        p75=("price_per_sqft", lambda s: s.quantile(0.75)),
    )
    g = g[g["n"] >= 30].sort_values("med")
    fig, ax = plt.subplots(figsize=(8, 6.2))
    y = np.arange(len(g))
    ax.barh(y, g["med"], height=0.55, color=[ZONE_COLOR[z] for z in g["zone"]])
    ax.hlines(y, g["p25"], g["p75"], color=INK, linewidth=1.2, alpha=0.55)
    ax.set_yticks(y, [f"{n}  (n={c:,})" for n, c in zip(g.index, g["n"])])
    for yi, v in zip(y, g["med"]):
        ax.text(v + 250, yi, f"₹{v:,.0f}", va="center", fontsize=8.5, color=INK)
    ax.set_xlabel("Asking price per sq ft (₹)  ·  bar = median, line = 25th–75th percentile",
                  color=MUTED, fontsize=9)
    _style(ax)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ZONE_COLOR.values()]
    ax.legend(handles, [f"{z} belt" for z in ZONE_COLOR], frameon=False, loc="lower right", fontsize=9)
    ax.set_title("Navi Mumbai asking rates by node", loc="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "node_benchmarks.png", dpi=160)
    plt.close(fig)

    # 2. Location premium after controlling for flat attributes.
    p = pd.read_csv(OUT / "node_premiums_controlled.csv").sort_values("premium_vs_kharghar")
    p = p[p["node"].isin(g.index)]
    fig, ax = plt.subplots(figsize=(8, 5.6))
    y = np.arange(len(p))
    colors = [ZONE_COLOR[df.loc[df.node == n, "zone"].iloc[0]] for n in p["node"]]
    ax.hlines(y, p["ci_low"] * 100, p["ci_high"] * 100, color=MUTED, linewidth=2)
    ax.scatter(p["premium_vs_kharghar"] * 100, y, s=46, color=colors, zorder=3,
               edgecolor="white", linewidth=1.5)
    ax.axvline(0, color="#c3c2b7", linewidth=1)
    ax.set_yticks(y, p["node"])
    ax.set_xlabel("Price premium vs Kharghar, same size, BHK, age and furnishing (%) · 95% CI",
                  color=MUTED, fontsize=9)
    _style(ax)
    ax.set_title("What location alone is worth", loc="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "location_premium.png", dpi=160)
    plt.close(fig)

    # 3. Amenity premiums.
    a = pd.read_csv(OUT / "amenity_premiums.csv").sort_values("premium")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    y = np.arange(len(a))
    sig = a["p_value"] < 0.05
    ax.hlines(y, a["ci_low"] * 100, a["ci_high"] * 100, color=MUTED, linewidth=2)
    ax.scatter(a["premium"] * 100, y, s=46, zorder=3, edgecolor="white", linewidth=1.5,
               color=np.where(sig, "#2a78d6", "#c3c2b7"))
    ax.axvline(0, color="#c3c2b7", linewidth=1)
    ax.set_yticks(y, a["amenity"].str.replace("_", " ").str.capitalize())
    ax.set_xlabel("Price premium holding size, BHK, node, new/resale fixed (%) · 95% CI · blue = p < 0.05",
                  color=MUTED, fontsize=9)
    _style(ax)
    ax.set_title("Amenities: individually small and noisy", loc="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "amenity_premiums.png", dpi=160)
    plt.close(fig)

    # 4. Model fit: out-of-fold predicted vs asking price.
    fv = pd.read_csv(OUT / "fair_value_screen.csv")
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(fv["model_value_inr"] / 1e5, fv["price_inr"] / 1e5, s=5, alpha=0.25, color="#2a78d6",
               linewidth=0)
    lim = [15, 600]
    ax.plot(lim, lim, color=INK, linewidth=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Model value, out-of-fold (₹ lakh)", color=MUTED, fontsize=9)
    ax.set_ylabel("Asking price (₹ lakh)", color=MUTED, fontsize=9)
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_title("Valuation model vs asking price", loc="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "model_fit.png", dpi=160)
    plt.close(fig)


def run(df: pd.DataFrame) -> Path:
    figures(df)
    data = dashboard_data(df)
    (OUT / "dashboard_data.json").write_text(json.dumps(data, separators=(",", ":")))
    return build_dashboard(data)


if __name__ == "__main__":
    print(run(pd.read_csv(ROOT / "data" / "processed" / "listings.csv")))
