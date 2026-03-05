"""Data quality gates: schema validation, null checks, outlier detection, continuity."""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field


@dataclass
class QualityReport:
    passed: bool
    checks: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        failed = [c for c in self.checks if not c["passed"]]
        if not failed:
            return f"All {len(self.checks)} checks passed."
        lines = [f"{len(failed)}/{len(self.checks)} checks FAILED:"]
        for c in failed:
            lines.append(f"  FAIL: {c['check']} -- {c['details']}")
        return "\n".join(lines)


EXPECTED_COLUMNS = {"unique_id", "ds", "y"}


def run_quality_checks(df: pd.DataFrame) -> QualityReport:
    """Run all data quality checks. Returns a QualityReport."""
    checks = []

    # 1. Required columns present
    missing_cols = EXPECTED_COLUMNS - set(df.columns)
    checks.append({
        "check": "required_columns",
        "passed": len(missing_cols) == 0,
        "details": f"missing: {missing_cols}" if missing_cols else "all present",
    })

    # 2. No empty dataframe
    checks.append({
        "check": "non_empty",
        "passed": len(df) > 0,
        "details": f"{len(df)} rows",
    })

    if len(df) == 0 or missing_cols:
        return QualityReport(passed=False, checks=checks)

    # 3. Null checks per column (<5% nulls)
    null_pct = df.isnull().sum() / len(df)
    for col in EXPECTED_COLUMNS:
        pct = null_pct.get(col, 0)
        checks.append({
            "check": f"nulls_{col}",
            "passed": pct < 0.05,
            "details": f"{pct:.2%} null",
        })

    # 4. Non-negative target
    neg_count = (df["y"] < 0).sum()
    checks.append({
        "check": "non_negative_y",
        "passed": neg_count == 0,
        "details": f"{neg_count} negative values",
    })

    # 5. Outlier check on y (IQR method, 3x)
    q1, q3 = df["y"].quantile([0.25, 0.75])
    iqr = q3 - q1
    outlier_pct = ((df["y"] < q1 - 3 * iqr) | (df["y"] > q3 + 3 * iqr)).mean()
    checks.append({
        "check": "outliers_y",
        "passed": outlier_pct < 0.02,
        "details": f"{outlier_pct:.2%} outliers (IQR 3x)",
    })

    # 6. Temporal continuity per store (no gaps > 1 day)
    for uid in df["unique_id"].unique():
        store_dates = df[df["unique_id"] == uid]["ds"].sort_values()
        if len(store_dates) < 2:
            continue
        gaps = store_dates.diff().dt.days
        max_gap = gaps.max()
        checks.append({
            "check": f"continuity_{uid}",
            "passed": max_gap <= 1,
            "details": f"max_gap={max_gap} days",
        })

    passed = all(c["passed"] for c in checks)
    return QualityReport(passed=passed, checks=checks)
