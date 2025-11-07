"""
High level orchestration for the dynamic pricing pipeline.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

import pandas as pd

from .config import EngineConfig, GuardrailConfig, ProductConfig
from .data_sources import BaseMarketDataSource
from .pricing import PricingResult, PricingStrategy, VolatilityAwareStrategy
from .signals import build_feature_frame


class PriceEngine:
    """Runs feature computation and pricing for a set of products."""

    def __init__(
        self,
        config: EngineConfig,
        data_source: BaseMarketDataSource,
        strategy: PricingStrategy | None = None,
    ):
        self.config = config
        self.data_source = data_source
        self.strategy = strategy or VolatilityAwareStrategy()

    def _price_products(self, features: pd.DataFrame) -> List[PricingResult]:
        results: List[PricingResult] = []
        for product in self.config.products:
            result = self.strategy.price(product, self.config.guardrails, features)
            results.append(result)
        return results

    def run(self, external_data: pd.DataFrame | None = None) -> Sequence[PricingResult]:
        """Execute the pipeline and return pricing results."""

        market_data = external_data if external_data is not None else self.data_source.load_market_data()
        features = build_feature_frame(market_data, self.config.smoothing_window)
        if features.empty:
            raise RuntimeError("Not enough data points for the requested smoothing window")
        return self._price_products(features)


__all__ = ["PriceEngine"]
