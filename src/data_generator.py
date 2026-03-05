"""Generate realistic synthetic sales data with seasonality, trends, and noise."""

import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import STORES, DATA_START, DATA_END, SALES_PARQUET


def generate_sales_data(
    stores: list[str] = STORES,
    start: str = DATA_START,
    end: str = DATA_END,
    output_path: Path = SALES_PARQUET,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate multi-store daily sales with realistic patterns.

    Patterns per store:
    - Base level (varies by store)
    - Weekly seasonality (weekends higher)
    - Monthly trend (slight upward drift)
    - Holiday spikes (random ~5% of days get a bump)
    - Gaussian noise
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rows = []

    for store in stores:
        base = rng.uniform(80, 200)  # per-store base sales level
        trend_slope = rng.uniform(0.02, 0.08)  # slight upward trend

        for i, date in enumerate(dates):
            # weekly seasonality: weekends ~30% higher
            dow = date.dayofweek
            weekly = 1.3 if dow >= 5 else 1.0 - 0.05 * abs(dow - 2)

            # monthly trend
            trend = 1 + trend_slope * (i / len(dates))

            # holiday spike (~5% of days)
            holiday = 1.4 if rng.random() < 0.05 else 1.0

            # noise
            noise = rng.normal(1.0, 0.08)

            y = max(0, base * weekly * trend * holiday * noise)

            rows.append({
                "unique_id": store,
                "ds": date,
                "y": round(y, 2),
                "store_id": store,
                "event_timestamp": date,
            })

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"Generated {len(df)} rows for {len(stores)} stores -> {output_path}")
    return df


if __name__ == "__main__":
    generate_sales_data()
