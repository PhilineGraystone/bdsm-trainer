# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Event log (safety architecture F) - table audit_log (migration 003).

Used by the central unit (punisher.py / punmqtt) and by the web interface.
Its own DB connection behind a lock: the central unit writes from two threads
(main loop + paho network thread), and pymysql connections are not thread
safe. Failures while logging are logged and never raised - the record must
not be able to stop the installation.
"""

import json
import logging
import threading

import pymysql

logger = logging.getLogger('Punisher')

_lock = threading.Lock()
_db = None
_cfg = None


def init(db_config):
    """db_config: configparser-Abschnitt [database] (hostname, username, password, database)."""
    global _cfg
    _cfg = dict(host=db_config['hostname'], user=db_config['username'],
                password=db_config['password'], database=db_config['database'],
                autocommit=True, charset='utf8mb4')


def _connect():
    global _db
    if _cfg is None:
        return None
    try:
        if _db is None:
            _db = pymysql.connect(**_cfg)
        else:
            _db.ping(reconnect=True)
        return _db
    except pymysql.Error as e:
        logger.error('audit: db connect failed: %s', e)
        _db = None
        return None


def log(source, kind, action, device=None, slave_id=None, data=None, user=None):
    """Record one row. `data`: dict/list -> JSON, str is kept as it is."""
    if _cfg is None:
        return False
    if data is not None and not isinstance(data, str):
        try:
            data = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            data = str(data)
    if data is not None and len(data) > 60000:
        data = data[:60000]
    with _lock:
        db = _connect()
        if db is None:
            return False
        try:
            with db.cursor() as cur:
                cur.execute(
                    'INSERT INTO audit_log (al_source, al_kind, al_device, al_slave_id, '
                    '                       al_action, al_data, al_user) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (source[:16], kind[:16], device, slave_id, action[:64], data, user))
            return True
        except pymysql.Error as e:
            logger.error('audit: insert failed: %s', e)
            return False


# --- Short forms ------------------------------------------------------------
def device_event(device, slave_id, event, payload):
    return log('device', 'event', event, device, slave_id or None, payload)


def command(device, action, args, cmd_id):
    return log('central', 'cmd', action, device, None, {'args': args, 'id': cmd_id})


def central(action, slave_id=None, data=None, device=None):
    return log('central', 'central', action, device, slave_id, data)


def web(action, user, kind='admin', device=None, slave_id=None, data=None):
    return log('web', kind, action, device, slave_id, data, user)
