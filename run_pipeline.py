"""Run the full pipeline: clean -> model -> dashboard and figures."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import clean  # noqa: E402
import model  # noqa: E402
import report  # noqa: E402

if __name__ == "__main__":
    df, log = clean.build()
    print("Cleaning:", json.dumps(log, indent=2))
    metrics = model.run(df)
    print("Models:", json.dumps({k: metrics[k] for k in
          ["baseline_node_median_ppsf", "hedonic_ridge", "gradient_boosting"]}, indent=2))
    print("Dashboard:", report.run(df))
