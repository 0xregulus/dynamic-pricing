"""
Command line interface for the dynamic pricing engine.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import load_config
from .data_sources import build_market_data_source
from .engine import PriceEngine
from .env import load_env_file
from .pricing import build_strategy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dynamic cryptocurrency pricing demo")
    parser.add_argument(
        "--config",
        default="examples/configs/example_config.yaml",
        help="Path to the YAML config file",
    )
    parser.add_argument(
        "--data",
        help="Optional CSV containing timestamp,price columns. "
        "If omitted the configured provider (e.g. CoinMarketCap) will be queried.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print intermediate signals for each product")
    parser.add_argument(
        "--market-condition",
        choices=["balanced", "bull", "bear", "lateral", "penetration", "competitor"],
        default="balanced",
        help="Selects a strategy tuned for the market regime or business goal",
    )
    return parser.parse_args()


def _load_external_data(csv_path: Optional[str]) -> Optional[pd.DataFrame]:
    if not csv_path:
        return None
    data_file = Path(csv_path)
    if not data_file.exists():
        raise FileNotFoundError(f"CSV data file not found: {csv_path}")
    return pd.read_csv(data_file, parse_dates=["timestamp"])


def main() -> None:
    load_env_file(os.getenv("DYNAMIC_PRICING_ENV_FILE", ".env"))
    args = _parse_args()
    config = load_config(args.config)
    data_source = build_market_data_source(config.data_source, csv_fallback=args.data)
    strategy = build_strategy(args.market_condition)
    engine = PriceEngine(config, data_source, strategy=strategy)

    external_data = _load_external_data(args.data)
    results = engine.run(external_data=external_data)

    print("\nDynamic Pricing Results\n-----------------------")
    for result in results:
        price_line = (
            f"{result.product.name:20} | "
            f"price: ${result.recommended_price:>8.2f} | "
            f"markup: {result.markup*100:>5.2f}%"
        )
        print(price_line)
        if args.verbose:
            signals = ", ".join(f"{key}={value:.4f}" for key, value in result.signals.items())
            print(f"    signals -> {signals}")


if __name__ == "__main__":
    main()
