"""Support for Nature Remo E energy sensor."""
import logging
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE
from . import DOMAIN, NatureRemoBase, NatureRemoDeviceBase

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    if discovery_info is None:
        return
    _LOGGER.debug("Setting up sensor platform.")
    coordinator = hass.data[DOMAIN]["coordinator"]
    appliances = coordinator.data["appliances"]
    devices = coordinator.data["devices"]
    entities = [
        NatureRemoE(coordinator, appliance)
        for appliance in appliances.values()
        if appliance["type"] == "EL_SMART_METER"
    ]
    for device in devices.values():
        for sensor in device["newest_events"].keys():
            if sensor == "te":
                entities.append(NatureRemoTemperatureSensor(coordinator, device))
            elif sensor == "hu":
                entities.append(NatureRemoHumiditySensor(coordinator, device))
            elif sensor == "il":
                entities.append(NatureRemoIlluminanceSensor(coordinator, device))
    async_add_entities(entities)

class NatureRemoE(NatureRemoBase):
    """Implementation of a Nature Remo E sensor."""

    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._unit_of_measurement = "W"  # 直接文字列を指定

    @property
    def state(self):
        appliance = self._coordinator.data["appliances"][self._appliance_id]
        echonetlite_properties = appliance["smart_meter"]["echonetlite_properties"]
        measured_instantaneous = next(
            v["val"] for v in echonetlite_properties if v["epc"] == 231
        )
        _LOGGER.debug("Current state: %sW", measured_instantaneous)
        return measured_instantaneous

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def device_class(self):
        return SensorDeviceClass.POWER

    async def async_added_to_hass(self):
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        await self._coordinator.async_request_refresh()

class NatureRemoTemperatureSensor(NatureRemoDeviceBase):
    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._name = self._name.strip() + " Temperature"

    @property
    def unique_id(self):
        return self._device["id"] + "-te"

    @property
    def unit_of_measurement(self):
        return "°C"  # 列挙が無ければ文字列で指定

    @property
    def state(self):
        device = self._coordinator.data["devices"][self._device["id"]]
        return device["newest_events"]["te"]["val"]

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

class NatureRemoHumiditySensor(NatureRemoDeviceBase):
    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._name = self._name.strip() + " Humidity"

    @property
    def unique_id(self):
        return self._device["id"] + "-hu"

    @property
    def unit_of_measurement(self):
        return PERCENTAGE  # これは比較的古いバージョンでも残っている

    @property
    def state(self):
        device = self._coordinator.data["devices"][self._device["id"]]
        return device["newest_events"]["hu"]["val"]

    @property
    def device_class(self):
        return SensorDeviceClass.HUMIDITY

class NatureRemoIlluminanceSensor(NatureRemoDeviceBase):
    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._name = self._name.strip() + " Illuminance"

    @property
    def unique_id(self):
        return self._device["id"] + "-il"

    @property
    def unit_of_measurement(self):
        return "lx"  # 列挙が無ければ文字列で指定

    @property
    def state(self):
        device = self._coordinator.data["devices"][self._device["id"]]
        return device["newest_events"]["il"]["val"]

    @property
    def device_class(self):
        return SensorDeviceClass.ILLUMINANCE
