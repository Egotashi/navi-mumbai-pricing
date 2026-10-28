# Data sources

All three files in `data/raw/` are public listing datasets originally scraped from Indian property portals and published on Kaggle. The copies here were taken from public GitHub mirrors. Check each dataset's Kaggle page for its current licence before redistributing.

| File | Original dataset | Used for | Navi Mumbai rows (raw → clean) |
|---|---|---|---|
| `makaan_2024.csv` | [Mumbai House Price Data (70k Entries)](https://www.kaggle.com/datasets/kevinnadar22/mumbai-house-price-data-70k-entries), 2024 Makaan listings, Apache-2.0 | Valuation model: area, BHK, bathrooms, furnishing, age, coordinates | 10,792 → 6,606 |
| `makaan_mmr.csv` | [Mumbai House Prices](https://www.kaggle.com/datasets/dravidvaishnav/mumbai-house-prices), Makaan listings across MMR | Possession status (ready vs under construction), new vs resale | 8,951 → 4,753 |
| `metro_amenities.csv` | Mumbai file from the Kaggle "Housing Prices in Metropolitan Areas of India" dataset | 13 amenity flags (gym, pool, clubhouse, …) | 1,646 → 1,172 |

Mirrors used: `mhatreanuj57-alt/navi-mumbai-house-price-prediction` (`makaan_2024.csv`, `metro_amenities.csv`) and `GauravGirkar/house-price-prediction-ml` (`makaan_mmr.csv`).

Known quirks handled in `src/clean.py`:

- `metro_amenities.csv` labels its area column `sqrt`; the values are square feet.
- `makaan_mmr.csv` stores prices as a number plus a unit (`L` for lakh, `Cr` for crore).
- `makaan_2024.csv` has a `total_floors` column that is 1 for almost every row, so it is not used.
- Locality names are free text ("Sector 21 Kamothe", "Kharghar Sector 35"); they are mapped to 18 canonical nodes with whole-word matching so that, for example, Ghatkopar is not read as Kopar Khairane.
