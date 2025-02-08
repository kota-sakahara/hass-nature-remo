"""The Nature Remo integration."""
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)
_RESOURCE = "https://api.nature.global/1"

DOMAIN = "nature_remo"

CONF_COOL_TEMP = "cool_temperature"
CONF_HEAT_TEMP = "heat_temperature"
DEFAULT_COOL_TEMP = 28
DEFAULT_HEAT_TEMP = 20
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=60)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ACCESS_TOKEN): cv.string,
                vol.Optional(CONF_COOL_TEMP, default=DEFAULT_COOL_TEMP): vol.Coerce(int),
                vol.Optional(CONF_HEAT_TEMP, default=DEFAULT_HEAT_TEMP): vol.Coerce(int),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up Nature Remo component."""
    _LOGGER.debug("Setting up Nature Remo component.")
    # 1) まず DataUpdateCoordinator を作成
    access_token = config[DOMAIN][CONF_ACCESS_TOKEN]
    session = async_get_clientsession(hass)
    api = NatureRemoAPI(access_token, session)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Nature Remo update",
        update_method=api.get,
        update_interval=DEFAULT_UPDATE_INTERVAL,
    )

    # 2) データを先にフェッチ（トークン不良などがあればここで例外になります）
    await coordinator.async_refresh()

    # 3) hass.data にまとめて格納
    hass.data[DOMAIN] = {
        "api": api,
        "coordinator": coordinator,
        "config": config[DOMAIN],
    }

    # 4) discovery.async_load_platform でプラットフォーム読み込み（旧来の方法）
    await discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "climate", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "light", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "switch", DOMAIN, {}, config)

    return True


class NatureRemoAPI:
    """Nature Remo API client."""

    def __init__(self, access_token, session):
        """Init API client."""
        self._access_token = access_token
        self._session = session

    async def get(self):
        """Get appliance and device list."""
        _LOGGER.debug("Trying to fetch appliance and device list from API.")
        headers = {"Authorization": f"Bearer {self._access_token}"}

        # appliances
        resp_app = await self._session.get(f"{_RESOURCE}/appliances", headers=headers)
        appliances_json = await resp_app.json()
        appliances = {x["id"]: x for x in appliances_json}

        # devices
        resp_dev = await self._session.get(f"{_RESOURCE}/devices", headers=headers)
        devices_json = await resp_dev.json()
        devices = {x["id"]: x for x in devices_json}

        return {"appliances": appliances, "devices": devices}

    async def post(self, path, data):
        """Post any request."""
        _LOGGER.debug("Trying to request post: %s, data: %s", path, data)
        headers = {"Authorization": f"Bearer {self._access_token}"}
        response = await self._session.post(
            f"{_RESOURCE}{path}", data=data, headers=headers
        )
        return await response.json()

    async def getany(self, path):
        """Get any request."""
        _LOGGER.debug("Trying to request get: %s", path)
        headers = {"Authorization": f"Bearer {self._access_token}"}
        response = await self._session.get(f"{_RESOURCE}{path}", headers=headers)
        # 例としてレスポンスをそのまま返す
        return await response.json()


class NatureRemoBase(Entity):
    """Nature Remo entity base class."""

    def __init__(self, coordinator, appliance):
        self._coordinator = coordinator
        self._name = f"Nature Remo {appliance['nickname']}"
        self._appliance_id = appliance["id"]
        self._device = appliance["device"]

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._appliance_id

    @property
    def should_poll(self):
        # DataUpdateCoordinator を使うためポーリング不要
        return False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device["id"])},
            "name": self._device["name"],
            "manufacturer": "Nature Remo",
            "model": self._device["serial_number"],
            "sw_version": self._device["firmware_version"],
        }


class NatureRemoDeviceBase(Entity):
    """Nature Remo Device entity base class."""

    def __init__(self, coordinator, device):
        self._coordinator = coordinator
        self._name = f"Nature Remo {device['name']}"
        self._device = device

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._device["id"]

    @property
    def should_poll(self):
        # 通常は DataUpdateCoordinator による更新を使うため False
        return False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device["id"])},
            "name": self._device["name"],
            "manufacturer": "Nature Remo",
            "model": self._device["serial_number"],
            "sw_version": self._device["firmware_version"],
        }

    async def async_added_to_hass(self):
        """Subscribe to updates from the coordinator."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity (generic service)."""
        await self._coordinator.async_request_refresh()
