"""Interactive Streamlit dashboard for the dynamic pricing engine."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd
import streamlit as st

from dynamic_pricing.competitors import CompetitorPriceService, CompetitorPricingError
from dynamic_pricing.config import (
    ConfigError,
    DataSourceConfig,
    EngineConfig,
    GuardrailConfig,
    ProductConfig,
    load_config,
)
from dynamic_pricing.data_sources import build_market_data_source
from dynamic_pricing.pricing import PricingResult, build_strategy
from dynamic_pricing.signals import build_feature_frame

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "examples" / "configs" / "example_config.yaml"


def _load_engine_config() -> EngineConfig:
    if not DEFAULT_CONFIG_PATH.exists():
        raise FileNotFoundError(
            "examples/configs/example_config.yaml not found. "
            "Update DEFAULT_CONFIG_PATH or provide a different configuration."
        )
    return load_config(DEFAULT_CONFIG_PATH)


def _fetch_market_data(data_config: DataSourceConfig) -> pd.DataFrame:
    source = build_market_data_source(data_config)
    frame = source.load_market_data()
    return frame.sort_values("timestamp").reset_index(drop=True)


def _compute_price_history(
    products: Sequence[ProductConfig],
    guardrails: GuardrailConfig,
    features: pd.DataFrame,
    strategy,
) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame()

    history: Dict[str, List[float]] = {product.name: [] for product in products}
    timestamps: List[pd.Timestamp] = []
    for idx in range(len(features)):
        window = features.iloc[: idx + 1]
        ts = window.iloc[-1]["timestamp"]
        timestamps.append(ts)
        for product in products:
            result = strategy.price(product, guardrails, window)
            history[product.name].append(result.recommended_price)

    price_history = pd.DataFrame(history)
    price_history.insert(0, "timestamp", pd.to_datetime(timestamps))
    return price_history


def _render_metrics(results: Sequence[PricingResult]) -> None:
    if not results:
        return
    cols = st.columns(len(results))
    for col, result in zip(cols, results):
        col.metric(
            label=result.product.name,
            value=f"${result.recommended_price:,.2f}",
            delta=f"{result.markup * 100:.2f}% markup",
        )


def _build_competitor_service(
    strategy_key: str,
    provider: str,
    asset: str,
    vs_currency: str,
    api_key: str,
) -> CompetitorPriceService | None:
    if strategy_key not in {"competitor", "competitor_match"}:
        return None

    provider_name = provider.strip().lower()
    if provider_name == "coinmarketcap":
        if not api_key:
            st.warning("CoinMarketCap provider selected but API key not provided. Falling back to stub quotes.")
            return CompetitorPriceService()
        try:
            return CompetitorPriceService(provider="coinmarketcap", asset=asset, vs_currency=vs_currency, api_key=api_key)
        except ValueError as exc:
            st.error(f"Unable to initialize CoinMarketCap competitor service: {exc}")
            return CompetitorPriceService()
        except CompetitorPricingError as exc:
            st.error(f"Competitor service error: {exc}")
            return CompetitorPriceService()
    return CompetitorPriceService()


def main() -> None:
    st.set_page_config(page_title="Dynamic Pricing Dashboard", layout="wide")
    st.title("Dynamic Pricing Sandbox")
    st.caption("Tune guardrails, strategies, and competitor references to see product prices update in real time.")

    try:
        engine_config = _load_engine_config()
    except (FileNotFoundError, ConfigError) as exc:
        st.error(str(exc))
        return

    default_products = list(engine_config.products)
    guardrail_defaults = engine_config.guardrails
    data_source_defaults = engine_config.data_source

    strategy_choice = st.sidebar.selectbox(
        "Strategy",
        options=["balanced", "bull", "bear", "lateral", "penetration", "competitor"],
        index=0,
    )
    asset_symbol = st.sidebar.text_input("Asset symbol", value=data_source_defaults.asset).upper()
    quote_currency = st.sidebar.text_input("Quote currency", value=data_source_defaults.vs_currency).upper()
    lookback_hours = st.sidebar.slider(
        "Lookback window (hours)",
        min_value=12,
        max_value=240,
        value=int(data_source_defaults.lookback_hours),
        step=6,
    )
    smoothing_window = st.sidebar.slider(
        "Smoothing window",
        min_value=3,
        max_value=48,
        value=int(engine_config.smoothing_window),
        step=1,
    )
    if st.sidebar.button("Refresh now"):
        st.rerun()

    min_markup = st.sidebar.number_input(
        "Min markup",
        min_value=0.0,
        max_value=2.0,
        value=float(guardrail_defaults.min_markup),
        step=0.01,
    )
    max_markup = st.sidebar.number_input(
        "Max markup",
        min_value=min_markup + 0.01,
        max_value=3.0,
        value=max(float(guardrail_defaults.max_markup), min_markup + 0.01),
        step=0.01,
    )
    volatility_floor = st.sidebar.number_input(
        "Volatility floor",
        min_value=0.0,
        max_value=1.0,
        value=float(guardrail_defaults.volatility_floor),
        step=0.01,
    )
    volatility_ceiling = st.sidebar.number_input(
        "Volatility ceiling",
        min_value=volatility_floor + 0.001,
        max_value=2.0,
        value=max(float(guardrail_defaults.volatility_ceiling), volatility_floor + 0.001),
        step=0.01,
    )

    product_configs: List[ProductConfig] = []
    for idx, product in enumerate(default_products):
        with st.sidebar.expander(f"Product: {product.name}", expanded=(idx == 0)):
            target_margin = st.number_input(
                f"Target margin ({product.name})",
                min_value=0.0,
                max_value=2.0,
                value=float(product.target_margin),
                step=0.01,
                key=f"margin_{idx}",
            )
            elasticity = st.number_input(
                f"Elasticity ({product.name})",
                min_value=0.0,
                max_value=2.0,
                value=float(product.elasticity),
                step=0.05,
                key=f"elasticity_{idx}",
            )
            competitor_name = st.text_input(
                f"Competitor name ({product.name})",
                value=product.competitor_name or "",
                key=f"competitor_{idx}",
            )
        product_configs.append(
            ProductConfig(
                name=product.name,
                target_margin=target_margin,
                elasticity=elasticity,
                competitor_name=competitor_name.strip() or None,
            )
        )

    api_key_default = data_source_defaults.api_key or os.getenv("COINMARKETCAP_API_KEY", "")
    api_key = st.sidebar.text_input("CoinMarketCap API key", value=api_key_default, type="password")
    provider_name = data_source_defaults.provider.lower()
    if provider_name != "coinmarketcap":
        st.warning(
            f"Loaded configuration targets '{provider_name}' data. The dashboard currently fetches live data "
            "from CoinMarketCap; update the YAML if needed."
        )
    if not api_key:
        st.warning("Provide a CoinMarketCap API key to fetch live candles.")
        st.stop()

    data_source_config = replace(
        data_source_defaults,
        asset=asset_symbol or data_source_defaults.asset,
        vs_currency=quote_currency or data_source_defaults.vs_currency,
        lookback_hours=int(lookback_hours),
        api_key=api_key,
    )
    try:
        prices = _fetch_market_data(data_source_config)
    except Exception as exc:  # noqa: BLE001 - show friendly message to user
        st.error(f"Failed to load market data: {exc}")
        st.stop()

    features = build_feature_frame(prices, smoothing_window)
    if features.empty:
        st.warning("Not enough data points for the selected smoothing window. Try increasing lookback hours.")
        return

    competitor_provider = st.sidebar.selectbox(
        "Competitor price provider",
        options=["stub", "coinmarketcap"],
        index=0,
    )

    guardrails = GuardrailConfig(
        min_markup=min_markup,
        max_markup=max_markup,
        volatility_floor=volatility_floor,
        volatility_ceiling=volatility_ceiling,
    )

    competitor_service = _build_competitor_service(
        strategy_choice,
        competitor_provider,
        asset_symbol,
        quote_currency,
        api_key if competitor_provider == "coinmarketcap" else "",
    )
    strategy = build_strategy(strategy_choice, competitor_service=competitor_service)

    price_history = _compute_price_history(product_configs, guardrails, features, strategy)
    latest_results: List[PricingResult] = []
    for product in product_configs:
        latest_results.append(strategy.price(product, guardrails, features))

    _render_metrics(latest_results)

    if not price_history.empty:
        chart_df = price_history.set_index("timestamp")
        st.subheader("Product Price Sparklines")
        st.line_chart(chart_df)

    st.subheader("Latest Signals")
    signals_rows = []
    for result in latest_results:
        signals = result.signals
        signals_rows.append(
            {
                "Product": result.product.name,
                "Recommended Price": result.recommended_price,
                "Markup (%)": round(result.markup * 100, 2),
                "Trend Strength": round(float(signals.get("trend_strength", 0.0)), 4),
                "Momentum": round(float(signals.get("momentum", 0.0)), 4),
                "Volatility": round(float(signals.get("volatility", 0.0)), 4),
                "Spot Price": round(float(signals.get("spot_price", 0.0)), 2),
            }
        )
    st.dataframe(pd.DataFrame(signals_rows))

    st.caption(
        "Use the sidebar to adjust guardrails, strategy, and competitor references. "
        "Live candles and competitor quotes stream from CoinMarketCap using the provided API key."
    )


if __name__ == "__main__":  # pragma: no cover - streamlit entrypoint
    main()
