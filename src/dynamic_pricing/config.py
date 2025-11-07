"""
Configuration loading helpers for the pricing engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


class ConfigError(RuntimeError):
    """Raised when the user provided configuration is invalid."""


@dataclass
class ProductConfig:
    """Represents a product that needs a crypto pegged selling price."""

    name: str
    base_price_usd: float
    target_margin: float
    elasticity: float
    competitor_price_usd: float | None = None


@dataclass
class GuardrailConfig:
    """Constraints that keep the dynamic price within safe bounds."""

    min_markup: float
    max_markup: float
    volatility_floor: float
    volatility_ceiling: float


@dataclass
class DataSourceConfig:
    """Market data source options."""

    provider: str
    asset: str
    vs_currency: str
    lookback_hours: int
    api_url: str | None = None
    api_key: str | None = None


@dataclass
class EngineConfig:
    """Top-level configuration object used by the PriceEngine."""

    products: List[ProductConfig]
    guardrails: GuardrailConfig
    data_source: DataSourceConfig
    smoothing_window: int = 12


def _require(dictionary: Dict[str, Any], key: str) -> Any:
    if key not in dictionary:
        raise ConfigError(f"Missing required configuration key: {key}")
    return dictionary[key]


def _load_products(raw_products: List[Dict[str, Any]]) -> List[ProductConfig]:
    products = []
    for entry in raw_products:
        try:
            products.append(
                ProductConfig(
                    name=_require(entry, "name"),
                    base_price_usd=float(_require(entry, "base_price_usd")),
                    target_margin=float(_require(entry, "target_margin")),
                    elasticity=float(_require(entry, "elasticity")),
                    competitor_price_usd=(
                        float(entry["competitor_price_usd"])
                        if "competitor_price_usd" in entry and entry["competitor_price_usd"] is not None
                        else None
                    ),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid product configuration: {entry}") from exc
    return products


def load_config(path: str | Path) -> EngineConfig:
    """Load EngineConfig from a YAML file."""

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    products = _load_products(_require(raw, "products"))

    guardrails_raw = _require(raw, "guardrails")
    guardrails = GuardrailConfig(
        min_markup=float(_require(guardrails_raw, "min_markup")),
        max_markup=float(_require(guardrails_raw, "max_markup")),
        volatility_floor=float(_require(guardrails_raw, "volatility_floor")),
        volatility_ceiling=float(_require(guardrails_raw, "volatility_ceiling")),
    )

    data_raw = _require(raw, "data_source")
    data_source = DataSourceConfig(
        provider=_require(data_raw, "provider"),
        asset=_require(data_raw, "asset"),
        vs_currency=data_raw.get("vs_currency", "usd"),
        lookback_hours=int(data_raw.get("lookback_hours", 72)),
        api_url=data_raw.get("api_url"),
        api_key=data_raw.get("api_key"),
    )

    return EngineConfig(
        products=products,
        guardrails=guardrails,
        data_source=data_source,
        smoothing_window=int(raw.get("smoothing_window", 12)),
    )


__all__ = [
    "ConfigError",
    "DataSourceConfig",
    "EngineConfig",
    "GuardrailConfig",
    "ProductConfig",
    "load_config",
]
