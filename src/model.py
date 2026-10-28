"""Valuation models for Navi Mumbai flats.

1. Valuation model (makaan_2024 rows: richest attributes)
   Target: log(price). Two models compared with project-grouped 5-fold CV, so
   listings from the same building never sit in both train and test folds:
     - Hedonic log-linear regression with node fixed effects (interpretable)
     - Histogram gradient boosting (non-linear, uses lat/lon)
2. Amenity premiums (metro_amenities rows: the only source with amenity flags)
   OLS of log(price) on size, BHK, new/resale, node fixed effects and the 13
   amenity flags, with heteroskedasticity-robust (HC3) standard errors.
3. Fair-value screen: out-of-fold predictions from the better model are
   compared with asking prices to flag listings priced well above or below
   comparable stock.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

NUM = ["log_area", "bhk", "bathrooms", "age_years"]
CAT = ["node", "furnishing"]
AMENITIES = [
    "gym", "lift", "parking", "maintenance_staff", "security", "play_area", "clubhouse",
    "intercom", "gardens", "indoor_games", "piped_gas", "jogging_track", "pool",
]
FAIR_VALUE_BAND = 0.25  # flag listings more than 25% from model value (~ the 75th pct error)


def _metrics(y_log: np.ndarray, pred_log: np.ndarray) -> dict:
    y, p = np.exp(y_log), np.exp(pred_log)
    ape = np.abs(p - y) / y
    ss_res = np.sum((y_log - pred_log) ** 2)
    ss_tot = np.sum((y_log - y_log.mean()) ** 2)
    return {
        "r2_log_price": round(float(1 - ss_res / ss_tot), 4),
        "mape": round(float(ape.mean()), 4),
        "median_ape": round(float(np.median(ape)), 4),
        "within_10pct": round(float((ape <= 0.10).mean()), 4),
        "within_20pct": round(float((ape <= 0.20).mean()), 4),
    }


def _hedonic() -> Pipeline:
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), CAT),
    ])
    return Pipeline([("pre", pre), ("reg", RidgeCV(alphas=np.logspace(-3, 2, 20)))])


def _boosting() -> Pipeline:
    pre = ColumnTransformer([
        ("num", "passthrough", NUM + ["lat", "lon"]),
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CAT),
    ])
    n_num = len(NUM) + 2
    reg = HistGradientBoostingRegressor(
        max_iter=600, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=25,
        l2_regularization=1.0,
        categorical_features=[n_num, n_num + 1], random_state=42,
    )
    return Pipeline([("pre", pre), ("reg", reg)])


def valuation(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    d = df[df["source"] == "makaan_2024"].dropna(subset=["bathrooms", "age_years"]).copy()
    d["log_area"] = np.log(d["area_sqft"])
    d["furnishing"] = d["furnishing"].fillna("Unknown")
    y = np.log(d["price_inr"].to_numpy())
    groups = d["project"].fillna("unknown").to_numpy()

    cv = GroupKFold(n_splits=5)
    results, oof = {}, {}
    for name, make in [("hedonic_ridge", _hedonic), ("gradient_boosting", _boosting)]:
        pred = np.zeros(len(d))
        fold_scores = []
        for tr, te in cv.split(d, y, groups):
            model = make().fit(d.iloc[tr], y[tr])
            pred[te] = model.predict(d.iloc[te])
            fold_scores.append(_metrics(y[te], pred[te])["r2_log_price"])
        m = _metrics(y, pred)
        m["r2_fold_std"] = round(float(np.std(fold_scores)), 4)
        results[name] = m
        oof[name] = pred

    # Naive baseline: node median price-per-sqft x area (what a broker's rule of thumb does).
    base = np.zeros(len(d))
    for tr, te in cv.split(d, y, groups):
        ppsf = d.iloc[tr].groupby("node")["price_per_sqft"].median()
        fallback = d.iloc[tr]["price_per_sqft"].median()
        rate = d.iloc[te]["node"].map(ppsf).fillna(fallback)
        base[te] = np.log(rate.to_numpy() * d.iloc[te]["area_sqft"].to_numpy())
    results["baseline_node_median_ppsf"] = _metrics(y, base)

    best = max(["hedonic_ridge", "gradient_boosting"], key=lambda k: results[k]["r2_log_price"])
    results["selected_model"] = best
    results["n_listings"] = int(len(d))
    results["n_projects"] = int(pd.Series(groups).nunique())

    # Interpretable effects from the hedonic model fit on all data (unscaled OLS).
    ols = smf.ols(
        "np.log(price_inr) ~ np.log(area_sqft) + bhk + bathrooms + age_years"
        " + C(furnishing, Treatment('Unfurnished')) + C(node, Treatment('Kharghar'))",
        data=d,
    ).fit(cov_type="HC3")
    results["hedonic_elasticity_area"] = round(float(ols.params["np.log(area_sqft)"]), 3)
    results["hedonic_age_effect_per_year"] = round(float(np.exp(ols.params["age_years"]) - 1), 4)
    results["hedonic_r2_in_sample"] = round(float(ols.rsquared), 4)

    # Export the hedonic coefficients so the dashboard can run a quick estimate
    # in the browser. Residual spread gives the estimate's typical range.
    coef = {"intercept": ols.params["Intercept"], "log_area": ols.params["np.log(area_sqft)"],
            "bhk": ols.params["bhk"], "bathrooms": ols.params["bathrooms"],
            "age_years": ols.params["age_years"], "node": {"Kharghar": 0.0},
            "furnishing": {"Unfurnished": 0.0}}
    for k, v in ols.params.items():
        if k.startswith("C(node"):
            coef["node"][k.split("[T.")[1].rstrip("]")] = v
        elif k.startswith("C(furnishing"):
            coef["furnishing"][k.split("[T.")[1].rstrip("]")] = v
    resid = ols.resid
    coef["resid_p25"], coef["resid_p75"] = float(resid.quantile(0.25)), float(resid.quantile(0.75))
    (OUT / "hedonic_coefficients.json").write_text(json.dumps(coef, indent=2, default=float))

    node_effects = []
    for k, v in ols.params.items():
        if k.startswith("C(node"):
            node = k.split("[T.")[1].rstrip("]")
            lo, hi = ols.conf_int().loc[k]
            node_effects.append({"node": node, "premium_vs_kharghar": np.exp(v) - 1,
                                 "ci_low": np.exp(lo) - 1, "ci_high": np.exp(hi) - 1})
    node_effects.append({"node": "Kharghar", "premium_vs_kharghar": 0.0, "ci_low": 0.0, "ci_high": 0.0})
    node_effects = pd.DataFrame(node_effects).sort_values("premium_vs_kharghar", ascending=False)
    node_effects.to_csv(OUT / "node_premiums_controlled.csv", index=False)

    fv = d[["node", "project", "bhk", "area_sqft", "price_inr", "price_per_sqft"]].copy()
    fv["model_value_inr"] = np.exp(oof[best])
    fv["gap_pct"] = fv["price_inr"] / fv["model_value_inr"] - 1
    fv["flag"] = np.select(
        [fv["gap_pct"] > FAIR_VALUE_BAND, fv["gap_pct"] < -FAIR_VALUE_BAND],
        ["Priced above comparables", "Priced below comparables"], "In line",
    )
    fv.to_csv(OUT / "fair_value_screen.csv", index=False)
    results["fair_value_flag_share"] = fv["flag"].value_counts(normalize=True).round(4).to_dict()
    return results, fv


def amenity_premiums(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["source"] == "metro_amenities"].dropna(subset=AMENITIES).copy()
    d["is_new"] = (d["sale_type"] == "New").astype(int)
    formula = (
        "np.log(price_inr) ~ np.log(area_sqft) + bhk + is_new + C(node) + "
        + " + ".join(AMENITIES)
    )
    fit = smf.ols(formula, data=d).fit(cov_type="HC3")
    ci = fit.conf_int()
    rows = []
    for a in AMENITIES:
        rows.append({
            "amenity": a,
            "premium": np.exp(fit.params[a]) - 1,
            "ci_low": np.exp(ci.loc[a, 0]) - 1,
            "ci_high": np.exp(ci.loc[a, 1]) - 1,
            "p_value": fit.pvalues[a],
            "share_with": d[a].mean(),
        })
    out = pd.DataFrame(rows).sort_values("premium", ascending=False)
    out.attrs["n"] = int(len(d))
    out.attrs["r2"] = float(fit.rsquared)
    # Amenities are highly collinear (gym/pool/clubhouse come bundled), so also
    # report the premium for the bundle count, which is more stable.
    fit2 = smf.ols(
        "np.log(price_inr) ~ np.log(area_sqft) + bhk + is_new + C(node) + amenity_count",
        data=d,
    ).fit(cov_type="HC3")
    out.attrs["premium_per_amenity"] = float(np.exp(fit2.params["amenity_count"]) - 1)
    lo, hi = fit2.conf_int().loc["amenity_count"]
    out.attrs["premium_per_amenity_ci"] = [float(np.exp(lo) - 1), float(np.exp(hi) - 1)]
    out.to_csv(OUT / "amenity_premiums.csv", index=False)
    return out


def run(df: pd.DataFrame) -> dict:
    OUT.mkdir(exist_ok=True)
    results, _ = valuation(df)
    am = amenity_premiums(df)
    results["amenity_model"] = {
        "n_listings": am.attrs["n"],
        "r2_in_sample": round(am.attrs["r2"], 4),
        "premium_per_additional_amenity": round(am.attrs["premium_per_amenity"], 4),
        "premium_per_additional_amenity_ci95": [round(x, 4) for x in am.attrs["premium_per_amenity_ci"]],
    }
    (OUT / "model_metrics.json").write_text(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    df = pd.read_csv(ROOT / "data" / "processed" / "listings.csv")
    print(json.dumps(run(df), indent=2))
