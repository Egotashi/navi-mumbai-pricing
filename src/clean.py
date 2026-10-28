"""Clean Navi Mumbai flat listings from the 2024 Makaan scrape.

Source (see data/SOURCES.md): makaan_2024.csv, Makaan.com listings scraped in
2024 for the Mumbai Metropolitan Region, with area, BHK, bathrooms, furnishing,
building age and coordinates.

Output: data/processed/listings.csv (one row per unique Navi Mumbai listing)
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# Canonical Navi Mumbai nodes (CIDCO nodes + Panvel belt). Order matters:
# longer names first so "Kopar Khairane" wins over a bare "Kopar".
NODES = {
    "Kopar Khairane": ["kopar khairane", "koparkhairane", "kopar khairne"],
    "CBD Belapur": ["cbd belapur", "belapur"],
    "Kharghar": ["kharghar"],
    "Vashi": ["vashi"],
    "Nerul": ["nerul"],
    "Sanpada": ["sanpada"],
    "Seawoods": ["seawoods", "sea woods"],
    "Juinagar": ["juinagar"],
    "Airoli": ["airoli"],
    "Ghansoli": ["ghansoli"],
    "Rabale": ["rabale"],
    "Ulwe": ["ulwe"],
    "Dronagiri": ["dronagiri"],
    "Kamothe": ["kamothe"],
    "Kalamboli": ["kalamboli"],
    "Karanjade": ["karanjade"],
    "Taloja": ["taloja"],
    "Panvel": ["panvel"],
}

# Rough zone grouping used in the report (north = Thane-Belapur belt,
# central = established CIDCO nodes, south = airport/Panvel growth belt).
ZONES = {
    "Airoli": "North", "Ghansoli": "North", "Rabale": "North", "Kopar Khairane": "North",
    "Vashi": "Central", "Sanpada": "Central", "Juinagar": "Central", "Nerul": "Central",
    "Seawoods": "Central", "CBD Belapur": "Central",
    "Kharghar": "South", "Kamothe": "South", "Kalamboli": "South", "Ulwe": "South",
    "Dronagiri": "South", "Taloja": "South", "Karanjade": "South", "Panvel": "South",
}

_NODE_PATTERNS = [
    (node, re.compile(r"\b(" + "|".join(map(re.escape, alts)) + r")\b", re.I))
    for node, alts in NODES.items()
]

COLUMNS = [
    "source", "node", "zone", "bhk", "area_sqft", "price_inr", "price_per_sqft",
    "property_type", "age_years", "furnishing", "bathrooms", "lat", "lon", "project",
]


def map_node(text: str) -> str | None:
    """Return the canonical node for a free-text locality, or None if not Navi Mumbai."""
    if not isinstance(text, str):
        return None
    for node, pat in _NODE_PATTERNS:
        if pat.search(text):
            return node
    return None


def _load_makaan_2024() -> pd.DataFrame:
    df = pd.read_csv(RAW / "makaan_2024.csv")
    df["node"] = df["locality"].map(map_node)
    df = df[df["node"].notna()].copy()
    return pd.DataFrame({
        "source": "makaan_2024",
        "node": df["node"],
        "bhk": df["bedroom_num"],
        "area_sqft": df["area"],
        "price_inr": df["price"],
        "property_type": df["property_type"],
        "age_years": df["age"],
        "furnishing": df["furnished"],
        "bathrooms": df["bathroom_num"],
        "lat": df["latitude"],
        "lon": df["longitude"],
        "project": df["title"].str.strip().str.lower(),
    })


def _clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    log = {"rows_in": len(df)}

    df = df.copy()
    for col in ["bhk", "area_sqft", "price_inr", "age_years", "bathrooms"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["bhk", "area_sqft", "price_inr", "bathrooms", "age_years"])
    log["after_drop_missing"] = len(df)

    # Residential flats only; plots, villas and independent houses price differently.
    df = df[df["property_type"].isin({"Apartment", "Studio Apartment"})]
    log["after_type_filter"] = len(df)

    # Plausibility bounds on size and size-per-bedroom.
    df = df[df["bhk"].between(1, 5) & df["area_sqft"].between(250, 4000)]
    df = df[(df["area_sqft"] / df["bhk"]).between(180, 1200)]
    log["after_size_bounds"] = len(df)

    df["price_per_sqft"] = df["price_inr"] / df["area_sqft"]

    # Within-node outlier trim on price per sq ft (robust: 3 * IQR on log scale).
    lp = np.log(df["price_per_sqft"])
    q1 = lp.groupby(df["node"]).transform(lambda s: s.quantile(0.25))
    q3 = lp.groupby(df["node"]).transform(lambda s: s.quantile(0.75))
    iqr = q3 - q1
    df = df[(lp >= q1 - 3 * iqr) & (lp <= q3 + 3 * iqr)]
    log["after_outlier_trim"] = len(df)

    # De-duplicate. The same flat is often listed several times (by different
    # brokers or reposted), so match on node + bhk + area + price rounded to
    # the nearest Rs 10k and keep the first.
    df["_key"] = (
        df["node"] + "|" + df["bhk"].astype(int).astype(str) + "|"
        + df["area_sqft"].round().astype(int).astype(str) + "|"
        + (df["price_inr"] / 1e4).round().astype(int).astype(str)
    )
    df = df.drop_duplicates("_key", keep="first")
    log["after_dedup"] = len(df)

    df["zone"] = df["node"].map(ZONES)
    df["bhk"] = df["bhk"].astype(int)
    df = df.reindex(columns=COLUMNS).reset_index(drop=True)
    log["rows_out"] = len(df)
    return df, log


def build() -> tuple[pd.DataFrame, dict]:
    df, log = _clean(_load_makaan_2024())
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "listings.csv", index=False)
    return df, log


if __name__ == "__main__":
    import json
    _, log = build()
    print(json.dumps(log, indent=2))
