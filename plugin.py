"""
<plugin key="HWBatteryControl" name="HomeWizard Battery Control" author="Christian" version="1.0.6">
    <params>
        <param field="Address" label="IP Address" width="200px" required="true"/>
        <param field="Port" label="Port" width="75px" required="true" default="443"/>
        <param field="Password" label="API Key" width="200px" required="true" password="true"/>

        <param field="Mode1" label="Polling Interval (sec)" width="75px">
            <options>
                <option label="2" value="2"/>
                <option label="5" value="5" default="true"/>
                <option label="10" value="10"/>
                <option label="20" value="20"/>
                <option label="30" value="30"/>
            </options>
        </param>

        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="Off" value="0" default="true"/>
                <option label="On" value="1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import json
import urllib.request
import ssl

class BasePlugin:
    def __init__(self):
        self.pluginInterval = 1
        self.dataInterval = 5
        self.dataIntervalCount = 0
        self.api_url = ""
        self.api_info_url = ""
        self.api_token = ""
        self.debug = False
        self.is_modern = False
        self.last_permissions = []

    def log(self, msg):
        if self.debug:
            Domoticz.Log("[DEBUG] " + msg)

    def onStart(self):
        self.dataInterval = int(Parameters["Mode1"])
        self.api_token = Parameters["Password"]
        self.debug = Parameters["Mode6"] == "1"

        ip = Parameters["Address"]
        port = Parameters["Port"]

        self.api_url = f"https://{ip}:{port}/api/batteries"
        self.api_info_url = f"https://{ip}:{port}/api"

        Domoticz.Log(f"HomeWizard Battery Control started, data interval = {self.dataInterval}s")
        Domoticz.Heartbeat(self.pluginInterval)

        self._createDevices()
        self._detectApiVersion()

    def _createDevices(self):
        if 1 not in Devices:
            Domoticz.Device(
                Name="Battery Mode",
                Unit=1,
                Type=244,
                Subtype=62,
                Switchtype=18,
                Options={
                    "LevelActions": "||||",
                    "LevelNames": "Standby|Zero|Predictive|To-Full",
                    "LevelOffHidden": "false",
                    "SelectorStyle": "0"
                },
                Description="Select the operating mode of the HomeWizard battery cluster."
            ).Create()
            Devices[1].Update(nValue=0, sValue="0")

        if 2 not in Devices:
            Domoticz.Device(
                Name="Charge Allowed",
                Unit=2,
                Type=244,
                Subtype=73,
                Switchtype=0,
                Description="Indicates whether the battery is allowed to charge."
            ).Create()

        if 3 not in Devices:
            Domoticz.Device(
                Name="Discharge Allowed",
                Unit=3,
                Type=244,
                Subtype=73,
                Switchtype=0,
                Description="Indicates whether the battery is allowed to discharge."
            ).Create()

        if 10 not in Devices:
            Domoticz.Device(
                Name="Total Power",
                Unit=10,
                Type=248,
                Subtype=1,
                Description="Current total power of the battery cluster (W)."
            ).Create()

        if 11 not in Devices:
            Domoticz.Device(
                Name="Target Power",
                Unit=11,
                Type=248,
                Subtype=1,
                Description="Target power the battery cluster attempts to reach (read-only)."
            ).Create()

        if 12 not in Devices:
            Domoticz.Device(
                Name="Max Consumption",
                Unit=12,
                Type=248,
                Subtype=1,
                Description="Maximum allowed consumption power (W)."
            ).Create()

        if 13 not in Devices:
            Domoticz.Device(
                Name="Max Production",
                Unit=13,
                Type=248,
                Subtype=1,
                Description="Maximum allowed production power (W)."
            ).Create()

    def _detectApiVersion(self):
        try:
            req = urllib.request.Request(self.api_info_url)
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("X-Api-Version", "2")

            context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, timeout=5, context=context)
            data = json.loads(response.read().decode())

            api_version = data.get("api_version", "0.0.0")
            parts = tuple(map(int, api_version.split(".")))
            self.is_modern = parts >= (2, 3, 0)

        except Exception as e:
            Domoticz.Error(f"API version detection failed: {e}")

    def onHeartbeat(self):
        if self.dataIntervalCount >= self.dataInterval:
            self.dataIntervalCount = 0
            self._pollAPI()
        else:
            self.dataIntervalCount += 1

    def _pollAPI(self):
        try:
            req = urllib.request.Request(self.api_url)
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("X-Api-Version", "2")

            context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, timeout=5, context=context)
            data = json.loads(response.read().decode())

            self._updateDevices(data)

        except Exception as e:
            Domoticz.Error(f"API error: {e}")

    def _updateDevices(self, data):
        mode = data.get("mode", "standby")
        charge_to_full = data.get("charge_to_full", False)

        level = 0
        if self.is_modern:
            if charge_to_full:
                level = 30
            elif mode == "standby":
                level = 0
            elif mode == "zero":
                level = 10
            elif mode == "predictive":
                level = 20
        else:
            if mode == "standby":
                level = 0
            elif mode == "zero":
                level = 10
            elif mode == "predictive":
                level = 20
            elif mode == "to_full":
                level = 30

        if Devices[1].sValue != str(level):
            Devices[1].Update(nValue=0, sValue=str(level))

        perms = data.get("permissions", [])
        self.last_permissions = perms

        charge_on = "charge_allowed" in perms
        if Devices[2].nValue != (1 if charge_on else 0):
            Devices[2].Update(1 if charge_on else 0, "On" if charge_on else "Off")

        discharge_on = "discharge_allowed" in perms
        if Devices[3].nValue != (1 if discharge_on else 0):
            Devices[3].Update(1 if discharge_on else 0, "On" if discharge_on else "Off")

        def updateIfChanged(unit, newValue):
            if Devices[unit].sValue != str(newValue):
                Devices[unit].Update(0, str(newValue))

        updateIfChanged(10, round(float(data.get("power_w", 0)), 3))
        updateIfChanged(11, round(float(data.get("target_power_w", 0)), 3))
        updateIfChanged(12, round(float(data.get("max_consumption_w", 0)), 3))
        updateIfChanged(13, round(float(data.get("max_production_w", 0)), 3))

    def onCommand(self, Unit, Command, Level, Color):
        if Unit == 1:
            self._handleMode(Level)
        elif Unit in (2, 3):
            self._handlePermissions(Unit, Command)

    def _handleMode(self, Level):
        payload = {}

        if Level == 0:
            payload = {"mode": "standby"}
        elif Level == 10:
            payload = {"mode": "zero"}
        elif Level == 20:
            if not self.is_modern:
                Domoticz.Error("Predictive mode not supported on API < 2.3.0")
                return
            payload = {"mode": "predictive"}
        elif Level == 30:
            if self.is_modern:
                payload = {"charge_to_full": True}
            else:
                payload = {"mode": "to_full"}

        self._put(payload)

    def _handlePermissions(self, Unit, Command):
        perms = self.last_permissions.copy()

        if Unit == 2:
            if Command == "On":
                if "charge_allowed" not in perms:
                    perms.append("charge_allowed")
            else:
                if "charge_allowed" in perms:
                    perms.remove("charge_allowed")

        elif Unit == 3:
            if Command == "On":
                if "discharge_allowed" not in perms:
                    perms.append("discharge_allowed")
            else:
                if "discharge_allowed" in perms:
                    perms.remove("discharge_allowed")

        payload = {"permissions": perms}
        self._put(payload)
        self.last_permissions = perms

    def _put(self, payload):
        try:
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode(),
                method="PUT"
            )
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("X-Api-Version", "2")
            req.add_header("Content-Type", "application/json")

            context = ssl._create_unverified_context()
            urllib.request.urlopen(req, timeout=5, context=context)

            self.dataIntervalCount = self.dataInterval

        except Exception as e:
            Domoticz.Error(f"PUT error: {e}")

global _plugin
_plugin = BasePlugin()

def onStart(): _plugin.onStart()
def onStop(): pass
def onHeartbeat(): _plugin.onHeartbeat()
def onCommand(Unit, Command, Level, Color): _plugin.onCommand(Unit, Command, Level, Color)
