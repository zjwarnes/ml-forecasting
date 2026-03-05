"""Feature registry: define features declaratively, compute incrementally."""

import pandas as pd
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FeatureDefinition:
    name: str
    compute_fn: Callable[[pd.DataFrame], pd.Series]
    dependencies: list[str] = field(default_factory=list)
    version: int = 1


class FeatureRegistry:
    """Registry of feature definitions that supports incremental computation."""

    def __init__(self):
        self._features: dict[str, FeatureDefinition] = {}

    def register(self, feature_def: FeatureDefinition):
        self._features[feature_def.name] = feature_def

    @property
    def feature_names(self) -> list[str]:
        return list(self._features.keys())

    def compute_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """Only compute features not already present as columns."""
        for name, feat in self._features.items():
            if name not in df.columns:
                df[name] = feat.compute_fn(df)
        return df

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Force recompute all registered features."""
        for name, feat in self._features.items():
            df[name] = feat.compute_fn(df)
        return df

    def get_missing(self, df: pd.DataFrame) -> list[str]:
        """Return names of features not yet in the dataframe."""
        return [name for name in self._features if name not in df.columns]
