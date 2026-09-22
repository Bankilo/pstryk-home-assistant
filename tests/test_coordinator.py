"""Regression coverage for cached prices during API outages."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pstryk.coordinator import (
    PstrykDataUpdateCoordinator,
    _to_float_precise,
)


def frame(start, buy, sell, *, cheap=False, expensive=False):
    """Create an hourly API frame with distinct buy/sell prices."""
    start = datetime.fromisoformat(start)
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "metrics": {
            "pricing": {
                "price_gross": buy,
                "price_prosumer_gross": sell,
                "is_cheap": cheap,
                "is_expensive": expensive,
            }
        },
    }


@pytest.fixture
def entry():
    return MockConfigEntry(domain="pstryk", data={"api_token": "test-token"})


@pytest.fixture
async def coordinator(hass, entry):
    return PstrykDataUpdateCoordinator(hass, MagicMock(), entry)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_unpublished_price_is_silent(value, caplog):
    assert _to_float_precise(value) is None
    assert "Price conversion error" not in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0.0), ("0.000", 0.0), (-0.125, -0.125), ("1,2345", 1.235),
     (Decimal("0.1234"), 0.123)],
)
def test_real_prices_keep_precision(value, expected):
    assert _to_float_precise(value) == expected


def test_malformed_price_still_warns(caplog):
    assert _to_float_precise("invalid") is None
    assert "Price conversion error" in caplog.text


@pytest.mark.parametrize("error", [asyncio.TimeoutError, aiohttp.ClientError])
async def test_repeated_outages_recompute_both_prices_and_flags(
    coordinator, freezer, error
):
    freezer.move_to("2026-09-22T07:00:00+00:00")
    raw = {"frames": [
        frame("2026-09-22T07:00:00+00:00", "0.7", "0.2", cheap=True),
        frame("2026-09-22T08:00:00+00:00", "1.23", "0.6", expensive=True),
        frame("2026-09-22T09:00:00+00:00", "0", "-0.125", cheap=True),
    ]}
    with patch.object(coordinator, "_fetch_unified_data", return_value=raw):
        assert (await coordinator._async_update_data())["buy"]["current_price"] == 0.7

    with patch.object(coordinator, "_fetch_unified_data", side_effect=error):
        for now, buy, sell, cheap, expensive in [
            ("08:00:00", 1.23, 0.6, False, True),
            ("09:00:00", 0.0, -0.125, True, False),
            ("10:00:00", None, None, False, False),
        ]:
            freezer.move_to(f"2026-09-22T{now}+00:00")
            data = await coordinator._async_update_data()
            for branch, price in [("buy", buy), ("sell", sell)]:
                assert data[branch]["current_price"] == price
                assert data[branch]["is_cheap"] is cheap
                assert data[branch]["is_expensive"] is expensive
                assert len(data[branch]["prices"]) == 3

    # Recovery resumes live data and replaces the stale cache.
    recovered = {"frames": [frame("2026-09-22T10:00:00+00:00", "0.8", "0.3")]}
    with patch.object(coordinator, "_fetch_unified_data", return_value=recovered):
        assert (await coordinator._async_update_data())["buy"]["current_price"] == 0.8
    assert (await coordinator._load_cache())["buy"]["current_price"] == 0.8


@pytest.mark.parametrize(
    ("first", "second", "local_hour", "offset"),
    [
        ("2026-09-22T21:00:00+00:00", "2026-09-22T22:00:00+00:00", 0, 2),
        ("2026-03-29T00:00:00+00:00", "2026-03-29T01:00:00+00:00", 3, 2),
        ("2026-10-25T00:00:00+00:00", "2026-10-25T01:00:00+00:00", 2, 1),
    ],
    ids=["midnight", "spring-dst", "autumn-dst"],
)
async def test_cache_rollover_uses_absolute_time(
    coordinator, freezer, first, second, local_hour, offset
):
    freezer.move_to(first)
    raw = {"frames": [
        frame(first, "0.5", "0.1", cheap=True),
        frame(second, "1.5", "0.9", expensive=True),
    ]}
    with patch.object(coordinator, "_fetch_unified_data", return_value=raw):
        await coordinator._async_update_data()

    freezer.move_to(second)
    with patch.object(coordinator, "_fetch_unified_data", side_effect=asyncio.TimeoutError):
        data = await coordinator._async_update_data()
    assert dt_util.now().hour == local_hour
    assert dt_util.now().utcoffset() == timedelta(hours=offset)
    for branch, price in [("buy", 1.5), ("sell", 0.9)]:
        assert data[branch]["current_price"] == price
        assert data[branch]["is_expensive"] is True
        assert data[branch]["is_cheap"] is False
        assert data[branch]["has_future_data"] is False


@pytest.mark.parametrize("cache", [None, "invalid json"])
async def test_outage_without_usable_cache_fails(coordinator, cache):
    if cache is not None:
        await asyncio.to_thread(
            Path(coordinator._cache_file).write_text, cache, encoding="utf-8"
        )
    with patch.object(coordinator, "_fetch_unified_data", side_effect=aiohttp.ClientError):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors_are_not_hidden_by_cache(coordinator, status):
    await coordinator._save_cache({"buy": {"current_price": 0.7}})
    response = MagicMock(status=status)
    coordinator._session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_restart_during_outage_uses_cache(
    hass, entry, coordinator, freezer, enable_custom_integrations
):
    freezer.move_to("2026-09-22T07:00:00+00:00")
    raw = {"frames": [
        frame("2026-09-22T07:00:00+00:00", "0.7", "0.2"),
        frame("2026-09-22T08:00:00+00:00", "1.23", "0.6", expensive=True),
    ]}
    with patch.object(coordinator, "_fetch_unified_data", return_value=raw):
        await coordinator._async_update_data()
    freezer.move_to("2026-09-22T08:00:00+00:00")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.pstryk.coordinator.PstrykDataUpdateCoordinator._fetch_unified_data",
        side_effect=asyncio.TimeoutError,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.data["buy"]["current_price"] == 1.23
        assert entry.runtime_data.data["sell"]["current_price"] == 0.6
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_timeout_crossing_hour_uses_time_after_request(coordinator, freezer):
    freezer.move_to("2026-09-22T07:30:00+00:00")
    raw = {"frames": [
        frame("2026-09-22T07:00:00+00:00", "0.7", "0.2", cheap=True),
        frame("2026-09-22T08:00:00+00:00", "1.23", "0.6", expensive=True),
    ]}
    with patch.object(coordinator, "_fetch_unified_data", return_value=raw):
        await coordinator._async_update_data()

    async def timeout(*args):
        freezer.tick(timedelta(seconds=30))
        raise asyncio.TimeoutError

    freezer.move_to("2026-09-22T07:59:50+00:00")
    with patch.object(coordinator, "_fetch_unified_data", side_effect=timeout):
        data = await coordinator._async_update_data()
    assert data["buy"]["current_price"] == 1.23
    assert data["sell"]["current_price"] == 0.6
    assert data["buy"]["is_expensive"] is True


async def test_registered_entities_advance_on_scheduled_outage_refresh(
    hass, entry, freezer, enable_custom_integrations
):
    """Exercise HA scheduling, listeners and entity states, not only parsing."""
    freezer.move_to("2026-09-22T07:00:00+00:00")
    entry.add_to_hass(hass)
    raw = {"frames": [
        frame("2026-09-22T07:00:00+00:00", "0.7", "0.2", cheap=True),
        frame("2026-09-22T08:00:00+00:00", "1.23", "0.6", expensive=True),
        frame("2026-09-22T09:00:00+00:00", "0", "-0.125", cheap=True),
    ]}
    with patch(
        "custom_components.pstryk.coordinator.PstrykDataUpdateCoordinator._fetch_unified_data",
        return_value=raw,
    ) as fetch:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)

        def state(domain, unique_id):
            entity_id = registry.async_get_entity_id(domain, "pstryk", unique_id)
            return hass.states.get(entity_id)

        assert state("sensor", "pstryk_buy_price").state == "0.7"
        assert state("binary_sensor", "pstryk_buy_cheap_hour").state == "on"
        fetch.side_effect = asyncio.TimeoutError
        for now, buy, sell, cheap, expensive, next_buy, next_sell in [
            ("08:00:01", "1.23", "0.6", "off", "on", "0.0", "-0.125"),
            ("09:00:02", "0.0", "-0.125", "on", "off", "unknown", "unknown"),
            ("10:00:03", "unknown", "unknown", "off", "off", "unknown", "unknown"),
        ]:
            freezer.move_to(f"2026-09-22T{now}+00:00")
            async_fire_time_changed(hass, dt_util.utcnow())
            await hass.async_block_till_done(wait_background_tasks=True)
            assert state("sensor", "pstryk_buy_price").state == buy
            assert state("sensor", "pstryk_sell_price").state == sell
            assert state("sensor", "pstryk_buy_price_next_hour").state == next_buy
            assert state("sensor", "pstryk_sell_price_next_hour").state == next_sell
            for side in ("buy", "sell"):
                assert state("binary_sensor", f"pstryk_{side}_cheap_hour").state == cheap
                assert state("binary_sensor", f"pstryk_{side}_expensive_hour").state == expensive
        assert fetch.await_count == 4
        assert await hass.config_entries.async_unload(entry.entry_id)
