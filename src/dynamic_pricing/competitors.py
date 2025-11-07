"""Competitor pricing service used by the pricing strategies."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

import requests


class CompetitorPricingError(RuntimeError):
    """Raised when a competitor quote cannot be retrieved."""


DEFAULT_COMPETITOR_PRICES: Dict[str, float] = {
    "binance": 30500.0,
    "kraken": 30250.0,
    "coinbase": 30320.0,
}


@dataclass
class CompetitorPriceQuote:
    name: str
    price: float


class CompetitorPriceService:
    """Retrieves competitor quotes via a stub map or CoinMarketCap's market-pairs API."""

    CMC_MARKET_PAIRS_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/market-pairs/latest"

    def __init__(
        self,
        price_map: Dict[str, float] | None = None,
        latency_ms: int = 0,
        provider: str = "stub",
        asset: str | None = None,
        vs_currency: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        provider_normalized = (provider or "stub").strip().lower()
        if provider_normalized not in {"stub", "coinmarketcap"}:
            raise ValueError(f"Unsupported competitor provider: {provider}")

        self.provider = provider_normalized
        self.latency_ms = latency_ms

        if self.provider == "stub":
            mapping = price_map or DEFAULT_COMPETITOR_PRICES
            self._prices = {name.lower(): float(price) for name, price in mapping.items()}
        else:
            self.asset = (asset or "BTC").upper()
            self.vs_currency = (vs_currency or "USD").upper()
            self._api_url = api_url or self.CMC_MARKET_PAIRS_URL
            self._api_key = (api_key or os.getenv("COINMARKETCAP_API_KEY") or "").strip()
            if not self._api_key:
                raise ValueError("CoinMarketCap competitor pricing requires an API key.")

    def get_price(self, competitor_name: str) -> CompetitorPriceQuote:
        if not competitor_name:
            raise CompetitorPricingError("Competitor name is required")
        key = competitor_name.strip().lower()

        if self.provider == "stub":
            if key not in self._prices:
                raise CompetitorPricingError(f"Unknown competitor: {competitor_name}")
            price = self._prices[key]
            return CompetitorPriceQuote(name=competitor_name, price=price)

        price = self._fetch_coinmarketcap_price(key)
        return CompetitorPriceQuote(name=competitor_name, price=price)

    def _fetch_coinmarketcap_price(self, competitor_key: str) -> float:
        """Query CoinMarketCap for the latest price listed on the competitor exchange."""

        headers = {"X-CMC_PRO_API_KEY": self._api_key}
        params = {
            "symbol": self.asset,
            "convert": self.vs_currency,
            "limit": 500,
        }
        try:
            response = requests.get(self._api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CompetitorPricingError("Failed to reach CoinMarketCap market-pairs endpoint") from exc

        payload = response.json() or {}
        data: List[dict] = payload.get("data") or []
        convert_symbol = self.vs_currency.upper()
        for entry in data:
            if entry.get("symbol", "").upper() != self.asset:
                continue
            market_pairs = entry.get("market_pairs") or []
            for pair in market_pairs:
                exchange_name = (
                    pair.get("exchange_name")
                    or pair.get("exchangeName")
                    or pair.get("exchange_slug")
                    or pair.get("exchangeSlug")
                )
                if not exchange_name or exchange_name.strip().lower() != competitor_key:
                    continue

                quote = pair.get("quote") or {}
                quotient = quote.get(convert_symbol) or quote.get(convert_symbol.lower())
                price = None
                if isinstance(quotient, dict):
                    price = quotient.get("price")
                    if price is None and isinstance(quotient.get("exchange_reported"), dict):
                        price = quotient["exchange_reported"].get("price")
                if price is None:
                    price = pair.get("price")
                if price is not None:
                    return float(price)

        raise CompetitorPricingError(
            f"No market pair found on CoinMarketCap for competitor '{competitor_key}' and asset {self.asset}/{self.vs_currency}."
        )


__all__ = [
    "CompetitorPriceQuote",
    "CompetitorPriceService",
    "CompetitorPricingError",
]
