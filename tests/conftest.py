"""Home Assistant fixtures for Pstryk regression tests."""

import pytest


@pytest.fixture(autouse=True)
async def configure_hass(hass, tmp_path):
    """Use Warsaw local time and an isolated on-disk cache."""
    await hass.config.async_set_time_zone("Europe/Warsaw")
    hass.config.config_dir = str(tmp_path)
