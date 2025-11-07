"""
Pricing strategies that transform signals into recommended prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol

import numpy as np
import pandas as pd

from .config import GuardrailConfig, ProductConfig


@dataclass
class PricingResult:
    product: ProductConfig
    markup: float
    recommended_price: float
    signals: Dict[str, float]


class PricingStrategy(Protocol):
    def price(self, product: ProductConfig, guardrails: GuardrailConfig, features: pd.DataFrame) -> PricingResult:
        ...


class VolatilityAwareStrategy:
    """Balances trend upside with volatility driven risk adjustments."""

    def __init__(self, risk_aversion: float = 1.0):
        self.risk_aversion = risk_aversion

    def _condition_adjustment(self, product: ProductConfig, signals: Dict[str, float]) -> float:
        """Override in subclasses to bias markup based on market regime."""

        return 0.0

    def _clamp_markup(self, markup: float, guardrails: GuardrailConfig) -> float:
        return float(np.clip(markup, guardrails.min_markup, guardrails.max_markup))

    def price(self, product: ProductConfig, guardrails: GuardrailConfig, features: pd.DataFrame) -> PricingResult:
        latest = features.iloc[-1]
        volatility = float(latest["volatility"])
        momentum = float(latest["momentum"])
        trend_strength = float(latest["trend_strength"])

        trend_bonus = product.elasticity * trend_strength
        momentum_bonus = 0.5 * product.elasticity * momentum

        if volatility <= guardrails.volatility_floor:
            volatility_penalty = 0
        else:
            normalized = min(
                1.0,
                (volatility - guardrails.volatility_floor)
                / max(guardrails.volatility_ceiling - guardrails.volatility_floor, 1e-6),
            )
            volatility_penalty = normalized * self.risk_aversion

        signals = {
            "volatility": volatility,
            "momentum": momentum,
            "trend_strength": trend_strength,
        }

        raw_markup = (
            product.target_margin
            + trend_bonus
            + momentum_bonus
            - volatility_penalty
            + self._condition_adjustment(product, signals)
        )
        markup = self._clamp_markup(raw_markup, guardrails)
        price = product.base_price_usd * (1 + markup)

        return PricingResult(
            product=product,
            markup=markup,
            recommended_price=round(price, 2),
            signals={
                **signals,
                "raw_markup": raw_markup,
            },
        )


class BullMarketStrategy(VolatilityAwareStrategy):
    """Amplifies upside capture when the market trends upward."""

    def __init__(self, risk_aversion: float = 0.7, upside_weight: float = 0.4):
        super().__init__(risk_aversion=risk_aversion)
        self.upside_weight = upside_weight

    def _condition_adjustment(self, product: ProductConfig, signals: Dict[str, float]) -> float:
        upside = max(0.0, signals["trend_strength"]) + max(0.0, signals["momentum"])
        return self.upside_weight * product.elasticity * upside


class BearMarketStrategy(VolatilityAwareStrategy):
    """Protects margin when the market sells off."""

    def __init__(self, risk_aversion: float = 1.6, downside_weight: float = 0.5):
        super().__init__(risk_aversion=risk_aversion)
        self.downside_weight = downside_weight

    def _condition_adjustment(self, product: ProductConfig, signals: Dict[str, float]) -> float:
        downside = abs(min(0.0, signals["trend_strength"])) + abs(min(0.0, signals["momentum"]))
        penalty = self.downside_weight * (product.elasticity + 0.1) * downside
        return -penalty


class LateralMarketStrategy(VolatilityAwareStrategy):
    """Keeps pricing tight during sideways consolidation."""

    def __init__(self, risk_aversion: float = 1.0, compression_weight: float = 0.2):
        super().__init__(risk_aversion=risk_aversion)
        self.compression_weight = compression_weight

    def _condition_adjustment(self, product: ProductConfig, signals: Dict[str, float]) -> float:
        drift = abs(signals["momentum"]) + abs(signals["trend_strength"])
        return -self.compression_weight * drift * (product.elasticity / 2)


class MarketPenetrationStrategy(VolatilityAwareStrategy):
    """Aggressively reduces markup to gain market share."""

    def __init__(self, risk_aversion: float = 0.9, penetration_weight: float = 0.35):
        super().__init__(risk_aversion=risk_aversion)
        self.penetration_weight = penetration_weight

    def _condition_adjustment(self, product: ProductConfig, signals: Dict[str, float]) -> float:
        volatility_pressure = min(1.0, max(0.0, signals["volatility"] * 8))
        elasticity_factor = max(0.1, product.elasticity)
        discount_bias = self.penetration_weight * elasticity_factor * (1 - 0.5 * volatility_pressure)
        return -discount_bias


class CompetitorPriceMatchStrategy(VolatilityAwareStrategy):
    """Keeps the markup aligned with a known competitor reference price."""

    def __init__(self, risk_aversion: float = 1.2, match_weight: float = 0.7, undercut: float = 0.01):
        super().__init__(risk_aversion=risk_aversion)
        self.match_weight = match_weight
        self.undercut = undercut

    def _condition_adjustment(self, product: ProductConfig, signals: Dict[str, float]) -> float:
        if not product.competitor_price_usd or product.competitor_price_usd <= 0:
            return 0.0

        competitor_markup = (product.competitor_price_usd / product.base_price_usd) - 1
        desired_markup = competitor_markup - self.undercut
        delta = desired_markup - product.target_margin
        return self.match_weight * delta


def build_strategy(condition: str | None) -> PricingStrategy:
    """Return a strategy tuned for the requested market condition."""

    normalized = (condition or "balanced").strip().lower()
    if normalized in {"balanced", "default", "volatility_aware"}:
        return VolatilityAwareStrategy()
    if normalized == "bull":
        return BullMarketStrategy()
    if normalized in {"bear", "bearish"}:
        return BearMarketStrategy()
    if normalized in {"lateral", "sideways"}:
        return LateralMarketStrategy()
    if normalized in {"penetration", "market_penetration"}:
        return MarketPenetrationStrategy()
    if normalized in {"competitor", "competitor_match"}:
        return CompetitorPriceMatchStrategy()
    raise ValueError(f"Unsupported market condition: {condition}")


__all__ = [
    "CompetitorPriceMatchStrategy",
    "BearMarketStrategy",
    "BullMarketStrategy",
    "LateralMarketStrategy",
    "MarketPenetrationStrategy",
    "PricingResult",
    "PricingStrategy",
    "VolatilityAwareStrategy",
    "build_strategy",
]
