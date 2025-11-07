# Dynamic Cryptocurrency Pricing

This project showcases a lightweight dynamic pricing engine for merchants that sell goods or services while getting paid in crypto. It loads crypto market data, derives risk and momentum signals, and outputs adaptive price recommendations for a configurable product catalog.

## Features

- Pull historical candles from CoinMarketCap (API key) or fall back to the bundled CSV sample.
- Compute rolling volatility, momentum, moving averages, and spread risk indexes.
- Combine business rules (target margin, elasticity curve, volatility guardrails) into a final suggested markup.
- CLI to simulate the pricing engine on top of sample data or live API calls.
- Modular architecture (config parsing, data sources, signal generation, pricing strategies) ready for extension.

## Quick Start

```bash
# create and install (uses pyproject/requirements automatically)
uv venv
source .venv/bin/activate
uv sync --dev

# prepare environment (fill in COINMARKETCAP_API_KEY inside .env)
cp .env.example .env
$EDITOR .env

# run the CLI via uv (falls back to .venv/python if uv run is unavailable)
uv run python -m dynamic_pricing.cli \
  --config examples/configs/example_config.yaml \
  --data examples/data/sample_market_data.csv \
  --market-condition bull \
  --verbose

# pull live CoinMarketCap data (requires network access and .env key)
uv run python -m dynamic_pricing.cli \
  --config examples/configs/example_config.yaml \
  --market-condition balanced \
  --verbose
```

### CoinMarketCap API Key

The live data source expects an API key. Provide it via the `COINMARKETCAP_API_KEY` environment variable (recommended) or add `api_key` under `data_source` in your YAML config. The key is only used to resolve asset and fiat metadata; price candles are fetched from CoinMarketCap's historical endpoint.

The CLI automatically loads environment variables from a local `.env` file (or the path defined in `DYNAMIC_PRICING_ENV_FILE`). For convenience, copy `.env.example` to `.env` and fill in your actual API key.

## Repository Layout

```
.
├── examples/
│   ├── configs/             # YAML configs describing catalog, guardrails and API options
│   └── data/                # Sample market data for offline testing
├── src/dynamic_pricing/     # Pricing engine source code
├── tests/                   # Pytest suite covering the core engine logic
└── README.md                # This file
```

## Market Conditions

Each strategy tweaks the markup curve. Swap `--market-condition` to experiment:

```bash
uv run python -m dynamic_pricing.cli \
  --config examples/configs/example_config.yaml \
  --market-condition <strategy>
```

- **balanced** – original volatility-aware blend of momentum and guardrails (default):
  ```bash
  uv run python -m dynamic_pricing.cli --config examples/configs/example_config.yaml --market-condition balanced
  ```
- **bull** – pushes markups higher when upward momentum is present:
  ```bash
  uv run python -m dynamic_pricing.cli --config examples/configs/example_config.yaml --market-condition bull
  ```
- **bear** – prioritizes downside protection and margin preservation:
  ```bash
  uv run python -m dynamic_pricing.cli --config examples/configs/example_config.yaml --market-condition bear
  ```
- **lateral** – compresses markups when price action chops sideways:
  ```bash
  uv run python -m dynamic_pricing.cli --config examples/configs/example_config.yaml --market-condition lateral
  ```
- **penetration** – intentionally lowers markups to grab market share:
  ```bash
  uv run python -m dynamic_pricing.cli --config examples/configs/example_config.yaml --market-condition penetration
  ```
- **competitor** – aligns with the configured competitor reference price:
  ```bash
  uv run python -m dynamic_pricing.cli --config examples/configs/example_config.yaml --market-condition competitor
  ```

### Configuration Notes

- Each product entry can include `competitor_price_usd` to power the competitor-matching strategy.
- Guardrails still apply to every strategy so markups never exceed safe bounds.

## Extending

- Replace the CSV data source with another API by implementing `BaseMarketDataSource`.
- Tweak the `VolatilityAwareStrategy` or plug in a new strategy subclass.
- Integrate the engine into another service via the `PriceEngine` class.

## Tests

```bash
uv run pytest
```

The suite focuses on the pricing engine behavior and guardrails.
