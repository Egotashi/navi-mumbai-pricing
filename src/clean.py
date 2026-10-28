"""Clean and consolidate public Navi Mumbai listings from three sources.

Sources (see data/SOURCES.md):
    makaan_2024      - 2024 Makaan listings: area, furnishing, age, bathrooms, lat/lon
    makaan_mmr       - MMR Makaan listings: construction status, new vs resale
    metro_amenities  - listings with 13 amenity flags (gym, pool, lift, ...)

Output: data/processed/listings.csv (one row per unique listing, common schema)
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

AMENITY_COLS = {
    "Gymnasium": "gym", "Lift Available": "lift", "CarParking": "parking",
    "Maintenance Staff": "maintenance_staff", "24x7 Security": "security",
    "Children's Play Area": "play_area", "Clubhouse": "clubhouse", "Intercom": "intercom",
    "Landscaped Gardens": "gardens", "Indoor Games": "indoor_games",
    "Gas Connection": "piped_gas", "Jogging Track": "jogging_track",
    "Swimming Pool": "pool",
}

COLUMNS = [
    "source", "node", "zone", "bhk", "area_sqft", "price_inr", "price_per_sqft",
    "property_type", "status", "sale_type", "age_years", "furnishing", "bathrooms",
    "lat", "lon", "amenity_count", *AMENITY_COLS.values(), "project",
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


def _load_makaan_mmr() -> pd.DataFrame:
    df = pd.read_csv(RAW / "makaan_mmr.csv")
    df["node"] = df["region"].map(map_node)
    df = df[df["node"].notna()].copy()
    mult = df["price_unit"].map({"L": 1e5, "Cr": 1e7})
    return pd.DataFrame({
        "source": "makaan_mmr",
        "node": df["node"],
        "bhk": df["bhk"],
        "area_sqft": df["area"],
        "price_inr": df["price"] * mult,
        "property_type": df["type"],
        "status": df["status"],
        "sale_type": df["age"].replace("Unknown", np.nan),
        "project": df["locality"].str.strip().str.lower(),
    })


def _load_metro_amenities() -> pd.DataFrame:
    df = pd.read_csv(RAW / "metro_amenities.csv", index_col=0)
    df["node"] = df["location"].map(map_node)
    df = df[df["node"].notna()].copy()
    flags = df[list(AMENITY_COLS)].rename(columns=AMENITY_COLS)
    out = pd.DataFrame({
        "source": "metro_amenities",
        "node": df["node"],
        "bhk": df["bhk"],
        "area_sqft": df["sqrt"],  # column is mislabelled in the raw file; values are sq ft
        "price_inr": df["price"],
        "sale_type": df["New/Resale"].map({1: "New", 0: "Resale"}),
    })
    out = pd.concat([out, flags], axis=1)
    out["amenity_count"] = flags.sum(axis=1, min_count=1)
    return out


def _clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    log = {"rows_in": len(df)}

    df = df.copy()
    for col in ["bhk", "area_sqft", "price_inr", "age_years", "bathrooms"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["bhk", "area_sqft", "price_inr"])
    log["after_drop_missing"] = len(df)

    # Residential flats only; plots, villas and independent houses price differently.
    keep_types = {"Apartment", "Studio Apartment", np.nan, None}
    df = df[df["property_type"].isin(keep_types) | df["property_type"].isna()]
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

    # De-duplicate within and across sources. Listings are reposted, and the
    # Makaan sources overlap, so match on node + bhk + area + price (rounded to
    # the nearest Rs 10k). Keep the richest source when duplicates collide.
    priority = {"makaan_2024": 0, "metro_amenities": 1, "makaan_mmr": 2}
    df["_prio"] = df["source"].map(priority)
    df["_key"] = (
        df["node"] + "|" + df["bhk"].astype(int).astype(str) + "|"
        + df["area_sqft"].round().astype(int).astype(str) + "|"
        + (df["price_inr"] / 1e4).round().astype(int).astype(str)
    )
    df = df.sort_values("_prio").drop_duplicates("_key", keep="first")
    log["after_dedup"] = len(df)

    df["zone"] = df["node"].map(ZONES)
    df["bhk"] = df["bhk"].astype(int)
    df = df.reindex(columns=COLUMNS).reset_index(drop=True)
    log["rows_out"] = len(df)
    return df, log


def build() -> tuple[pd.DataFrame, dict]:
    raw = pd.concat(
        [_load_makaan_2024(), _load_makaan_mmr(), _load_metro_amenities()],
        ignore_index=True,
    )
    raw_by_source = raw["source"].value_counts().to_dict()
    df, log = _clean(raw)
    log["raw_navi_mumbai_rows_by_source"] = raw_by_source
    log["clean_rows_by_source"] = df["source"].value_counts().to_dict()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "listings.csv", index=False)
    return df, log


if __name__ == "__main__":
    import json
    _, log = build()
    print(json.dumps(log, indent=2))
