"""Constants for the Pstryk.pl integration."""
from datetime import timedelta

DOMAIN = "pstryk"
API_BASE_URL = "https://api.pstryk.pl/integrations"
BUY_ENDPOINT = "pricing/?resolution=hour&window_start={start}&window_end={end}"
SELL_ENDPOINT = "prosumer-pricing/?resolution=hour&window_start={start}&window_end={end}"
ENERGY_COST_ENDPOINT = "meter-data/energy-cost/?resolution=hour&window_start={start}&window_end={end}"
ENERGY_USAGE_ENDPOINT = "meter-data/energy-usage/?resolution=hour&window_start={start}&window_end={end}"

CONF_API_TOKEN = "api_token"
CONF_METER_IP = "meter_ip"
CONF_METER_AUTO_DETECTED = "meter_auto_detected"

# mDNS service type for Pstryk meter discovery
MDNS_SERVICE_TYPE = "_pstryk._tcp.local."

DEFAULT_SCAN_INTERVAL = timedelta(hours=1)  # For API data
METER_SCAN_INTERVAL = timedelta(seconds=10)  # For local meter data

ATTR_CURRENT_PRICE = "current_price"
ATTR_NEXT_HOUR_PRICE = "next_hour_price"
ATTR_PRICES_TODAY = "prices_today"
ATTR_PRICES_TOMORROW = "prices_tomorrow"
ATTR_PRICES = "prices"
ATTR_IS_CHEAP = "is_cheap"
ATTR_IS_EXPENSIVE = "is_expensive"
ATTR_CHEAP_HOURS = "cheap_hours"
ATTR_EXPENSIVE_HOURS = "expensive_hours"
ATTR_PRICES_FUTURE = "prices_future"
ATTR_CURRENT_ENERGY_COST = "current_energy_cost"
ATTR_PREVIOUS_HOUR_ENERGY_COST = "previous_hour_energy_cost"

COORDINATOR = "coordinator"