"""Constants for the Pstryk.pl integration."""
from datetime import timedelta

DOMAIN = "pstryk"
API_BASE_URL = "https://api.pstryk.pl/integrations"
BUY_ENDPOINT = "pricing/?resolution=hour&window_start={start}&window_end={end}"
SELL_ENDPOINT = "prosumer-pricing/?resolution=hour&window_start={start}&window_end={end}"

CONF_API_TOKEN = "api_token"

DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

ATTR_CURRENT_PRICE = "current_price"
ATTR_NEXT_HOUR_PRICE = "next_hour_price"
ATTR_PRICES_TODAY = "prices_today"
ATTR_PRICES_TOMORROW = "prices_tomorrow"
ATTR_IS_CHEAP = "is_cheap"
ATTR_IS_EXPENSIVE = "is_expensive"
ATTR_CHEAP_HOURS = "cheap_hours"
ATTR_EXPENSIVE_HOURS = "expensive_hours"
ATTR_PRICES_FUTURE = "prices_future"

COORDINATOR = "coordinator"