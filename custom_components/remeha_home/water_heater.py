"""Platform for DHW control."""

from __future__ import annotations
from typing import Any

from homeassistant.components.water_heater import (
    STATE_HIGH_DEMAND,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_HALVES, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RemehaHomeAPI
from .const import DOMAIN
from .coordinator import RemehaHomeUpdateCoordinator

REMEHA_DHW_MODE_TO_OPERATION = {
    "ContinuousComfort": "comfort",
    "Schedule": "schedule",
    "Off": "eco",
}

OPERATION_TO_REMEHA_DHW_MODE = {
    "comfort": "ContinuousComfort",
    "schedule": "Schedule",
    "eco": "Off",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DHW water heater entities from a config entry."""
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for appliance in coordinator.data["appliances"]:
        appliance_id = appliance["applianceId"]
        for hot_water_zone in appliance["hotWaterZones"]:
            hot_water_zone_id = hot_water_zone["hotWaterZoneId"]
            entities.append(
                RemehaHomeWaterHeater(api, coordinator, appliance_id, hot_water_zone_id)
            )

    async_add_entities(entities)


class RemehaHomeWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Water heater entity representing a DHW zone."""

    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "remeha_home_dhw"
    _attr_has_entity_name = True
    _attr_name = None
    _attr_precision = PRECISION_HALVES

    def __init__(
        self,
        api: RemehaHomeAPI,
        coordinator: RemehaHomeUpdateCoordinator,
        appliance_id: str,
        hot_water_zone_id: str,
    ) -> None:
        """Create a DHW water heater entity."""
        super().__init__(coordinator)
        self.api = api
        self.appliance_id = appliance_id
        self.hot_water_zone_id = hot_water_zone_id
        self._attr_unique_id = "_".join([DOMAIN, self.hot_water_zone_id, "water_heater"])

    @property
    def _data(self) -> dict:
        """Return the DHW zone information."""
        return self.coordinator.get_by_id(self.hot_water_zone_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        return self.coordinator.get_device_info(self.hot_water_zone_id)

    @property
    def current_operation(self) -> str | None:
        """Return the current operation mode."""
        return REMEHA_DHW_MODE_TO_OPERATION.get(self._data.get("dhwZoneMode"), "eco")

    @property
    def operation_list(self) -> list[str]:
        """Return the list of available operation modes."""
        return ["eco", "comfort", "schedule"]

    @property
    def state(self) -> str | None:
        """Return a state that reflects heating activity when available."""
        dhw_status = self._data.get("dhwStatus")
        if dhw_status in ("ProducingHeat", "RequestingHeat"):
            return STATE_HIGH_DEMAND
        if dhw_status == "LowTemperature":
            return "low_temperature"
        return self.current_operation

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature based on the active setpoint."""
        setpoint_type = self._active_setpoint_type()
        if setpoint_type == "comfort":
            return self._data.get("comfortSetPoint")
        if setpoint_type == "eco":
            return self._data.get("reducedSetpoint")
        return self._data.get("targetSetpoint")

    @property
    def current_temperature(self) -> float | None:
        """Return the current DHW temperature."""
        return self._data.get("dhwTemperature")

    @property
    def min_temp(self) -> float | None:
        """Return the minimum setpoint across comfort/eco ranges."""
        ranges = self._data.get("setPointRanges") or {}
        candidates = [
            ranges.get("comfortSetpointMin"),
            ranges.get("reducedSetpointMin"),
            self._data.get("setPointMin"),
        ]
        return min(value for value in candidates if value is not None)

    @property
    def max_temp(self) -> float | None:
        """Return the maximum setpoint across comfort/eco ranges."""
        ranges = self._data.get("setPointRanges") or {}
        candidates = [
            ranges.get("comfortSetpointMax"),
            ranges.get("reducedSetpointMax"),
            self._data.get("setPointMax"),
        ]
        return max(value for value in candidates if value is not None)

    def _active_setpoint_type(self) -> str:
        """Guess which setpoint is currently active."""
        mode = self._data.get("dhwZoneMode")
        if mode == "ContinuousComfort":
            return "comfort"
        if mode == "Schedule":
            target = self._data.get("targetSetpoint")
            comfort = self._data.get("comfortSetPoint")
            reduced = self._data.get("reducedSetpoint")
            if comfort is not None and target is not None and abs(target - comfort) < 0.25:
                return "comfort"
            if reduced is not None and target is not None and abs(target - reduced) < 0.25:
                return "eco"
            return "comfort"
        return "eco"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes for diagnostics."""
        return {
            "dhw_status": self._data.get("dhwStatus"),
            "boost_mode_end_time": self._data.get("boostModeEndTime"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature for the active setpoint."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        setpoint_type = self._active_setpoint_type()
        if setpoint_type == "comfort":
            await self.api.async_set_dhw_comfort_setpoint(
                self.hot_water_zone_id, temperature
            )
        else:
            await self.api.async_set_dhw_reduced_setpoint(
                self.hot_water_zone_id, temperature
            )

        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set operation mode."""
        target_mode = OPERATION_TO_REMEHA_DHW_MODE.get(operation_mode)
        if not target_mode:
            return

        if target_mode == "ContinuousComfort":
            await self.api.async_set_dhw_mode_comfort(self.hot_water_zone_id)
        elif target_mode == "Schedule":
            await self.api.async_set_dhw_mode_schedule(self.hot_water_zone_id)
        elif target_mode == "Off":
            await self.api.async_set_dhw_mode_eco(self.hot_water_zone_id)
        else:
            return

        # Optimistic update until the coordinator polls fresh data
        self._data["dhwZoneMode"] = target_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
