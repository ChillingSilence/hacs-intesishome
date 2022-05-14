# pylint: disable=duplicate-code
"""Config flow for IntesisHome."""
import logging

from pyintesishome import (
    IHAuthenticationError,
    IHConnectionError,
    IntesisBase,
    IntesisBox,
    IntesisHome,
    IntesisHomeLocal,
)

from pyintesishome.const import (
    DEVICE_AIRCONWITHME,
    DEVICE_INTESISBOX,
    DEVICE_INTESISHOME,
    DEVICE_INTESISHOME_LOCAL,
)
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntesisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IntesisHome."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial device type selection step."""
        # unique_id = user_input["unique_id"]
        # await self.async_set_unique_id(unique_id)
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_DEVICE]:
                return await self.async_step_details(
                    device_type=user_input[CONF_DEVICE]
                )

        device_type_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=DEVICE_INTESISHOME): vol.In(
                    [
                        DEVICE_AIRCONWITHME,
                        DEVICE_INTESISHOME,
                        DEVICE_INTESISBOX,
                        DEVICE_INTESISHOME_LOCAL,
                    ]
                )
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=device_type_schema, errors=errors
        )

    async def async_step_details(self, user_input=None, device_type=None):
        """Handle the device connection step."""
        cloud_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=device_type): vol.In(
                    [DEVICE_AIRCONWITHME, DEVICE_INTESISHOME]
                ),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        local_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=device_type): vol.In(
                    [DEVICE_INTESISBOX, DEVICE_INTESISHOME_LOCAL]
                ),
                vol.Required(CONF_HOST): str,
            }
        )
        local_auth_schema = local_schema.extend(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        errors: dict[str, str] = {}

        if user_input is None:
            return

        controller: IntesisBase = None
        try:
            if user_input[CONF_DEVICE] == DEVICE_INTESISBOX:
                controller = IntesisBox(user_input[CONF_HOST], loop=self.hass.loop)
                await controller.connect()
            elif user_input[CONF_DEVICE] == DEVICE_INTESISHOME_LOCAL:
                controller = IntesisHomeLocal(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    loop=self.hass.loop,
                    websession=async_get_clientsession(self.hass),
                )
                await controller.poll_status()
            else:
                controller = IntesisHome(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    loop=self.hass.loop,
                    websession=async_get_clientsession(self.hass),
                )
                await controller.poll_status()
        except IHAuthenticationError:
            errors["base"] = "invalid_auth"
        except IHConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        if len(controller.get_devices()) == 0:
            errors["base"] = "no_devices"

        if "base" not in errors:
            unique_id = f"{controller.device_type}_{controller.controller_id}".lower()
            name = f"{controller.device_type} {controller.name}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Pass the controller through to the platform setup
            self.hass.data.setdefault(DOMAIN, {})
            self.hass.data[DOMAIN].setdefault("controller", {})
            self.hass.data[DOMAIN]["controller"][unique_id] = controller

            return self.async_create_entry(
                title=name,
                data=user_input,
            )

        # Preserve device type if provided via user input
        if user_input:
            device_type = user_input.get(CONF_DEVICE, None)

        # Show the correct configuration schema
        if device_type == DEVICE_INTESISBOX:
            return self.async_show_form(
                step_id="details", data_schema=local_schema, errors=errors
            )
        if device_type == DEVICE_INTESISHOME_LOCAL:
            return self.async_show_form(
                step_id="details", data_schema=local_auth_schema, errors=errors
            )
        return self.async_show_form(
            step_id="details", data_schema=cloud_schema, errors=errors
        )

    async def async_step_import(self, import_data) -> FlowResult:
        """Handle configuration by yaml file."""
        return await self.async_step_user(import_data)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class NoDevices(exceptions.HomeAssistantError):
    """Error to indicate the account has no devices."""
