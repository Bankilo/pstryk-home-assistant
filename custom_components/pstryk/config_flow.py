"""Config flow for Pstryk.pl integration."""

import asyncio
import hashlib
import logging
from datetime import timedelta
from typing import Any
import ipaddress

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL, CONF_API_TOKEN, CONF_METER_IP, CONF_METER_AUTO_DETECTED, DOMAIN, MDNS_SERVICE_TYPE

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA_STEP1 = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): str,
        vol.Optional(CONF_NAME, default="Pstryk"): str,
    }
)

DATA_SCHEMA_METER_MANUAL = vol.Schema(
    {
        vol.Optional(CONF_METER_IP, default=""): str,
    }
)


async def validate_api_token(hass: HomeAssistant, api_token: str) -> tuple[bool, str]:
    """Validate the API token by making a test request.
    
    Returns a tuple of (is_valid, error_message).
    If is_valid is True, error_message will be an empty string.
    """
    session = async_get_clientsession(hass)
    headers = {"Authorization": f"{api_token}", "Accept": "application/json"}
    now = dt_util.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    start_utc = today.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = tomorrow.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    try:
        async with session.get(
            f"{API_BASE_URL}/pricing/?resolution=hour&window_start={start_utc}&window_end={end_utc}", 
            headers=headers, 
            timeout=30
        ) as response:
            if response.status == 200:
                # Verify we can parse the response
                try:
                    data = await response.json()
                    if "frames" in data:
                        return True, ""
                    else:
                        _LOGGER.error("API response missing 'frames' field")
                        return False, "invalid_response"
                except Exception as err:
                    _LOGGER.error("Error parsing API response: %s", err)
                    return False, "invalid_response"
            elif response.status == 401 or response.status == 403:
                return False, "invalid_auth"
            else:
                _LOGGER.error("Unexpected response from API: %s", response.status)
                return False, "cannot_connect"
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout when connecting to Pstryk API")
        return False, "timeout_error"
    except aiohttp.ClientError as err:
        _LOGGER.error("Client error when connecting to Pstryk API: %s", err)
        return False, "cannot_connect"
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error when validating Pstryk API token: %s", err)
        return False, "unknown"


async def discover_pstryk_meters(hass: HomeAssistant, timeout: int = 10) -> list[dict[str, str]]:
    """Discover Pstryk meters using mDNS."""
    discovered_meters = []
    
    try:
        # Use shared Zeroconf instance
        aiozc = await zeroconf.async_get_async_instance(hass)
        
        # Browse for Pstryk meters
        from zeroconf import ServiceBrowser, ServiceListener
        from zeroconf.asyncio import AsyncServiceInfo
        
        class PstrykListener(ServiceListener):
            def __init__(self):
                self.services = []
            
            def add_service(self, zc, type_, name):
                self.services.append((zc, type_, name))
            
            def remove_service(self, zc, type_, name):
                pass
            
            def update_service(self, zc, type_, name):
                pass
        
        listener = PstrykListener()
        browser = ServiceBrowser(aiozc.zeroconf, MDNS_SERVICE_TYPE, listener)
        
        # Wait for discovery with better logging
        _LOGGER.info("Waiting %d seconds for mDNS discovery...", timeout)
        await asyncio.sleep(timeout)
        _LOGGER.info("Discovery timeout completed, found %d services", len(listener.services))
        
        # Process discovered services
        for zc, type_, name in listener.services:
            try:
                info = AsyncServiceInfo(type_, name)
                await info.async_request(aiozc.zeroconf, 3000)
                
                if info and info.addresses:
                    ip_address = str(ipaddress.ip_address(info.addresses[0]))
                    port = info.port or 80
                    
                    discovered_meters.append({
                        "name": name.replace(f".{MDNS_SERVICE_TYPE}", ""),
                        "ip": ip_address,
                        "port": port,
                        "host": f"{ip_address}:{port}" if port != 80 else ip_address
                    })
                    _LOGGER.info("Discovered Pstryk meter: %s at %s:%s", name, ip_address, port)
            except Exception as err:
                _LOGGER.warning("Error processing discovered service %s: %s", name, err)
        
        # Clean up browser
        browser.cancel()
        
    except Exception as err:
        _LOGGER.error("Error during mDNS discovery: %s", err)
    
    return discovered_meters


async def validate_meter_connection(hass: HomeAssistant, meter_ip: str) -> tuple[bool, dict[str, Any] | None, str]:
    """Validate connection to Pstryk meter and get state data.
    
    Returns a tuple of (is_valid, meter_data, error_message).
    """
    if not meter_ip:
        return False, None, "empty_ip"
    
    # Validate IP format
    try:
        ipaddress.ip_address(meter_ip.split(':')[0])
    except ValueError:
        return False, None, "invalid_ip"
    
    session = async_get_clientsession(hass)
    
    # Ensure we have http:// prefix
    if not meter_ip.startswith(('http://', 'https://')):
        meter_url = f"http://{meter_ip}"
    else:
        meter_url = meter_ip
    
    if not meter_url.endswith('/'):
        meter_url += '/'
    
    try:
        async with session.get(f"{meter_url}state", timeout=10) as response:
            if response.status == 200:
                try:
                    data = await response.json()
                    _LOGGER.info("Successfully connected to Pstryk meter at %s", meter_ip)
                    return True, data, ""
                except Exception as err:
                    _LOGGER.error("Error parsing meter response: %s", err)
                    return False, None, "invalid_response"
            else:
                _LOGGER.error("Meter returned status %s", response.status)
                return False, None, "cannot_connect"
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout when connecting to meter at %s", meter_ip)
        return False, None, "timeout_error"
    except aiohttp.ClientError as err:
        _LOGGER.error("Client error when connecting to meter: %s", err)
        return False, None, "cannot_connect"
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error when connecting to meter: %s", err)
        return False, None, "unknown"


class PstrykConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pstryk.pl."""

    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._api_token = None
        self._name = None
        self._discovered_meters = []
        self._meter_data = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API token validation."""
        errors = {}

        if user_input is not None:
            # Use a stable hash of the API token as unique_id so the same
            # account cannot be configured twice, regardless of the chosen
            # friendly name.
            unique = hashlib.sha256(user_input[CONF_API_TOKEN].encode()).hexdigest()
            await self.async_set_unique_id(unique)
            self._abort_if_unique_id_configured()
            
            # Validate API token
            valid, error = await validate_api_token(
                self.hass, user_input[CONF_API_TOKEN]
            )

            if valid:
                # Store API token and name for later use
                self._api_token = user_input[CONF_API_TOKEN]
                self._name = user_input[CONF_NAME]
                
                # Move to meter discovery step
                return await self.async_step_meter_discovery()
            else:
                errors["base"] = error
                _LOGGER.warning(
                    "Failed to connect to Pstryk API with provided token. Error: %s", error
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA_STEP1, errors=errors
        )

    async def async_step_meter_discovery(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle meter discovery step."""
        if user_input is None:
            # Start meter discovery with longer timeout
            _LOGGER.info("Starting Pstryk meter discovery...")
            self._discovered_meters = await discover_pstryk_meters(self.hass, timeout=15)
            
            if self._discovered_meters:
                # Meters found, show selection
                _LOGGER.info("Found %d Pstryk meter(s)", len(self._discovered_meters))
                return await self.async_step_meter_selection()
            else:
                # No meters found, ask for manual IP
                _LOGGER.info("No Pstryk meters discovered, asking for manual IP")
                return await self.async_step_meter_manual()
        
        return self.async_abort(reason="unknown")

    async def async_step_meter_selection(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle meter selection from discovered meters."""
        errors = {}
        
        if user_input is not None:
            selected_meter = user_input.get("meter")
            
            if selected_meter == "manual":
                # User chose manual entry
                return await self.async_step_meter_manual()
            
            # Find selected meter
            meter_info = None
            for meter in self._discovered_meters:
                if meter["host"] == selected_meter:
                    meter_info = meter
                    break
            
            if meter_info:
                # Validate connection to selected meter
                valid, meter_data, error = await validate_meter_connection(self.hass, meter_info["host"])
                
                if valid:
                    # Store meter data and create entry
                    self._meter_data = meter_data
                    return await self._create_entry_with_meter(meter_info["host"], True)
                else:
                    errors["base"] = error
                    _LOGGER.warning("Failed to connect to selected meter %s: %s", meter_info["host"], error)
            else:
                errors["base"] = "meter_not_found"
        
        # Create options for meter selection
        meter_options = {}
        for meter in self._discovered_meters:
            meter_options[meter["host"]] = f"{meter['name']} ({meter['host']})"
        
        # Add manual option
        meter_options["manual"] = "Enter IP address manually"
        
        schema = vol.Schema({
            vol.Required("meter"): vol.In(meter_options)
        })
        
        return self.async_show_form(
            step_id="meter_selection", 
            data_schema=schema, 
            errors=errors,
            description_placeholders={
                "meter_count": len(self._discovered_meters)
            }
        )

    async def async_step_meter_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle manual meter IP entry."""
        errors = {}
        
        if user_input is not None:
            meter_ip = user_input.get(CONF_METER_IP, "").strip()
            
            if not meter_ip:
                # User skipped meter configuration
                return await self._create_entry_without_meter()
            
            # Validate meter connection
            valid, meter_data, error = await validate_meter_connection(self.hass, meter_ip)
            
            if valid:
                # Store meter data and create entry
                self._meter_data = meter_data
                return await self._create_entry_with_meter(meter_ip, False)
            else:
                errors[CONF_METER_IP] = error
                _LOGGER.warning("Failed to connect to meter at %s: %s", meter_ip, error)
        
        return self.async_show_form(
            step_id="meter_manual", 
            data_schema=DATA_SCHEMA_METER_MANUAL, 
            errors=errors
        )

    async def _create_entry_with_meter(self, meter_ip: str, auto_detected: bool) -> FlowResult:
        """Create config entry with meter information."""
        # Save meter data to cache file if available
        if self._meter_data:
            import json
            import os
            
            cache_file = self.hass.config.path("pstryk_cache.json")
            try:
                # Load existing cache or create new using async executor
                def _read_cache():
                    cache_data = {}
                    if os.path.exists(cache_file):
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                    return cache_data
                
                cache_data = await self.hass.async_add_executor_job(_read_cache)
                
                # Add meter data
                cache_data["meter_state"] = self._meter_data
                cache_data["meter_ip"] = meter_ip
                cache_data["meter_last_update"] = dt_util.utcnow().isoformat()
                
                # Save cache using async executor
                def _write_cache():
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, indent=2)
                
                await self.hass.async_add_executor_job(_write_cache)
                
                _LOGGER.info("Saved meter data to cache file")
            except Exception as err:
                _LOGGER.warning("Failed to save meter data to cache: %s", err)
        
        data = {
            CONF_API_TOKEN: self._api_token,
            CONF_NAME: self._name,
            CONF_METER_IP: meter_ip,
            CONF_METER_AUTO_DETECTED: auto_detected,
        }
        
        return self.async_create_entry(title=self._name, data=data)

    async def _create_entry_without_meter(self) -> FlowResult:
        """Create config entry without meter information."""
        data = {
            CONF_API_TOKEN: self._api_token,
            CONF_NAME: self._name,
        }
        
        return self.async_create_entry(title=self._name, data=data)