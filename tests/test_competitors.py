import pytest

from dynamic_pricing.competitors import CompetitorPriceService, CompetitorPricingError


def test_competitor_service_stub_returns_price():
    service = CompetitorPriceService(price_map={"kraken": 123.45})
    quote = service.get_price("Kraken")

    assert quote.name == "Kraken"
    assert quote.price == pytest.approx(123.45)


def test_competitor_service_coinmarketcap_fetches_price(monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "symbol": "BTC",
                        "market_pairs": [
                            {
                                "exchange_name": "Binance",
                                "quote": {"USD": {"price": 31000.0}},
                            }
                        ],
                    }
                ]
            }

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("dynamic_pricing.competitors.requests.get", fake_get)

    service = CompetitorPriceService(
        provider="coinmarketcap",
        asset="BTC",
        vs_currency="USD",
        api_key="token",
    )

    quote = service.get_price("Binance")

    assert quote.price == pytest.approx(31000.0)
    assert captured["params"]["symbol"] == "BTC"
    assert captured["params"]["convert"] == "USD"
    assert captured["headers"]["X-CMC_PRO_API_KEY"] == "token"


def test_competitor_service_coinmarketcap_missing_exchange(monkeypatch):
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"symbol": "BTC", "market_pairs": []}]}

    monkeypatch.setattr("dynamic_pricing.competitors.requests.get", lambda *args, **kwargs: DummyResponse())

    service = CompetitorPriceService(
        provider="coinmarketcap",
        asset="BTC",
        vs_currency="USD",
        api_key="token",
    )

    with pytest.raises(CompetitorPricingError):
        service.get_price("Kraken")
