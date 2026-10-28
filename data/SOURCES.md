# Data source

`data/raw/makaan_2024.csv` is the public Kaggle dataset [Mumbai House Price Data (70k Entries)](https://www.kaggle.com/datasets/kevinnadar22/mumbai-house-price-data-70k-entries): 71,938 flat listings across the Mumbai Metropolitan Region, scraped from Makaan.com in 2024 and released under Apache-2.0. The copy here was taken from the public GitHub mirror `mhatreanuj57-alt/navi-mumbai-house-price-prediction`.

Columns used: price, area, locality, property type, bedrooms, bathrooms, furnishing, building age, latitude and longitude. The listings carry no posting date, so the data is treated as a single 2024 snapshot.

Known quirks handled in `src/clean.py`:

- Locality names are free text ("Sector 21 Kamothe", "Kharghar Sector 35"); they are mapped to 18 canonical Navi Mumbai nodes with whole-word matching so that, for example, Ghatkopar is not read as Kopar Khairane.
- The `total_floors` column is 1 for almost every row, so it is not used.
- The same flat is often listed several times; about 37% of Navi Mumbai rows are repeats and are removed.
