"""Platform for DHW boost control."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RemehaHomeAPI
from .const import DOMAIN
from .coordinator import RemehaHomeUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up DHW boost buttons from a config entry."""
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[RemehaHomeBoostButton] = []
    for appliance in coordinator.data["appliances"]:
        appliance_id = appliance["applianceId"]
        for hot_water_zone in appliance["hotWaterZones"]:
            if not hot_water_zone.get("capabilityBoostMode", False):
                continue
            hot_water_zone_id = hot_water_zone["hotWaterZoneId"]
            entities.append(
                RemehaHomeBoostButton(
                    api,
                    coordinator,
                    appliance_id,
                    hot_water_zone_id,
                )
            )

    async_add_entities(entities)


class RemehaHomeBoostButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger DHW boost."""

    _attr_has_entity_name = True
    _attr_name = "Boost"
    _attr_icon = "mdi:water-boiler"

    def __init__(
        self,
        api: RemehaHomeAPI,
        coordinator: RemehaHomeUpdateCoordinator,
        appliance_id: str,
        hot_water_zone_id: str,
    ) -> None:
        """Create a DHW boost button."""
        super().__init__(coordinator)
        self.api = api
        self.appliance_id = appliance_id
        self.hot_water_zone_id = hot_water_zone_id
        self._attr_unique_id = "_".join(
            [DOMAIN, self.hot_water_zone_id, "boost_button"]
        )

    @property
    def _data(self):
        """Return data for this zone."""
        return self.coordinator.get_by_id(self.hot_water_zone_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        return self.coordinator.get_device_info(self.hot_water_zone_id)

    async def async_press(self) -> None:
        """Trigger the boost mode."""
        duration = self._data.get("boostDuration") or 30
        await self.api.async_trigger_hot_water_boost(self.appliance_id, duration)
        await self.coordinator.async_request_refresh()
