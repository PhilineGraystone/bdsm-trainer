# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
from slave import slave


class slaves():
    """Registry of the slaves who are logged in (key: RFID)."""

    def __init__(self):
        # was a class attribute before -> an instance attribute now
        self.slaves = {}
        self.notify = None          # f(kind, slave, **kw) - set by the central unit (session status)
        self.logbook = None         # libs/logbook.py - set by the central unit (project doc 14)

    def add_slave(self, mqtt, devices, slave_id, rfid, name, program, modes,
                  program_id=None, program_name=None):
        if rfid not in self.slaves:
            self.slaves[rfid] = slave(mqtt, devices, slave_id, name, rfid, program, modes,
                                      program_id=program_id, program_name=program_name,
                                      notify=self._notify, logbook=self.logbook)
        return self.slaves[rfid]

    def _notify(self, kind, s, **kw):
        if self.notify:
            self.notify(kind, s, **kw)

    def slave_online(self, rfid):
        return rfid in self.slaves

    def remove_slave(self, rfid):
        if rfid in self.slaves:
            self.slaves[rfid].disconnect()
            self.slaves.pop(rfid, None)

    def count_slaves(self):
        return len(self.slaves)

    def all(self):
        return list(self.slaves.values())

    def by_id(self, slave_id):
        for s in self.slaves.values():
            if s.slave_id == slave_id:
                return s
        return None

    def has_slave_id(self, slave_id):
        return self.by_id(slave_id) is not None

    def holder_of(self, device):
        """The logged-in slave currently holding the device (online) - or None."""
        for s in self.slaves.values():
            if s.get_online_device(device):
                return s
        return None

    def for_program(self, program_id):
        return [s for s in self.slaves.values() if s.program_id == program_id]

    def add_device(self, rfid, device):
        self.slaves[rfid].add_device(device)

    def add_offline_device(self, rfid, device):
        self.slaves[rfid].add_offline_device(device)

    def execute_program(self):
        # list(): the dict can change while we iterate over it (MQTT thread)
        for s in list(self.slaves.values()):
            s.execute()

    def stop_all(self):
        for s in list(self.slaves.values()):
            s.stop()

    def disconnect_all(self):
        """Release every assignment (central unit shutting down): devices then show
        'Waiting for SlaveID' again instead of a ghost holder."""
        for s in list(self.slaves.values()):
            s.disconnect()
        self.slaves.clear()

    def snapshot(self):
        return [s.snapshot() for s in self.slaves.values()]

    def get_slave_id_from_offline_device(self, off_device):
        for s in list(self.slaves.values()):
            if s.get_offline_device(off_device):
                s.set_offline_device_as_online(off_device)

    def set_online_device_to_offline(self, on_device):
        for s in list(self.slaves.values()):
            if s.get_online_device(on_device):
                s.set_online_device_as_offline(on_device)

    def on_device_event(self, device, slave_id, event, data):
        """Pass a device event on to the slave it belongs to.
        Matched by device UUID (the slave who holds the device)."""
        for s in list(self.slaves.values()):
            if s.get_online_device(device):
                if isinstance(data, dict):
                    data = dict(data, device=device)
                s.on_event(event, data)
                return
