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
- `binary_sensor.pstryk_buy_cheap_hour`: Indicates if current hour is flagged as cheap for buying
- `binary_sensor.pstryk_buy_expensive_hour`: Indicates if current hour is flagged as expensive for buying
- `binary_sensor.pstryk_sell_cheap_hour`: Indicates if current hour is flagged as cheap for selling
- `binary_sensor.pstryk_sell_expensive_hour`: Indicates if current hour is flagged as expensive for selling

Each price sensor exposes hourly price data via additional attributes:

- `prices_today` – dictionary of today's prices
- `prices_tomorrow` – dictionary of tomorrow's prices (when available)
- `prices` – combined dictionary of today and tomorrow

The binary sensors include lists of upcoming cheap or expensive hours.

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

## Troubleshooting

If you encounter issues with the integration:

1. Check that your API token is valid
2. Verify your internet connection
3. Check Home Assistant logs for any error messages
4. If problems persist, open an issue on GitHub

## License

This project is licensed under the MIT License - see the LICENSE file for details.
