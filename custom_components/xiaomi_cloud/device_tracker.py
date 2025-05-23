"""Support for the Xiaomi device tracking."""
import logging

from homeassistant.components.device_tracker.config_entry import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    DOMAIN,
    COORDINATOR,
    SIGNAL_STATE_UPDATED
)


_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Configure a dispatcher connection based on a config entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    devices = []
    
    # Check if coordinator has valid data
    if not coordinator.data or not isinstance(coordinator.data, list) or len(coordinator.data) == 0:
        _LOGGER.debug("No device data available yet. Device will be set up when data becomes available.")
        return
        
    for i in range(len(coordinator.data)):
        devices.append(XiaomiDeviceEntity(hass, coordinator, i))
        _LOGGER.debug("device is : %s", i)
    
    async_add_entities(devices, True)

class XiaomiDeviceEntity(TrackerEntity, RestoreEntity, Entity):
    """Represent a tracked device."""

    def __init__(self, hass, coordinator, vin) -> None:
        """Set up Geofency entity."""
        self._hass = hass
        self._vin = vin
        self.coordinator = coordinator  
        self._unique_id = coordinator.data[vin]["imei"]    
        
        # Format model name to create entity ID in the desired format
        model = coordinator.data[vin]["model"]
        if model:
            # Remove spaces and replace with underscores, remove special characters
            formatted_model = model.replace(" ", "_").lower()
            self._name = formatted_model
        else:
            self._name = f"xiaomi_device_{vin}"
            
        self._icon = "mdi:map-marker"
        self.sw_version = coordinator.data[vin]["version"]
        self._last_lat = coordinator.data[vin].get("device_lat")
        self._last_lon = coordinator.data[vin].get("device_lon")
        self._last_accuracy = coordinator.data[vin].get("device_accuracy")
        self._last_update_time = coordinator.data[vin].get("device_location_update_time")
        self._last_coordinate_type = coordinator.data[vin].get("coordinate_type")
        self._last_device_phone = coordinator.data[vin].get("device_phone")

    async def async_update(self):
        """Update Colorfulclouds entity."""   
        _LOGGER.debug("async_update")
        await self.coordinator.async_request_refresh()
    async def async_added_to_hass(self):
        """Subscribe for update from the hub"""

        _LOGGER.debug("device_tracker_unique_id: %s", self._unique_id)

        async def async_update_state():
            """Update sensor state."""
            await self.async_update_ha_state(True)

        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        
    @property
    def battery_level(self):
        """Return battery value of the device."""
        data = self.coordinator.data
        if not isinstance(data, list) or self._vin >= len(data):
            _LOGGER.debug("coordinator.data is not a list or index is out of range: %s", data)
            return None
        return data[self._vin].get("device_power")

    @property
    def device_state_attributes(self):
        """Return device specific attributes."""
        data = self.coordinator.data
        if not isinstance(data, list) or self._vin >= len(data):
            _LOGGER.debug("coordinator.data is not a list or index out of range: %s", data)
            attrs = {}
            if self._last_update_time:
                attrs["last_update"] = self._last_update_time
            if self._last_coordinate_type:
                attrs["coordinate_type"] = self._last_coordinate_type
            if self._last_device_phone:
                attrs["device_phone"] = self._last_device_phone
            attrs["imei"] = self._unique_id
            return attrs
            
        device_data = data[self._vin]
        attrs = {}
        update_time = device_data.get("device_location_update_time")
        if update_time:
            attrs["last_update"] = update_time
            self._last_update_time = update_time
        
        coordinate_type = device_data.get("coordinate_type")
        if coordinate_type:
            attrs["coordinate_type"] = coordinate_type
            self._last_coordinate_type = coordinate_type
            
        device_phone = device_data.get("device_phone")
        if device_phone:
            attrs["device_phone"] = device_phone
            self._last_device_phone = device_phone
            
        attrs["imei"] = device_data.get("imei", self._unique_id)

        return attrs

    @property
    def latitude(self):
        """Return latitude value of the device."""
        data = self.coordinator.data
        if not isinstance(data, list) or self._vin >= len(data):
            _LOGGER.debug("coordinator.data is not list or index out of range: %s", data)
            return self._last_lat

        device_data = data[self._vin]
        lat = device_data.get("device_lat")
        if lat is None:
            return self._last_lat
        self._last_lat = lat
        return lat

    @property
    def longitude(self):
        """Return longitude value of the device."""
        data = self.coordinator.data
        if not isinstance(data, list) or self._vin >= len(data):
            _LOGGER.debug("coordinator.data is not a list or index out of range: %s", data)
            return self._last_lon

        device_data = data[self._vin]
        lon = device_data.get("device_lon")
        if lon is None:
            return self._last_lon
        self._last_lon = lon
        return lon

    @property
    def location_accuracy(self):
        """Return the gps accuracy of the device."""
        data = self.coordinator.data
        if not isinstance(data, list) or self._vin >= len(data):
            _LOGGER.debug("coordinator.data is not a list or index out of range: %s", data)
            return self._last_accuracy
            
        accuracy = data[self._vin].get("device_accuracy")
        if accuracy is not None:
            self._last_accuracy = accuracy
        return self._last_accuracy

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def name(self):
        """Return the name of the device."""
        data = self.coordinator.data
        if not isinstance(data, list) or self._vin >= len(data):
            _LOGGER.debug("coordinator.data is not a list or index out of range: %s", data)
            return self._name
            
        model = data[self._vin].get("model")
        if model:
            # Format model name according to requirements
            formatted_model = model.replace(" ", "_").lower()
            return formatted_model
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID."""
        return self._unique_id
    
    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self._name,
            "manufacturer": "Xiaomi",
            "entry_type": DeviceEntryType.SERVICE, 
            "sw_version": self.sw_version,
            "model": self._name
        }


    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return False

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

        

