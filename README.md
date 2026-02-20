# Pstryk.pl Energy Prices

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

This is a Home Assistant custom component that integrates with Pstryk.pl API to show electricity buying and selling prices.

## Features

- Real-time electricity buying prices
- Real-time electricity selling prices (for prosumers)
- Today's hourly price breakdown
- Tomorrow's hourly price breakdown (when available)
- Next hour price
- Detection of cheap and expensive hours
- Binary sensors for cheap/expensive hour status

## Installation

### HACS (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Add this repository as a custom repository in HACS:
   - Navigate to HACS in Home Assistant
   - Go to "Integrations"
   - Click the three dots in the top right corner
   - Select "Custom repositories"
   - Enter the repository URL: `https://github.com/Bankilo/pstryk-home-assistant`
   - Category: Integration
   - Click "Add"
3. Install the integration from HACS
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/pstryk` directory to your Home Assistant `/config/custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Home Assistant Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Pstryk.pl"
4. Enter your API token from Pstryk.pl
5. Click "Submit"

## API Token

To obtain an API token:

1. Log in to your Pstryk.pl account
2. Navigate to account settings
3. Generate an API token
4. Copy the token and use it in the Home Assistant integration setup

## Entities

The integration creates the following sensors:

- `sensor.pstryk_buy_price`: Current electricity buying price
- `sensor.pstryk_sell_price`: Current electricity selling price
- `sensor.pstryk_buy_price_next_hour`: Buying price for the upcoming hour
- `sensor.pstryk_sell_price_next_hour`: Selling price for the upcoming hour
- `binary_sensor.pstryk_buy_cheap_hour`: Indicates if current hour is flagged as cheap for buying
- `binary_sensor.pstryk_buy_expensive_hour`: Indicates if current hour is flagged as expensive for buying
- `binary_sensor.pstryk_sell_cheap_hour`: Indicates if current hour is flagged as cheap for selling
- `binary_sensor.pstryk_sell_expensive_hour`: Indicates if current hour is flagged as expensive for selling

Each price sensor exposes hourly price data via additional attributes compatible with [ev_smart_charging](https://github.com/jonasbkarlsson/ev_smart_charging):

- `prices_today` – list of today's hourly prices: `[{"time": "2025-02-20T00:00:00+01:00", "price": 0.71}, ...]`
- `prices_tomorrow` – list of tomorrow's hourly prices (same format, empty `[]` when not yet available)
- `is_cheap` – boolean, `true` when the current hour is flagged as cheap
- `is_expensive` – boolean, `true` when the current hour is flagged as expensive

Each next-hour sensor exposes:

- `target_hour` – ISO 8601 timestamp of the hour the price applies to (e.g. `"2025-02-20T14:00:00+01:00"`)

Each binary sensor exposes a list of upcoming cheap or expensive hours:

- `cheap_hours` / `expensive_hours` – `[{"timestamp": "2025-02-20T13:00:00+00:00", "hour": 13, "price": 0.71, "date": "2025-02-20"}, ...]`

## Usage in Automations

You can use these sensors in automations to optimize energy usage based on current prices:

```yaml
# Example 1: Turn on appliance during low price (numeric threshold)
automation:
  - alias: "Turn on appliance during low price"
    trigger:
      - platform: state
        entity_id: sensor.pstryk_buy_price
    condition:
      - condition: numeric_state
        entity_id: sensor.pstryk_buy_price
        below: 0.50  # Example price threshold
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.washing_machine

# Example 2: Turn on appliance during cheap hour flag
automation:
  - alias: "Turn on appliance during cheap hour"
    trigger:
      - platform: state
        entity_id: binary_sensor.pstryk_buy_cheap_hour
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.washing_machine

# Example 3: Turn off high-consumption devices during expensive hours
automation:
  - alias: "Turn off devices during expensive hour"
    trigger:
      - platform: state
        entity_id: binary_sensor.pstryk_buy_expensive_hour
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.high_consumption_device
```

## Viewing Price Charts

To visualise hourly prices you can use the
[ApexCharts card](https://github.com/RomRider/apexcharts-card) in a Lovelace
dashboard:

```yaml
type: custom:apexcharts-card
header:
  show: true
series:
  - entity: sensor.pstryk_buy_price
    name: Buy Price
    data_generator: |
      const today = entity.attributes.prices_today || [];
      const tomorrow = entity.attributes.prices_tomorrow || [];
      return today.concat(tomorrow).map(i => [i.time, i.price]);
  - entity: sensor.pstryk_sell_price
    name: Sell Price
    data_generator: |
      const today = entity.attributes.prices_today || [];
      const tomorrow = entity.attributes.prices_tomorrow || [];
      return today.concat(tomorrow).map(i => [i.time, i.price]);
```

This configuration will plot all available hourly prices for today and tomorrow.

## Offline Cache

The integration caches the last successful API response to
`config/pstryk_cache.json`. If the Pstryk.pl API becomes unavailable, cached
data will be used so your sensors continue to report prices.

## Troubleshooting

If you encounter issues with the integration:

1. Check that your API token is valid
2. Verify your internet connection
3. Check Home Assistant logs for any error messages
4. If problems persist, open an issue on GitHub

## License

This project is licensed under the MIT License - see the LICENSE file for details.
