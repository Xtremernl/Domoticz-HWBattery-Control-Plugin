"""
<plugin key="HWBatteryControl" name="HomeWizard Battery Control" author="Christian" version="1.0.0">
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
        self.poll_interval = 5
        self.api_url = ""
        self.api_info_url = ""
        self.api_token = ""
        self.debug = False
        self.next_poll = 0
        self.is_modern = False
        self.last_permissions = []

    def log(self, msg):
        if self.debug:
            Domoticz.Log("[DEBUG] " + msg)

    def onStart(self):
        Domoticz.Log("HomeWizard Battery Control plugin started")

        self.poll_interval = int(Parameters["Mode1"])
        self.api_token = Parameters["Password"]
        self.debug = Parameters["Mode6"] == "1"

        ip = Parameters["Address"]
        port = Parameters["Port"]

        self.api_url = f"https://{ip}:{port}/api/batteries"
        self.api_info_url = f"https://{ip}:{port}/api"

        self._createDevices()
        self._detectApiVersion()

    def _createDevices(self):
        # Mode selector
        if 1 not in Devices:
            Domoticz.Device(
                Name="Battery Mode",
                Unit=1,
                Type=244,
                Subtype=62,
                Switchtype=18
            ).Create()
            Devices[1].Update(nValue=0, sValue="Standby")

        # Charge Allowed
        if 2 not in Devices:
            Domoticz.Device(
                Name="Charge Allowed",
                Unit=2,
                Type=244,
                Subtype=73,
                Switchtype=0
            ).Create()

        # Discharge Allowed
        if 3 not in Devices:
            Domoticz.Device(
                Name="Discharge Allowed",
                Unit=3,
                Type=244,
                Subtype=73,
                Switchtype=0
            ).Create()

        # Power sensors
        if 10 not in Devices:
            Domoticz.Device(Name="Total Power", Unit=10, Type=248, Subtype=1).Create()

        if 11 not in Devices:
            Domoticz.Device(Name="Target Power", Unit=11, Type=248, Subtype=1).Create()

        if 12 not in Devices:
            Domoticz.Device(Name="Max Consumption", Unit=12, Type=248, Subtype=1).Create()

        if 13 not in Devices:
            Domoticz.Device(Name="Max Production", Unit=13, Type=248, Subtype=1).Create()

    def _detectApiVersion(self):
        try:
            req = urllib.request.Request(self.api_info_url)
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("X-Api-Version", "2")

            context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, timeout=5, context=context)
            data = json.loads(response.read().decode())

            self.log("API info response:\n" + json.dumps(data, indent=2))

            api_version = data.get("api_version", "0.0.0")
            parts = tuple(map(int, api_version.split(".")))
            self.is_modern = parts >= (2, 3, 0)

            self.log(f"Detected API version: {api_version} → modern={self.is_modern}")

        except Exception as e:
            Domoticz.Error(f"API version detection failed: {e}")

    def onHeartbeat(self):
        if self.next_poll > 0:
            self.next_poll -= 1
            return

        self.next_poll = self.poll_interval
        self._pollAPI()

    def _pollAPI(self):
        try:
            req = urllib.request.Request(self.api_url)
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("X-Api-Version", "2")

            context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, timeout=5, context=context)
            data = json.loads(response.read().decode())

            self.log("Battery data:\n" + json.dumps(data, indent=2))

            self._updateDevices(data)

        except Exception as e:
            Domoticz.Error(f"API error: {e}")

    def _updateDevices(self, data):
        # Mode
        mode = data.get("mode", "standby")
        Devices[1].Update(nValue=0, sValue=mode.capitalize())

        # Permissions
        perms = data.get("permissions", [])
        self.last_permissions = perms

        Devices[2].Update(nValue=1 if "charge_allowed" in perms else 0,
                          sValue="On" if "charge_allowed" in perms else "Off")

        Devices[3].Update(nValue=1 if "discharge_allowed" in perms else 0,
                          sValue="On" if "discharge_allowed" in perms else "Off")

        # Power sensors
        Devices[10].Update(0, str(int(data.get("power_w", 0))))
        Devices[11].Update(0, str(int(data.get("target_power_w", 0))))
        Devices[12].Update(0, str(int(data.get("max_consumption_w", 0))))
        Devices[13].Update(0, str(int(data.get("max_production_w", 0))))

    def onCommand(self, Unit, Command, Level, Color):
        self.log(f"Command received: Unit={Unit}, Command={Command}, Level={Level}")

        if Unit == 1:
            self._handleMode(Level)
        elif Unit in (2, 3):
            self._handlePermissions(Unit, Command)

    def _handleMode(self, Level):
        payload = {}

        if Level == 0:  # Standby
            payload = {"mode": "standby"}

        elif Level == 10:  # Zero
            payload = {"mode": "zero"}

        elif Level == 20:  # Predictive
            if not self.is_modern:
                Domoticz.Error("Predictive mode not supported on API < 2.3.0")
                return
            payload = {"mode": "predictive"}

        elif Level == 30:  # To-Full
            if self.is_modern:
                payload = {"charge_to_full": True}
            else:
                payload = {"mode": "to_full"}

        self._put(payload)

    def _handlePermissions(self, Unit, Command):
        perms = self.last_permissions.copy()

        if Unit == 2:  # Charge Allowed
            if Command == "On":
                if "charge_allowed" not in perms:
                    perms.append("charge_allowed")
            else:
                if "charge_allowed" in perms:
                    perms.remove("charge_allowed")

        elif Unit == 3:  # Discharge Allowed
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
            self.log("PUT payload:\n" + json.dumps(payload, indent=2))

            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode(),
                method="PUT"
            )
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("X-Api-Version", "2")
            req.add_header("Content-Type", "application/json")

            context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, timeout=5, context=context)
            result = response.read().decode()

            self.log("PUT response:\n" + result)

        except Exception as e:
            Domoticz.Error(f"PUT error: {e}")

global _plugin
_plugin = BasePlugin()

def onStart(): _plugin.onStart()
def onStop(): pass
def onHeartbeat(): _plugin.onHeartbeat()
def onCommand(Unit, Command, Level, Color): _plugin.onCommand(Unit, Command, Level, Color)
