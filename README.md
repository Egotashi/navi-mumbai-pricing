# Navi Mumbai Residential Pricing

Pricing analysis for flats across 18 Navi Mumbai nodes, built on public listing data: a cleaning pipeline that consolidates three sources, regression models that value a flat from its location and attributes, an interactive benchmark dashboard, and a written market report.

![Median asking rate by node](docs/figures/node_benchmarks.png)

## What's in it

| Part | File | What it does |
|---|---|---|
| Cleaning pipeline | `src/clean.py` | Loads three public datasets, maps free-text localities to 18 canonical nodes, standardises prices (lakh/crore → ₹), filters implausible sizes, trims per-node outliers, and removes duplicates within and across sources. 21,389 raw rows → 12,531 unique listings. |
| Valuation models | `src/model.py` | Hedonic log-linear regression and gradient boosting, compared against a per-sq-ft rule of thumb with project-grouped 5-fold CV. Also estimates location premiums and amenity premiums with robust standard errors, and runs a fair-value screen. |
| Dashboard | `dashboard/index.html` | Self-contained page (no server). Filter by belt and BHK to recompute node benchmarks, ticket sizes and supply mix; includes an in-browser valuation estimate. |
| Market report | `docs/market_report.md` | Findings on node benchmarks, location premiums, ticket sizes, supply pipeline, amenities and model accuracy. |

## Key results

- **Three-tier market:** median asking rate ₹16,800/sq ft in the Central belt (Vashi–Belapur), ₹13,200 in the North (Airoli, Ghansoli), ₹8,400 in the South growth belt (Kharghar–Panvel–Taloja).
- **Location premium:** an identical flat lists for +71% in Seawoods and −40% in Taloja compared with Kharghar.
- **Model accuracy:** gradient boosting reaches R² 0.826 on log price and a 16.0% median error, against 20.8% for node median rate × area.
- **Amenities:** about +0.8% per additional amenity in the package; individual amenity effects are not separately identifiable.

| Model (out-of-fold, grouped by project) | R² log price | Median error | Within 20% |
|---|---|---|---|
| Node median rate × area | 0.711 | 20.8% | 48.3% |
| Hedonic regression | 0.783 | 18.9% | 52.1% |
| Gradient boosting | 0.826 | 16.0% | 58.4% |

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py
```

This rebuilds `data/processed/listings.csv`, everything in `outputs/`, the report figures in `docs/figures/`, and `dashboard/index.html`. Open the dashboard file directly in a browser.

## Methodology notes

- **Grouped cross-validation.** The same building is often listed many times. Folds are split by project so the model is always tested on buildings it has not seen; random splits overstate accuracy.
- **Log price target.** Prices are right-skewed and errors scale with price, so models predict log price and report percentage errors.
- **Robust inference.** Location and amenity premiums come from OLS with HC3 heteroskedasticity-robust standard errors.
- **Deduplication.** Listings match on node, BHK, area and price rounded to ₹10,000; the source with the richest attributes is kept.

## Limitations

- Asking prices, not registered sale values.
- Listed area may be carpet, built-up or super built-up depending on the listing.
- No unit floor level, sale dates, absorption or lead data in public listings.
- Listings date from roughly 2023–2024.

## Project structure

```
├── data/
│   ├── raw/                 # three public source files (see data/SOURCES.md)
│   └── processed/           # listings.csv, written by the pipeline
├── src/
│   ├── clean.py             # cleaning and consolidation
│   ├── model.py             # valuation, premiums, fair-value screen
│   └── report.py            # figures and dashboard build
├── dashboard/
│   ├── template.html        # dashboard source
│   └── index.html           # built dashboard with data embedded
├── docs/
│   ├── market_report.md
│   └── figures/
├── outputs/                 # metrics, premiums, fair-value screen, coefficients
└── run_pipeline.py
```

Data sources and licences: [`data/SOURCES.md`](data/SOURCES.md).
