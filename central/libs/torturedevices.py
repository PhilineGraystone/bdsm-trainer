# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
from torturedevice import torturedevice


class torturedevices():

    def __init__(self):
        self.devices = {}

    def add_device(self, mqtt, model, device, ip, online, capabilities=None, fw=None,
                   limits=None, degraded=None):
        if device not in self.devices:
            self.devices[device] = torturedevice(mqtt, model, device, ip, online,
                                                 capabilities=capabilities, fw=fw,
                                                 limits=limits, degraded=degraded)
        else:
            # known device: refresh capabilities and state (a second hello)
            d = self.devices[device]
            if capabilities or degraded is not None:
                d.set_capabilities(capabilities, degraded)
            if fw:
                d.fw_version = fw
            if limits:
                # A device whose limits were lowered in the portal reports new
                # values after its restart. Without this the central unit would
                # keep the earlier ones (project doc 23).
                import devicemodels
                d.envelope = devicemodels.envelope_of(d.model, limits)

    def set_blocked(self, device, reason):
        """Block or unblock a device.

        Blocked means: it stays in the list, it stays visible, it keeps
        reporting its state - it just carries nothing out any more. The reason
        is either firmware below the floor or a MAC that does not match the one
        on record.

        The REASON is carried along, not just a yes/no. "Device blocked" on its
        own leaves the supervisor guessing what to do about it.
        """
        d = self.devices.get(device)
        if d:
            d.blocked = reason or ''

    def blocked_reason(self, device):
        d = self.devices.get(device)
        return getattr(d, 'blocked', '') if d else ''

    def remove_device(self, device):
        self.devices.pop(device, None)

    def device_online(self, device):
        return device in self.devices

    def get_device(self, device):
        return self.devices.get(device, False)

    def count_devices(self):
        return len(self.devices)

    def set_state(self, device, state):
        d = self.devices.get(device)
        if d:
            d.set_state(state)

    def set_response(self, device, response):
        d = self.devices.get(device)
        if d:
            d.set_response(response)

    def stop_all(self):
        for d in list(self.devices.values()):
            d.stop()

    def emergency_all(self):
        for d in list(self.devices.values()):
            d.emergency()
