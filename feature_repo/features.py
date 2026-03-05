"""Feast feature definitions — matches what the service and training pipeline use."""

from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64

# ── Entity ─────────────────────────────────────────────────────────────
store = Entity(name="store_id", join_keys=["store_id"])

# ── Data Source ────────────────────────────────────────────────────────
features_source = FileSource(
    path="../data/features.parquet",
    timestamp_field="event_timestamp",
)

# ── Feature View ───────────────────────────────────────────────────────
sales_stats = FeatureView(
    name="sales_stats",
    entities=[store],
    schema=[
        Field(name="y", dtype=Float32),
        Field(name="rolling_sales_7d", dtype=Float32),
        Field(name="rolling_sales_28d", dtype=Float32),
        Field(name="lag_7", dtype=Float32),
        Field(name="lag_14", dtype=Float32),
        Field(name="day_of_week", dtype=Int64),
        Field(name="month", dtype=Int64),
        Field(name="is_weekend", dtype=Int64),
    ],
    source=features_source,
)
