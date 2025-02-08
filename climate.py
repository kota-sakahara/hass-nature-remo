import logging
from homeassistant.core import callback
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE
# from homeassistant.const import UnitOfTemperature  # バージョンによっては使えない場合があるので要注意

from . import DOMAIN, CONF_COOL_TEMP, CONF_HEAT_TEMP, NatureRemoBase

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.SWING_MODE
)

MODE_HA_TO_REMO = {
    HVACMode.AUTO: "auto",
    HVACMode.FAN_ONLY: "blow",
    HVACMode.COOL: "cool",
    HVACMode.DRY: "dry",
    HVACMode.HEAT: "warm",
    HVACMode.OFF: "power-off",
}

MODE_REMO_TO_HA = {
    "auto": HVACMode.AUTO,
    "blow": HVACMode.FAN_ONLY,
    "cool": HVACMode.COOL,
    "dry": HVACMode.DRY,
    "warm": HVACMode.HEAT,
    "power-off": HVACMode.OFF,
}

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    if discovery_info is None:
        return
    _LOGGER.debug("Setting up climate platform.")

    coordinator = hass.data[DOMAIN]["coordinator"]
    api = hass.data[DOMAIN]["api"]
    domain_config = hass.data[DOMAIN]["config"]
    appliances = coordinator.data["appliances"]
    entities = []

    for appliance in appliances.values():
        if appliance["type"] == "AC":
            entities.append(NatureRemoAC(coordinator, api, appliance, domain_config))

    async_add_entities(entities)


class NatureRemoAC(NatureRemoBase, ClimateEntity):
    """Implementation of a Nature Remo AC."""

    def __init__(self, coordinator, api, appliance, config):
        super().__init__(coordinator, appliance)
        self._api = api
        self._default_temp = {
            HVACMode.COOL: config[CONF_COOL_TEMP],
            HVACMode.HEAT: config[CONF_HEAT_TEMP],
        }
        self._modes = appliance["aircon"]["range"]["modes"]
        self._hvac_mode = None
        self._current_temperature = None
        self._target_temperature = None
        self._remo_mode = None
        self._fan_mode = None
        self._swing_mode = None
        self._last_target_temperature = {v: None for v in MODE_REMO_TO_HA}
        # ↓コンストラクタ最後で _update() を呼ぶ
        self._update(appliance["settings"], None)

    def _update(self, ac_settings, device):
        """Handle internal update of AC settings and device states."""
        self._remo_mode = ac_settings["mode"]
        try:
            self._target_temperature = float(ac_settings["temp"])
            self._last_target_temperature[self._remo_mode] = ac_settings["temp"]
        except (ValueError, KeyError, TypeError):
            self._target_temperature = None

        if ac_settings.get("button") == MODE_HA_TO_REMO[HVACMode.OFF]:
            self._hvac_mode = HVACMode.OFF
        else:
            self._hvac_mode = MODE_REMO_TO_HA.get(self._remo_mode, HVACMode.OFF)

        self._fan_mode = ac_settings.get("vol") or None
        self._swing_mode = ac_settings.get("dir") or None

        if device and device.get("newest_events", {}).get("te"):
            try:
                self._current_temperature = float(device["newest_events"]["te"]["val"])
            except ValueError:
                self._current_temperature = None

    @property
    def supported_features(self):
        return SUPPORT_FLAGS

    @property
    def current_temperature(self):
        return self._current_temperature

    @property
    def temperature_unit(self):
        # バージョンによっては UnitOfTemperature.CELSIUS が使えない場合がある
        # その場合は単純に "°C" を返してください。
        return "°C"

    @property
    def min_temp(self):
        temp_range = self._current_mode_temp_range()
        return min(temp_range) if temp_range else 0

    @property
    def max_temp(self):
        temp_range = self._current_mode_temp_range()
        return max(temp_range) if temp_range else 0

    @property
    def target_temperature(self):
        return self._target_temperature

    @property
    def target_temperature_step(self):
        temp_range = self._current_mode_temp_range()
        if len(temp_range) >= 2:
            step = round(temp_range[1] - temp_range[0], 1)
            if step in [1.0, 0.5]:
                return step
        return 1

    @property
    def hvac_mode(self):
        return self._hvac_mode

    @property
    def hvac_modes(self):
        remo_modes = list(self._modes.keys())
        ha_modes = [MODE_REMO_TO_HA[m] for m in remo_modes]
        ha_modes.append(HVACMode.OFF)
        return ha_modes

    @property
    def fan_mode(self):
        return self._fan_mode

    @property
    def fan_modes(self):
        return self._modes[self._remo_mode]["vol"]

    @property
    def swing_mode(self):
        return self._swing_mode

    @property
    def swing_modes(self):
        return self._modes[self._remo_mode]["dir"]

    @property
    def extra_state_attributes(self):
        return {
            "previous_target_temperature": self._last_target_temperature,
        }

    async def async_set_temperature(self, **kwargs):
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is None:
            return
        if isinstance(target_temp, float) and target_temp.is_integer():
            target_temp = int(target_temp)
        _LOGGER.debug("Set temperature: %s", target_temp)
        await self._post({"temperature": f"{target_temp}"})

    async def async_set_hvac_mode(self, hvac_mode):
        _LOGGER.debug("Set hvac mode: %s", hvac_mode)
        mode = MODE_HA_TO_REMO[hvac_mode]
        if mode == MODE_HA_TO_REMO[HVACMode.OFF]:
            await self._post({"button": mode})
        else:
            data = {"operation_mode": mode}
            if self._last_target_temperature.get(mode):
                data["temperature"] = self._last_target_temperature[mode]
            elif self._default_temp.get(hvac_mode):
                data["temperature"] = self._default_temp[hvac_mode]
            await self._post(data)

    async def async_set_fan_mode(self, fan_mode):
        _LOGGER.debug("Set fan mode: %s", fan_mode)
        await self._post({"air_volume": fan_mode})

    async def async_set_swing_mode(self, swing_mode):
        _LOGGER.debug("Set swing mode: %s", swing_mode)
        await self._post({"air_direction": swing_mode})

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self._update_callback)
        )

    async def async_update(self):
        """Request coordinator refresh."""
        await self._coordinator.async_request_refresh()

    @callback
    def _update_callback(self):
        """Called by coordinator listener. Update from latest data."""
        data = self._coordinator.data
        # coordinator.data から最新のアプライアンス設定とデバイス状態をとる
        if not data:
            return
        appliance = data["appliances"].get(self._appliance_id, {})
        ac_settings = appliance.get("settings", {})
        device_id = None
        if "device" in appliance:
            device_id = appliance["device"]["id"]

        device = data["devices"].get(device_id, {}) if device_id else {}
        self._update(ac_settings, device)
        self.async_write_ha_state()

    async def _post(self, data):
        response = await self._api.post(f"/appliances/{self._appliance_id}/aircon_settings", data)
        # レスポンスには最新設定が返ってくる想定なので反映させる
        if "mode" in response:
            # responseがエラーの場合などは無いかもしれない
            self._update(response, None)
        self.async_write_ha_state()

    def _current_mode_temp_range(self):
        if self._remo_mode not in self._modes:
            return []
        temp_range = self._modes[self._remo_mode].get("temp", [])
        result = []
        for t in temp_range:
            # t is None / '' / or a real string
            if not t:  # None や '' を弾く
                continue
            try:
                result.append(float(t))
            except ValueError:
                # 変換できない文字列もスキップ
                pass
        return result
