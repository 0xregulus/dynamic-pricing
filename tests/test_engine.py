from datetime import datetime, timedelta, timezone

import pandas as pd

from dynamic_pricing.competitors import CompetitorPriceService
from dynamic_pricing.config import DataSourceConfig, EngineConfig, GuardrailConfig, ProductConfig
from dynamic_pricing.data_sources import BaseMarketDataSource
from dynamic_pricing.engine import PriceEngine
from dynamic_pricing.pricing import (
    BearMarketStrategy,
    BullMarketStrategy,
    CompetitorPriceMatchStrategy,
    LateralMarketStrategy,
    MarketPenetrationStrategy,
    VolatilityAwareStrategy,
    build_strategy,
)


class DummySource(BaseMarketDataSource):
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def load_market_data(self) -> pd.DataFrame:
        return self.frame


def build_frame(points: int = 24) -> pd.DataFrame:
    base = datetime.now(tz=timezone.utc) - timedelta(hours=points)
    timestamps = [base + timedelta(hours=i) for i in range(points)]
    prices = [30000 + (i * 25) for i in range(points)]
    return pd.DataFrame({"timestamp": timestamps, "price": prices})


def test_engine_returns_price_for_all_products():
    products = [
        ProductConfig(name="Test A", target_margin=0.3, elasticity=0.5),
        ProductConfig(name="Test B", target_margin=0.4, elasticity=0.2),
    ]
    config = EngineConfig(
        products=products,
        guardrails=GuardrailConfig(
            min_markup=0.1,
            max_markup=0.8,
            volatility_floor=0.01,
            volatility_ceiling=0.3,
        ),
        data_source=DataSourceConfig(
            provider="csv",
            asset="bitcoin",
            vs_currency="usd",
            lookback_hours=24,
        ),
        smoothing_window=6,
    )
    data = build_frame(30)
    engine = PriceEngine(config, DummySource(data), strategy=VolatilityAwareStrategy(risk_aversion=0.2))

    results = engine.run()

    assert len(results) == len(products)
    for result in results:
        assert result.recommended_price > 0
        assert config.guardrails.min_markup <= result.markup <= config.guardrails.max_markup


def test_strategy_penalizes_high_volatility():
    product = ProductConfig(name="Test", target_margin=0.3, elasticity=0.3)
    guardrails = GuardrailConfig(
        min_markup=0.1,
        max_markup=0.8,
        volatility_floor=0.01,
        volatility_ceiling=0.2,
    )
    strategy = VolatilityAwareStrategy(risk_aversion=1.5)

    data = build_frame(20)
    engine = PriceEngine(
        EngineConfig(
            products=[product],
            guardrails=guardrails,
            data_source=DataSourceConfig(
                provider="csv",
                asset="bitcoin",
                vs_currency="usd",
                lookback_hours=24,
            ),
            smoothing_window=5,
        ),
        DummySource(data),
        strategy=strategy,
    )

    low_vol_result = engine.run()[0]

    # increase volatility by alternating spikes
    noisy = data.copy()
    noisy["price"] = noisy["price"].astype(float)
    noisy.loc[::2, "price"] *= 1.1
    noisy.loc[1::2, "price"] *= 0.9
    high_vol_result = engine.run(external_data=noisy)[0]

    assert high_vol_result.markup <= low_vol_result.markup


def test_build_strategy_handles_market_conditions():
    assert isinstance(build_strategy("bull"), BullMarketStrategy)
    assert isinstance(build_strategy("bear"), BearMarketStrategy)
    assert isinstance(build_strategy("lateral"), LateralMarketStrategy)
    assert isinstance(build_strategy("penetration"), MarketPenetrationStrategy)
    assert isinstance(build_strategy("competitor"), CompetitorPriceMatchStrategy)
    assert isinstance(build_strategy("balanced"), VolatilityAwareStrategy)


def test_market_condition_strategies_shift_markup():
    product = ProductConfig(name="Conditioned", target_margin=0.35, elasticity=0.5)
    guardrails = GuardrailConfig(
        min_markup=0.1,
        max_markup=0.9,
        volatility_floor=0.01,
        volatility_ceiling=0.25,
    )
    config = EngineConfig(
        products=[product],
        guardrails=guardrails,
        data_source=DataSourceConfig(
            provider="csv",
            asset="bitcoin",
            vs_currency="usd",
            lookback_hours=48,
        ),
        smoothing_window=6,
    )
    data = build_frame(48)

    bull_markup = PriceEngine(config, DummySource(data), strategy=BullMarketStrategy()).run()[0].markup
    bear_markup = PriceEngine(config, DummySource(data), strategy=BearMarketStrategy()).run()[0].markup
    lateral_markup = PriceEngine(config, DummySource(data), strategy=LateralMarketStrategy()).run()[0].markup
    penetration_markup = PriceEngine(config, DummySource(data), strategy=MarketPenetrationStrategy()).run()[0].markup
    balanced_markup = PriceEngine(config, DummySource(data), strategy=VolatilityAwareStrategy()).run()[0].markup

    assert bull_markup >= balanced_markup
    assert bear_markup <= balanced_markup
    assert guardrails.min_markup <= lateral_markup <= guardrails.max_markup
    assert abs(lateral_markup - balanced_markup) < 0.05
    assert penetration_markup <= balanced_markup


def test_competitor_strategy_tracks_reference_price():
    product = ProductConfig(
        name="Competitive",
        target_margin=0.4,
        elasticity=0.3,
        competitor_name="Kraken",
    )
    guardrails = GuardrailConfig(
        min_markup=0.0,
        max_markup=0.9,
        volatility_floor=0.01,
        volatility_ceiling=0.3,
    )
    config = EngineConfig(
        products=[product],
        guardrails=guardrails,
        data_source=DataSourceConfig(
            provider="csv",
            asset="bitcoin",
            vs_currency="usd",
            lookback_hours=24,
        ),
        smoothing_window=6,
    )
    data = build_frame(30)
    spot_price = data["price"].iloc[-1]
    competitor_price = spot_price * 1.05
    price_service = CompetitorPriceService({"kraken": competitor_price})

    balanced = PriceEngine(config, DummySource(data), strategy=VolatilityAwareStrategy()).run()[0]
    competitor = PriceEngine(
        config,
        DummySource(data),
        strategy=CompetitorPriceMatchStrategy(match_weight=1.0, price_service=price_service),
    ).run()[0]

    target_markup = (competitor_price / spot_price) - 1 - 0.01

    assert competitor.markup <= balanced.markup
    assert abs(competitor.markup - target_markup) < 0.1
