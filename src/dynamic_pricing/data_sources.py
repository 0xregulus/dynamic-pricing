"""
Market data source implementations for the pricing engine.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

from .config import DataSourceConfig


class BaseMarketDataSource(ABC):
    @abstractmethod
    def load_market_data(self) -> pd.DataFrame:
        """Return a DataFrame with at least timestamp and price columns."""


class CSVMarketDataSource(BaseMarketDataSource):
    """Reads pre-downloaded candles from a CSV file."""

    def __init__(self, csv_path: str | Path):
        self._csv_path = Path(csv_path)

    def load_market_data(self) -> pd.DataFrame:
        frame = pd.read_csv(self._csv_path, parse_dates=["timestamp"])
        if "price" not in frame.columns:
            raise ValueError("CSV needs a 'price' column")
        return frame.sort_values("timestamp").reset_index(drop=True)


class CoinMarketCapDataSource(BaseMarketDataSource):
    """Pulls hourly candles from CoinMarketCap."""

    HISTORICAL_URL = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/historical"
    CRYPTO_MAP_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map"
    FIAT_MAP_URL = "https://pro-api.coinmarketcap.com/v1/fiat/map"

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self._api_key = (config.api_key or os.getenv("COINMARKETCAP_API_KEY") or "").strip()
        if not self._api_key:
            raise ValueError("CoinMarketCap API key missing. Set data_source.api_key or COINMARKETCAP_API_KEY.")
        self._fiat_cache: dict[str, int] | None = None
        self._asset_id: int | None = None

    def _headers(self) -> dict[str, str]:
        return {"X-CMC_PRO_API_KEY": self._api_key}

    def _load_fiat_directory(self) -> dict[str, int]:
        if self._fiat_cache is None:
            response = requests.get(self.FIAT_MAP_URL, headers=self._headers(), timeout=10)
            response.raise_for_status()
            entries = response.json().get("data") or []
            self._fiat_cache = {entry["symbol"].upper(): entry["id"] for entry in entries}
        return self._fiat_cache

    def _lookup_assets(self, params: Optional[dict] = None) -> list[dict]:
        response = requests.get(self.CRYPTO_MAP_URL, params=params, headers=self._headers(), timeout=10)
        response.raise_for_status()
        return response.json().get("data") or []

    def _resolve_asset_id(self) -> int:
        if self._asset_id is not None:
            return self._asset_id

        asset = self.config.asset.strip()
        if asset.isdigit():
            self._asset_id = int(asset)
            return self._asset_id

        # Try direct symbol lookup first
        symbol = asset.upper()
        candidates = self._lookup_assets({"symbol": symbol})
        active = [entry for entry in candidates if entry.get("is_active")]
        if active:
            self._asset_id = active[0]["id"]
            return self._asset_id

        # Fallback: scan listing for slug matches
        slug = asset.lower()
        for entry in self._lookup_assets():
            if entry.get("slug") == slug and entry.get("is_active"):
                self._asset_id = entry["id"]
                return self._asset_id

        raise RuntimeError(f"Unable to resolve CoinMarketCap asset id for '{self.config.asset}'.")

    def _resolve_convert_id(self) -> int:
        directory = self._load_fiat_directory()
        symbol = self.config.vs_currency.upper()
        if symbol not in directory:
            raise RuntimeError(f"Unsupported vs_currency for CoinMarketCap: {self.config.vs_currency}")
        return directory[symbol]

    def _build_interval_params(self) -> dict:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=max(1, self.config.lookback_hours))
        return {
            "timeStart": int(start.timestamp()),
            "timeEnd": int(end.timestamp()),
            "interval": "1h",
        }

    def _convert_series(self, quotes: Iterable[dict]) -> pd.DataFrame:
        timestamps: list[datetime] = []
        prices: list[float] = []
        for entry in quotes:
            quote = entry.get("quote") or {}
            price = quote.get("close")
            timestamp = quote.get("timestamp") or entry.get("timeClose")
            if price is None or not timestamp:
                continue
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            timestamps.append(ts)
            prices.append(float(price))
        if not timestamps:
            raise RuntimeError("CoinMarketCap returned no price points for the requested window.")
        return pd.DataFrame({"timestamp": timestamps, "price": prices})

    def load_market_data(self) -> pd.DataFrame:
        asset_id = self._resolve_asset_id()
        convert_id = self._resolve_convert_id()
        params = {
            "id": asset_id,
            "convertId": convert_id,
            **self._build_interval_params(),
        }
        url = self.config.api_url or self.HISTORICAL_URL
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        quotes = (payload.get("data") or {}).get("quotes") or []
        frame = self._convert_series(quotes)
        return frame.sort_values("timestamp").reset_index(drop=True)


def build_market_data_source(
    data_config: DataSourceConfig, csv_fallback: Optional[str] = None
) -> BaseMarketDataSource:
    """Return the best matching data source for the provided configuration."""

    provider = data_config.provider.lower()
    if provider == "coinmarketcap":
        return CoinMarketCapDataSource(data_config)
    if provider == "csv" and csv_fallback:
        return CSVMarketDataSource(csv_fallback)
    raise ValueError(f"Unsupported data provider: {data_config.provider}")


__all__ = [
    "BaseMarketDataSource",
    "CSVMarketDataSource",
    "CoinMarketCapDataSource",
    "build_market_data_source",
]
