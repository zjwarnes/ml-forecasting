"""Heuristic fallback: SeasonalNaive (last week's value for same day-of-week).

This is the safety net — always available, never fails, no model required.
Used when all ML models breach performance gates or serving errors occur.
"""

import pandas as pd
import numpy as np
from config.settings import FORECAST_HORIZON, SEASON_LENGTH


def seasonal_naive_forecast(
    history: pd.DataFrame,
    horizon: int = FORECAST_HORIZON,
    season_length: int = SEASON_LENGTH,
) -> pd.DataFrame:
    """Predict the next `horizon` days by repeating values from `season_length` days ago.

    Args:
        history: DataFrame with columns [unique_id, ds, y], sorted by ds.
        horizon: Number of days to forecast.
        season_length: Lookback period (7 = weekly pattern).

    Returns:
        DataFrame with columns [unique_id, ds, SeasonalNaive].
    """
    forecasts = []
    for uid, group in history.groupby("unique_id"):
        group = group.sort_values("ds")
        last_date = group["ds"].max()
        tail = group["y"].values[-season_length:]

        preds = []
        for h in range(1, horizon + 1):
            # cycle through the seasonal pattern
            idx = (h - 1) % season_length
            preds.append(max(0, tail[idx]))  # clamp to non-negative

        future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
        forecasts.append(pd.DataFrame({
            "unique_id": uid,
            "ds": future_dates,
            "SeasonalNaive": preds,
        }))

    return pd.concat(forecasts, ignore_index=True)
