#!/usr/bin/env python3
# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Punisher — HDMI display (pygame, 7" 1024x600), own process next to punisher.py.

Pure MQTT consumer (process cut doc 04 D4): reads the session status of the
central unit (retained), its events, the heartbeat and the device states.
No database, no network apart from the broker. Images from the file system:
  pics/theme/*.png|jpg     theme images (idle slideshow, background)
  pics/slaves/<id>.png|jpg photo of the slave (id = slaves.slave_id)
  pics/grades/<A-F>.png    grade icons (replace the built-in glyphs, doc 14)

Logbook (doc 14): rank name, score, place and forecast on the slave card,
result toast with grade icon, Leaderboard when idle, special image on
promotion/demotion, weekly Report in the first seconds after the login.

Pi OS Lite: runs without X directly over KMS/DRM (SDL_VIDEODRIVER=kmsdrm), user
in the groups video, render, input. With a desktop SDL takes X11/Wayland itself.

Call:    python3 punisher-display.py [--windowed] [--snapshot out.png] [--demo]
Config:  [display] width=1024 height=600 fullscreen=1 fps=25 lang=de title=PUNISHER subtitle=...
         driver=kmsdrm (default; x11/wayland/auto only with a desktop)
"""

import sys
import os
punisherdir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(punisherdir, 'libs'))
os.chdir(punisherdir)

import argparse
import configparser
import glob
import json
import logging
import math
import threading
import time

import paho.mqtt.client as mqtt

import mqttaccount
import mqtttls

# --------------------------------------------------------------------------- #
args = argparse.ArgumentParser()
args.add_argument('--windowed', action='store_true', help='Fenster statt Vollbild')
args.add_argument('--snapshot', help='ein Bild rendern, als PNG speichern, beenden (Test)')
args.add_argument('--demo', action='store_true', help='Beispieldaten statt MQTT (Test)')
opts = args.parse_args()

config = configparser.ConfigParser()
config.read('config/config.ini')
D = config['display'] if 'display' in config else {}
W, H = int(D.get('width', 1024)), int(D.get('height', 600))
FPS = int(D.get('fps', 25))
LANG = D.get('lang', 'de')
TITLE = D.get('title', 'PUNISHER')
SUBTITLE = D.get('subtitle', 'Devious City')
FULLSCREEN = D.get('fullscreen', '1') == '1' and not opts.windowed

# Video driver: [display] driver = kmsdrm (default, Pi OS Lite: straight to the
# HDMI output) | x11 | wayland | auto (SDL decides, follows a DISPLAY variable).
# A DISPLAY set over SSH (MobaXterm, X forwarding) is deliberately IGNORED,
# otherwise the picture lands in the X window on the workstation instead of at
# the HDMI. --snapshot renders without a screen (dummy).
DRIVER = D.get('driver', 'kmsdrm').strip().lower()
if opts.snapshot:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
elif DRIVER != 'auto':
    os.environ['SDL_VIDEODRIVER'] = DRIVER
    if DRIVER == 'kmsdrm':
        os.environ.pop('DISPLAY', None)
        os.environ.pop('WAYLAND_DISPLAY', None)
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402  (after the environment variables)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-7s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('display')

# --------------------------------------------------------------------------- #
TEXT = {
    'de': dict(idle_hint='Tag auflegen, um zu beginnen', devices='Geräte online', device='Gerät online', central_ok='Zentrale bereit',
               central_off='ZENTRALE NICHT ERREICHBAR', welcome='Willkommen, {name}', bye='Auf Wiedersehen, {name}',
               unknown='Unbekannter Tag — bitte an die Aufsicht wenden', program='Programm', step_of='Schritt {pos} von {total}',
               next_in='nächster Schritt in {s} s', finished='Programm beendet', waiting='Vorbereitung — {s} s',
               no_program='kein Programm', emergency='EMERGENCY — ALLE GERÄTE GESPERRT', emergency_sub='Freigabe nur durch Aus- und Einschalten der Geräte',
               skipped='übersprungen', devices_title='Geräte', events_title='Zuletzt', offline='offline',
               # Condition at the collar (collar firmware from 3.4.0 on). The display so far
               # showed only the mode - that the wearer is currently OUT of the posture was
               # not to be seen on the screen, although the collar knows it.
               cond=dict(ok='in Haltung', out='Haltung verlassen', outside='außerhalb',
                         moving='bewegt sich'),
               # V-Cage proximity (doc 42 point 3). A visitor who sees the bar
               # shorten understands the pulse that follows — that is the
               # exhibition's point: show it, do not hide it.
               cage_in='V-Cage: drinnen', cage_near='V-Cage: NAHE DER GRENZE', cage_out='V-Cage: DRAUSSEN seit {s}',
               cage_next_warn='Warnung in {n} s', cage_next_pulse='IMPULS in {n} s', cage_gaveup='V-Cage hat aufgegeben',
               # Sanctions (doc 26). They belong on the screen: a sanction that
               # is in force and that nobody sees is a trap instead of a notice.
               sanctions_title='Auflagen',
               device_busy='{name}: Gerät ist bei {other} in Benutzung',
               rank='Rang', points='P', place='Platz', week_score='Woche', total='gesamt', plan='Wochenplan',
               leaderboard='Rangliste der Woche', result='{name}: {action} — Note {grade}, {points} Punkte',
               result_best=' · Bestleistung!', result_aborted='{name}: {action} abgebrochen', promotion='AUFSTIEG', demotion='ABSTIEG',
               rank_now='{name} ist jetzt {rank_name} (Rang {rank})', badge='{name}: Abzeichen „{badge}“',
               bonus='{name}: +{points} Punkte — {note}', detention='{name}: Nachsitzen — {action}', privilege='{name}: Privileg „{priv}“',
               streak_reached='{name}: Serie „{streak}“ — {n} {unit}', streak_broken='{name}: SERIE GEBROCHEN — {streak}, {n} {unit}',
               streaks_title='Serien', streak_lost='gebrochen bei {n}', unit={'Tage': 'Tage', 'Durchgänge': 'Durchgänge', 'Wochen': 'Wochen'},
               dayform='Tagesform: {form}', dayform_set='{name}: Tagesform {form} ({day})', dayforms={'easy': 'leicht', 'normal': 'normal', 'strict': 'streng'},
               mystery='{name}: ?', mystery_revealed='{name}: ? war — {text}',
               review_title='ZEUGNIS Woche {week}', review_rank='Rang {a} → {b} · {name}', review_score='{score} Punkte · Platz {place}',
               review_plan='Wochenplan {done}/{total} · {punish} Bestrafungen', review_grades='Noten', running='läuft', punish_short='Str.',
               attention='Aufmerksamkeit {hits}/{cues}', attention_cue='ACHTUNG — Taster drücken!', no_plan='kein Wochenplan',
               day_rest='Tag: noch {min} min', day_next='danach: {label}', day_tasks='{n} Planaufgaben heute',
               instruction='ANWEISUNG', instruction_left='noch {min} min', capitulation='{name} hat kapituliert',
               day_end='{name}: Tag beendet',
               calmode='KALIBRIERUNG', calmode_hint='Kein Programm, kein Tag — nichts wird gewertet.',
               day_status={'running': 'Tag läuft', 'done': 'Tag beendet', 'capitulated': 'KAPITULIERT', 'aborted': 'abgebrochen'},
               chal_title='Herausforderung — {action}', chal_target='Ziel {target}', chal_not_entered='nicht angetreten',
               chal_status={'open': 'offen', 'decided': 'entschieden', 'void': 'ungültig'},
               st={'idle': 'bereit', 'active': 'aktiv', 'emergency': 'GESPERRT', 'boot': 'startet', 'offline': 'offline'},
               ev={'shock': 'Impuls', 'warn': 'Warnung', 'locked': 'verriegelt', 'released': 'gelöst', 'lock_start': 'Anlegen',
                   'not_attached': 'nicht angelegt', 'bond_lost': 'Kontakt verloren', 'mode_start': 'Modus gestartet',
                   'mode_end': 'Modus beendet', 'pet_violation': 'aufgestanden!', 'pet_ok': 'wieder unten', 'inactive': 'keine Bewegung',
                   'active': 'Bewegung', 'cage_out': 'außerhalb!', 'cage_ok': 'zurück im Bereich', 'cage_giveup': 'V-Cage: Ende',
                   'cmd_rejected': 'abgelehnt', 'safe_state': 'sicherer Zustand', 'stopped': 'gestoppt', 'emergency': 'EMERGENCY',
                   'vibe': 'Vibration', 'beep': 'Ton', 'pet_armed': 'Haltung eingelernt', 'test_tx': 'Test',
                   'statue_violation': 'Haltung verlassen!', 'statue_ok': 'Haltung wieder ok', 'statue_armed': 'Haltung gemerkt',
                   'task_start': 'Aufgabe gestartet', 'task_end': 'Aufgabe beendet', 'wobble': 'Wackler', 'lost': 'Knopf gefallen!',
                   'hit': 'Treffer', 'missed': 'verpasst!', 'trainer_start': 'Training gestartet', 'trainer_end': 'Training beendet',
                   'stroke': 'Stoß', 'miss': 'Fehlstoß!', 'reward': 'Belohnung', 'press': 'Taster', 'attention_cue': 'Achtung!'}),
    'en': dict(idle_hint='Place your tag to begin', devices='devices online', device='device online', central_ok='central ready',
               central_off='CENTRAL UNREACHABLE', welcome='Welcome, {name}', bye='Goodbye, {name}',
               unknown='Unknown tag — please see the supervisor', program='Program', step_of='Step {pos} of {total}',
               next_in='next step in {s} s', finished='Program finished', waiting='Preparing — {s} s',
               no_program='no program', emergency='EMERGENCY — ALL DEVICES LOCKED', emergency_sub='Release only by power-cycling the devices',
               skipped='skipped', devices_title='Devices', events_title='Recent', offline='offline',
               cage_in='V-Cage: inside', cage_near='V-Cage: NEAR THE EDGE', cage_out='V-Cage: OUTSIDE for {s}',
               cage_next_warn='warning in {n} s', cage_next_pulse='PULSE in {n} s', cage_gaveup='V-Cage gave up',
               cond=dict(ok='in position', out='position left', outside='outside',
                         moving='moving'),
               sanctions_title='Sanctions',
               device_busy='{name}: device in use by {other}',
               rank='Rank', points='P', place='Place', week_score='week', total='total', plan='Weekly plan',
               leaderboard='Leaderboard of the week', result='{name}: {action} — grade {grade}, {points} points',
               result_best=' · personal best!', result_aborted='{name}: {action} aborted', promotion='PROMOTION', demotion='DEMOTION',
               rank_now='{name} is now {rank_name} (rank {rank})', badge='{name}: badge “{badge}”',
               bonus='{name}: +{points} points — {note}', detention='{name}: detention — {action}', privilege='{name}: privilege “{priv}”',
               streak_reached='{name}: streak “{streak}” — {n} {unit}', streak_broken='{name}: STREAK BROKEN — {streak}, {n} {unit}',
               streaks_title='Streaks', streak_lost='broken at {n}', unit={'Tage': 'days', 'Durchgänge': 'runs', 'Wochen': 'weeks'},
               dayform='Day form: {form}', dayform_set='{name}: day form {form} ({day})', dayforms={'easy': 'easy', 'normal': 'normal', 'strict': 'strict'},
               mystery='{name}: ?', mystery_revealed='{name}: ? was — {text}',
               review_title='REPORT week {week}', review_rank='Rank {a} → {b} · {name}', review_score='{score} points · place {place}',
               review_plan='Weekly plan {done}/{total} · {punish} punishments', review_grades='Grades', running='running', punish_short='pun.',
               attention='Attention {hits}/{cues}', attention_cue='ATTENTION — press the button!', no_plan='no weekly plan',
               day_rest='Day: {min} min left', day_next='next: {label}', day_tasks='{n} plan tasks today',
               instruction='INSTRUCTION', instruction_left='{min} min left', capitulation='{name} has capitulated',
               day_end='{name}: day finished',
               calmode='CALIBRATION', calmode_hint='No programme, no day - nothing is scored.',
               day_status={'running': 'day running', 'done': 'day finished', 'capitulated': 'CAPITULATED', 'aborted': 'aborted'},
               chal_title='Challenge — {action}', chal_target='target {target}', chal_not_entered='did not enter',
               chal_status={'open': 'open', 'decided': 'decided', 'void': 'void'},
               st={'idle': 'ready', 'active': 'active', 'emergency': 'LOCKED', 'boot': 'booting', 'offline': 'offline'}, ev={}),
}
T = TEXT.get(LANG, TEXT['de'])

# --------------------------------------------------------------------------- #
class State:
    """Everything that comes in over MQTT — shared between network and render thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.session = {'slaves': []}
        self.devices = {}             # uuid -> state dict
        self.dev_names = {}           # uuid -> label from the web (dev_address) — comes via session.devices_named
        self.last_hb = 0.0
        self.toasts = []              # [(until, kind, text, extra)]
        self.emergency_until = 0.0
        self.connected = False
        self.leaderboard = None       # punisher/central/leaderboard (retained)
        self.special = None           # special image (promotion/demotion): dict with 'until'

    def toast(self, kind, text, secs=4.0, extra=None):
        with self.lock:
            self.toasts = [t for t in self.toasts if not (t[1] == kind and t[2] == text)][-3:]
            self.toasts.append((time.time() + secs, kind, text, extra))

    def snapshot(self):
        with self.lock:
            now = time.time()
            self.toasts = [t for t in self.toasts if t[0] > now]
            return {
                'session': self.session, 'devices': dict(self.devices), 'toasts': list(self.toasts),
                'central_alive': (now - self.last_hb) < 5 if self.last_hb else False,
                'emergency': self.emergency_until > now or any(d.get('state') == 'emergency' for d in self.devices.values()),
                'connected': self.connected,
                'leaderboard': self.leaderboard,
                'special': self.special if (self.special and self.special['until'] > now) else None,
            }


S = State()


class Bus(mqtt.Client):
    def __init__(self):
        super().__init__(mqtt.CallbackAPIVersion.VERSION2, client_id='PunisherDisplay')

    def on_connect(self, client, userdata, flags, rc, properties):
        if rc != 0:
            log.error('mqtt connect failed: %s', rc)
            return
        S.connected = True
        for t in ('punisher/central/session', 'punisher/central/event', 'punisher/central/heartbeat',
                  'punisher/central/leaderboard',
                  'punisher/devices/+/state', 'punisher/devices/+/event', 'punisher/emergency',
                  'punisher/devices/+/emergency'):
            self.subscribe(t, 0)
        log.info('mqtt connected')

    def on_disconnect(self, client, userdata, flags, rc, properties):
        S.connected = False

    def on_message(self, client, userdata, msg):
        try:
            j = json.loads(msg.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            j = {}
        if not isinstance(j, dict):
            j = {}                    # a list/number as payload must not end the MQTT thread
        parts = msg.topic.split('/')
        now = time.time()
        if msg.topic == 'punisher/central/session':
            with S.lock:
                S.session = j if isinstance(j, dict) and 'slaves' in j else {'slaves': []}
        elif msg.topic == 'punisher/central/heartbeat':
            with S.lock:
                S.last_hb = now
        elif msg.topic == 'punisher/central/leaderboard':
            with S.lock:
                S.leaderboard = j if isinstance(j, dict) else None
        elif msg.topic == 'punisher/central/event':
            ev = j.get('event')
            if ev == 'login':
                S.toast('login', T['welcome'].format(name=j.get('name', '')), 6)
            elif ev == 'logout':
                # The day ends regularly, by capitulation or by abort (doc 14 §12.2)
                r = j.get('reason')
                if r == 'capitulated':
                    S.toast('unknown', T['capitulation'].format(name=j.get('name', '')), 8)
                elif r == 'done':
                    S.toast('logout', T['day_end'].format(name=j.get('name', '')), 6)
                else:
                    S.toast('logout', T['bye'].format(name=j.get('name', '')), 6)
            elif ev == 'rfid_unknown':
                S.toast('unknown', T['unknown'], 6)
            elif ev == 'device_busy':
                S.toast('unknown', T['device_busy'].format(name=j.get('name', ''), other=j.get('held_by', '')), 8)
            elif ev == 'step':
                txt = f"{j.get('name', '')}: {j.get('action', j.get('code'))}"
                if j.get('skipped'):
                    txt += f" ({T['skipped']})"
                S.toast('step', txt, 5)
            elif ev == 'achievement':
                if j.get('status') == 'aborted':
                    S.toast('step', T['result_aborted'].format(name=j.get('name', ''), action=j.get('action_name', j.get('action'))), 5)
                else:
                    txt = T['result'].format(name=j.get('name', ''), action=j.get('action_name', j.get('action')),
                                             grade=j.get('grade', '?'), points=j.get('points', 0))
                    if j.get('best'):
                        txt += T['result_best']
                    S.toast('grade', txt, 8, extra=j.get('grade'))
            elif ev == 'rank_change':
                up = (j.get('to') or 0) > (j.get('from') or 0)
                with S.lock:
                    S.special = {'until': now + 9, 'up': up, 'name': j.get('name', ''), 'rank': j.get('to'),
                                 'rank_name': j.get('rank_name', ''), 'from': j.get('from'), 'slave_id': j.get('slave_id')}
            elif ev == 'badge':
                S.toast('badge', T['badge'].format(name=j.get('name', ''), badge=j.get('badge_name', j.get('badge'))), 7)
            elif ev == 'bonus':
                S.toast('badge', T['bonus'].format(name=j.get('name', ''), points=j.get('points', 0), note=j.get('note', '')), 7)
            elif ev == 'detention':
                S.toast('unknown', T['detention'].format(name=j.get('name', ''), action=j.get('action', '')), 7)
            elif ev == 'privilege' and j.get('granted'):
                S.toast('badge', T['privilege'].format(name=j.get('name', ''), priv=j.get('privilege_name', j.get('privilege'))), 7)
            elif ev == 'attention_cue':
                S.toast('unknown', T['attention_cue'], 4)
            elif ev == 'streak_reached':
                S.toast('badge', T['streak_reached'].format(name=j.get('name_slave', ''), streak=j.get('name', ''),
                                                            n=j.get('n', 0), unit=T['unit'].get(j.get('unit'), j.get('unit', ''))), 8)
            elif ev == 'mystery':
                S.toast('unknown', T['mystery'].format(name=j.get('name', '')), 6)
            elif ev == 'mystery_revealed':
                S.toast('step', T['mystery_revealed'].format(name=j.get('name', ''), text=j.get('text', '')), 8)
            elif ev == 'dayform':
                S.toast('unknown' if j.get('form') == 'strict' else 'badge',
                        T['dayform_set'].format(name=j.get('name', ''), form=T['dayforms'].get(j.get('form'), j.get('form', '')),
                                                day=j.get('day', '')[5:].replace('-', '.')), 7)
            elif ev == 'streak_broken':
                # the loss is shown (decision Philine 2026-09-16): the more
                # interesting moment for the visitors than the seventh day
                S.toast('unknown', T['streak_broken'].format(name=j.get('name_slave', ''), streak=j.get('name', ''),
                                                             n=j.get('n', 0), unit=T['unit'].get(j.get('unit'), j.get('unit', ''))), 9)
        elif msg.topic == 'punisher/emergency' or (len(parts) == 4 and parts[3] == 'emergency'):
            with S.lock:
                S.emergency_until = now + 3600
        elif len(parts) == 4 and parts[1] == 'devices':
            uuid, kind = parts[2], parts[3]
            with S.lock:
                d = S.devices.setdefault(uuid, {})
                if kind == 'state':
                    d.update(j)
                    d['_seen'] = now
                elif kind == 'event':
                    d['_event'] = j
                    d['_event_t'] = now
                    if j.get('event') == 'emergency':
                        S.emergency_until = now + 3600


# --------------------------------------------------------------------------- #
#  Rendering
# --------------------------------------------------------------------------- #
BG, PANEL, LINE = (12, 13, 16), (26, 28, 34), (48, 52, 62)
FG, MUTED, ACC = (236, 236, 236), (150, 158, 170), (124, 183, 255)
OK, WARN, ERR, EMG = (94, 194, 122), (232, 184, 74), (229, 100, 107), (255, 45, 85)

_fonts = {}


def font(size, bold=False, serif=False):
    key = (size, bold, serif)
    if key not in _fonts:
        path = None
        for cand in (['fonts/FreeSerif.ttf'] if serif else ['fonts/FreeSansBold.ttf' if bold else 'fonts/FreeSans.ttf', 'fonts/FreeSans.ttf']):
            if os.path.exists(cand):
                path = cand
                break
        f = pygame.font.Font(path, size) if path else pygame.font.SysFont('dejavusans', size, bold=bold)
        if bold and path and 'Bold' not in path:
            f.set_bold(True)
        _fonts[key] = f
    return _fonts[key]


def text(surf, s, x, y, size=22, color=FG, bold=False, serif=False, align='left', maxw=None):
    f = font(size, bold, serif)
    if maxw:
        while len(s) > 3 and f.size(s)[0] > maxw:
            s = s[:-2] + '…'
    img = f.render(s, True, color)
    r = img.get_rect()
    if align == 'center':
        r.midtop = (x, y)
    elif align == 'right':
        r.topright = (x, y)
    else:
        r.topleft = (x, y)
    surf.blit(img, r)
    return r


def wrap(surf, s, x, y, w, size=20, color=FG, lh=None, maxlines=3):
    f = font(size)
    lh = lh or int(size * 1.3)
    words, lines, cur = s.split(), [], ''
    for wd in words:
        t = (cur + ' ' + wd).strip()
        if f.size(t)[0] <= w:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    lines.append(cur)
    for i, ln in enumerate(lines[:maxlines]):
        surf.blit(f.render(ln, True, color), (x, y + i * lh))
    return y + min(len(lines), maxlines) * lh


def panel(surf, rect, color=PANEL, radius=12, border=LINE):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, 1, border_radius=radius)


_img_cache = {}


def load_image(path, size, mode='cover'):
    key = (path, size, mode)
    if key in _img_cache:
        return _img_cache[key]
    try:
        img = pygame.image.load(path).convert_alpha()
    except (pygame.error, FileNotFoundError):
        _img_cache[key] = None
        return None
    iw, ih = img.get_size()
    tw, th = size
    scale = max(tw / iw, th / ih) if mode == 'cover' else min(tw / iw, th / ih)
    img = pygame.transform.smoothscale(img, (max(1, int(iw * scale)), max(1, int(ih * scale))))
    if mode == 'cover':
        out = pygame.Surface(size, pygame.SRCALPHA)
        out.blit(img, ((tw - img.get_width()) // 2, (th - img.get_height()) // 2))
        img = out
    _img_cache[key] = img
    return img


def theme_images():
    files = sorted(glob.glob('pics/theme/*.png') + glob.glob('pics/theme/*.jpg') + glob.glob('pics/theme/*.jpeg'))
    return files


def slave_photo(slave_id, size):
    for ext in ('jpg', 'jpeg', 'png'):
        p = f'pics/slaves/{slave_id}.{ext}'
        if os.path.exists(p):
            return load_image(p, size, 'cover')
    return None


def draw_silhouette(surf, rect):
    panel(surf, rect, (36, 38, 46), 14)
    cx, top = rect.centerx, rect.top
    r = rect.width // 5
    pygame.draw.circle(surf, (70, 74, 86), (cx, top + rect.height // 3), r)
    pygame.draw.ellipse(surf, (70, 74, 86), pygame.Rect(cx - r * 2, top + rect.height // 3 + r, r * 4, rect.height))
    surf.set_clip(None)


GRADE_COL = {'A': (240, 192, 64), 'B': (124, 183, 255), 'C': (94, 194, 122), 'D': (232, 184, 74), 'E': (229, 100, 107), 'F': (154, 163, 173)}


def grade_image(g, size):
    for ext in ('png', 'jpg'):
        p = f'pics/grades/{g}.{ext}'
        if os.path.exists(p):
            return load_image(p, (size, size), 'contain')
    return None


def draw_grade(surf, g, x, y, size=28):
    """Grade icon A-F: crown, medal, tick, exclamation mark, warning sign, cross (default
    glyphs; pics/grades/<g>.png replaces them). Draws at (x, y) in size x size."""
    g = (g or '').upper()
    img = grade_image(g, size)
    if img:
        surf.blit(img, (x, y))
        return
    c = GRADE_COL.get(g, MUTED)
    s_ = size / 34.0
    def P(px, py):
        return (int(x + px * s_), int(y + py * s_))
    w = max(2, int(3 * s_))
    if g == 'A':
        pygame.draw.polygon(surf, c, [P(4, 20), P(7, 9), P(12, 14), P(17, 6), P(22, 14), P(27, 9), P(30, 20)])
        pygame.draw.rect(surf, c, (*P(4, 22), int(26 * s_), max(2, int(4 * s_))))
    elif g == 'B':
        pygame.draw.circle(surf, c, P(17, 20), int(8 * s_))
        pygame.draw.polygon(surf, c, [P(11, 4), P(17, 12), P(23, 4)])
    elif g == 'C':
        pygame.draw.lines(surf, c, False, [P(6, 18), P(14, 26), P(28, 8)], w + 1)
    elif g == 'D':
        pygame.draw.rect(surf, c, (*P(15, 5), max(2, int(4 * s_)), int(15 * s_)))
        pygame.draw.circle(surf, c, P(17, 26), max(2, int(2.6 * s_)))
    elif g == 'E':
        pygame.draw.polygon(surf, c, [P(17, 4), P(31, 28), P(3, 28)], w)
        pygame.draw.rect(surf, c, (*P(15.5, 12), max(2, int(3 * s_)), int(9 * s_)))
        pygame.draw.circle(surf, c, P(17, 24.5), max(2, int(1.8 * s_)))
    elif g == 'F':
        pygame.draw.line(surf, c, P(7, 7), P(27, 27), w + 1)
        pygame.draw.line(surf, c, P(27, 7), P(7, 27), w + 1)
    else:
        pygame.draw.circle(surf, c, P(17, 17), int(10 * s_), w)


def dev_state_text(st):
    if not st:
        return T['offline'], MUTED
    s = st.get('state', 'idle')
    if s == 'emergency':
        return T['st']['emergency'], EMG
    rem = st.get('remaining_s')
    if rem is not None:          # keep counting the time left since the last state
        rem = max(0, int(rem - (time.time() - st.get('_seen', time.time()))))
    if st.get('lock') in ('countdown', 'locked'):
        return (f"{st['lock']} {rem // 60}:{rem % 60:02d}" if rem else st['lock']), WARN
    if st.get('mode') and st.get('mode') != 'idle':
        return (f"{st['mode']} {rem // 60}:{rem % 60:02d}" if rem else st['mode']), WARN
    if s == 'offline':
        return T['offline'], MUTED
    return T['st'].get(s, s), OK


def dev_cond_text(st):
    """Second line of the device tile: in which condition the wearer is AT THE
    DEVICE, and since when.

    The collar has reported that since 3.4.0, the web shows it - the screen
    kept on showing only the mode. Right here is where it belongs: whoever
    stands in front of it sees "Statue" and does not know whether she is
    holding the posture (counter-proof Philine 2026-09-11).

    Returns (text, colour) or (None, None) when the device reports nothing -
    then the tile stays as it was.
    """
    if not st:
        return None, None
    c = st.get('cond')
    if not c or c == 'none':
        return None, None
    since = st.get('cond_since_s')
    if since is not None:
        # Time has passed since the last message; otherwise the duration would
        # stand still between two state messages.
        since = max(0, int(since + (time.time() - st.get('_seen', time.time()))))
    word = T['cond'].get(c, c)
    if since is not None:
        word = f"{word} · {since // 60}:{since % 60:02d}"
    return word, (WARN if c in ('out', 'outside') else OK)


def cage_info(st):
    """(text, colour, fill 0..1) of the V-Cage proximity, or (None, None, None).

    Only while the collar is in cage mode and sends its margin (collar 2.2.0).
    The margin is RSSI minus the collar's own threshold: > 0 inside, < 0 out.
    The bar runs from -10 dB (empty) to +20 dB (full), the mark sits at 0 — the
    same scale as in the web, so that what the supervisor sees on her screen
    and what the visitor sees on the wall is the same picture.
    """
    if not st or st.get('mode') != 'cage' or 'cage_margin_db' not in st:
        return None, None, None
    m = int(st['cage_margin_db'])
    fill = max(0.0, min(1.0, (m + 10) / 30.0))
    if m < 0:
        out_s = st.get('cage_out_s')
        if out_s is not None:
            out_s = max(0, int(out_s + (time.time() - st.get('_seen', time.time()))))
        txt = T['cage_out'].format(s=f"{(out_s or 0) // 60}:{(out_s or 0) % 60:02d}")
        nxt = st.get('cage_next_s')
        if st.get('cage_gaveup'):
            txt += ' · ' + T['cage_gaveup']
        elif nxt is not None:
            # Ceiling, not floor: "in 4 s" stays 4 until it is truly below 3.
            # A countdown that shows 3 while 3.9 s remain counts down too fast.
            nxt = max(0, int(math.ceil(nxt - (time.time() - st.get('_seen', time.time())))))
            txt += ' · ' + (T['cage_next_pulse'] if st.get('cage_warned') else T['cage_next_warn']).format(n=nxt)
        return txt, ERR, fill
    if m < 5:
        return T['cage_near'], WARN, fill
    return T['cage_in'], OK, fill


# --------------------------------------------------------------------------- #
class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.theme = theme_images()
        self.theme_i = 0
        self.theme_t = time.time()
        self.page_t = time.time()
        self.page = 0
        self.board_t = time.time()     # switch between the weekly Leaderboard and the Challenges
        self.board_i = 0

    # --- Background: theme images as a slideshow, dimmed -----------------------
    def background(self, alpha=90):
        self.screen.fill(BG)
        if not self.theme:
            # discreet surface without images
            for i in range(0, H, 4):
                c = 12 + int(6 * (1 - i / H))
                pygame.draw.line(self.screen, (c, c + 1, c + 4), (0, i), (W, i), 4)
            return
        now = time.time()
        if now - self.theme_t > 12:
            self.theme_t = now
            self.theme_i = (self.theme_i + 1) % len(self.theme)
        img = load_image(self.theme[self.theme_i], (W, H), 'cover')
        if img:
            img = img.copy()
            img.set_alpha(alpha)
            self.screen.blit(img, (0, 0))
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 110))
        self.screen.blit(shade, (0, 0))

    def statusbar(self, snap):
        n_on = sum(1 for d in snap['devices'].values() if d.get('state') not in (None, 'offline') and time.time() - d.get('_seen', 0) < 45)
        y = H - 34
        pygame.draw.rect(self.screen, (0, 0, 0, 0), (0, y, W, 34))
        col = OK if snap['central_alive'] else ERR
        pygame.draw.circle(self.screen, col, (24, y + 17), 6)
        text(self.screen, T['central_ok'] if snap['central_alive'] else T['central_off'], 40, y + 6, 18, FG if snap['central_alive'] else ERR)
        text(self.screen, f"{n_on} {T['device'] if n_on == 1 else T['devices']}", W // 2, y + 6, 18, MUTED, align='center')
        text(self.screen, time.strftime('%H:%M'), W - 20, y + 4, 22, MUTED, align='right')
        if not snap['connected']:
            text(self.screen, 'MQTT …', W - 110, y + 6, 18, ERR, align='right')

    # --- Idle --------------------------------------------------------------------
    def attract(self, snap):
        self.background(110)
        pulse = 0.5 + 0.5 * math.sin(time.time() * 1.6)
        text(self.screen, TITLE, W // 2, 140, 120, FG, serif=True, align='center')
        pygame.draw.line(self.screen, ACC, (W // 2 - 160, 285), (W // 2 + 160, 285), 2)
        text(self.screen, SUBTITLE, W // 2, 300, 30, MUTED, serif=True, align='center')
        c = tuple(int(MUTED[i] + (FG[i] - MUTED[i]) * pulse) for i in range(3))
        board = snap.get('leaderboard') or {}
        lb = board.get('week') or []
        # Second Leaderboard (doc 14 §12.4): Challenges alternate with the weekly
        # Leaderboard so that both are to be seen when idle.
        chals = [c2 for c2 in (board.get('challenges') or []) if c2.get('entries')]
        boards = ([('week', lb)] if lb else []) + [('chal', c2) for c2 in chals]
        if boards:
            if time.time() - self.board_t > 10:
                self.board_t = time.time()
                self.board_i += 1
            kind, data = boards[self.board_i % len(boards)]
            text(self.screen, T['idle_hint'], W // 2, 350, 26, c, align='center')
            rect = pygame.Rect(W // 2 - 300, 395, 600, 0)
            if kind == 'week':
                rect.height = min(180, 34 + 28 * min(5, len(data)))
                self.leaderboard_panel(data, rect)
            else:
                rect.height = min(200, 52 + 28 * min(5, len(data['entries'])))
                self.challenge_panel(data, rect)
            if len(boards) > 1:
                text(self.screen, f"{self.board_i % len(boards) + 1}/{len(boards)}",
                     rect.right, rect.bottom + 6, 15, MUTED, align='right')
        else:
            text(self.screen, T['idle_hint'], W // 2, 430, 30, c, align='center')
        self.statusbar(snap)

    def leaderboard_panel(self, entries, rect):
        panel(self.screen, rect, (20, 22, 28, 220), 12)
        text(self.screen, T['leaderboard'], rect.left + 14, rect.top + 6, 16, MUTED)
        y = rect.top + 30
        for e in entries[:5]:
            text(self.screen, f"{e.get('place')}.", rect.left + 14, y, 19, FG, bold=True)
            text(self.screen, e.get('name', ''), rect.left + 44, y, 19, FG, maxw=220)
            text(self.screen, f"{e.get('rank')} · {e.get('rank_name', '')}", rect.left + 270, y, 17, WARN, maxw=200)
            text(self.screen, f"{e.get('points', 0)} {T['points']}", rect.right - 14, y, 19, ACC, bold=True, align='right')
            y += 28

    def challenge_panel(self, ch, rect):
        """Second Leaderboard: one Challenge with the placings of all slaves."""
        panel(self.screen, rect, (20, 22, 28, 220), 12)
        text(self.screen, T['chal_title'].format(action=ch.get('action_name', '')), rect.left + 14, rect.top + 6, 16, MUTED, maxw=rect.width - 150)
        text(self.screen, T['chal_status'].get(ch.get('status'), ch.get('status') or ''), rect.right - 14, rect.top + 6, 16,
             OK if ch.get('status') == 'decided' else WARN, align='right')
        text(self.screen, T['chal_target'].format(target=ch.get('target_text') or ch.get('target')), rect.left + 14, rect.top + 26, 15, MUTED)
        y = rect.top + 50
        for e in ch.get('entries', [])[:5]:
            entered = not e.get('note')
            col = FG if entered else MUTED
            text(self.screen, f"{e.get('place') or '–'}.", rect.left + 14, y, 19, col, bold=True)
            text(self.screen, e.get('name', ''), rect.left + 44, y, 19, col, maxw=240)
            if entered:
                if e.get('grade'):
                    draw_grade(self.screen, e['grade'], rect.left + 300, y - 3, 22)
                text(self.screen, f"{e.get('points') or 0} {T['points']}", rect.right - 14, y, 19, ACC, bold=True, align='right')
            else:
                text(self.screen, T['chal_not_entered'], rect.right - 14, y, 17, ERR, align='right')
            y += 28

    # --- Slave card -------------------------------------------------------------
    def slave_card(self, sl, rect, snap, compact=False):
        panel(self.screen, rect, (20, 22, 28, 230), 16)
        pad = 18
        photo_w, photo_h = (150, 190) if compact else (200, 250)
        pr = pygame.Rect(rect.left + pad, rect.top + pad, photo_w, photo_h)
        img = slave_photo(sl.get('slave_id'), (photo_w, photo_h))
        if img:
            self.screen.blit(img, pr)
            pygame.draw.rect(self.screen, LINE, pr, 1, border_radius=8)
        else:
            draw_silhouette(self.screen, pr)
        tx = pr.right + pad
        tw = rect.right - pad - tx
        text(self.screen, sl.get('name', ''), tx, rect.top + pad - 4, 30 if compact else 42, FG, bold=True, maxw=tw)
        prog = (sl.get('program') or {}).get('name') or T['no_program']
        text(self.screen, f"{T['program']}: {prog}", tx, rect.top + pad + (34 if compact else 50), 20 if compact else 24, ACC, maxw=tw)

        # Logbook: rank, score, place, forecast (doc 14)
        L = sl.get('logbook')
        y = rect.top + pad + (60 if compact else 84)
        if L:
            rank_txt = f"{T['rank']} {L.get('rank')} · {L.get('rank_name', '')} · {L.get('score_week', 0)} {T['points']}"
            if L.get('place_week'):
                rank_txt += f" · {T['place']} {L['place_week']}"
            if L.get('points_total') is not None:
                rank_txt += f" · {T['total']} {L['points_total']}"
            text(self.screen, rank_txt, tx, y, 17 if compact else 20, WARN, bold=True, maxw=tw)
            y += 22 if compact else 26
            fc = L.get('forecast') or {}
            if fc.get('text'):
                col = {'up': OK, 'down': ERR, 'hold': MUTED}.get(fc.get('risk'), MUTED)
                txt = fc['text']
                # day form (doc 44 §5) on the same line - the visitors see what kind of day it is
                df = (L.get('dayform') or {}).get('form')
                if df and df != 'normal':
                    txt += '  ·  ' + T['dayform'].format(form=T['dayforms'].get(df, df))
                    col = ERR if df == 'strict' else OK
                text(self.screen, txt, tx, y, 15 if compact else 17, col, maxw=tw)
                y += 20 if compact else 24
        # Calibration run (doc 33): instead of the Day plan and the progress it
        # stands here that nothing is scored. She shall see that herself — a
        # run in which nothing counts and one in which everything counts must
        # not look the same on the display.
        if sl.get('calibration_mode'):
            text(self.screen, T['calmode'], tx, y, 17 if compact else 20, WARN, bold=True, maxw=tw)
            y += 21 if compact else 25
            text(self.screen, T['calmode_hint'], tx, y, 15 if compact else 17, MUTED, maxw=tw)
            y += 20 if compact else 24

        # Course of the day (doc 14 §12): current block, time left of the day, what comes next
        day = sl.get('day')
        if day:
            st = T['day_status'].get(day.get('status'), day.get('status') or '')
            line = day.get('block_label') or st
            if day.get('status') == 'running':
                line += ' · ' + T['day_rest'].format(min=day.get('remaining_min', 0))
            elif st and st != line:
                line += ' · ' + st
            if day.get('tasks'):
                line += ' · ' + T['day_tasks'].format(n=day['tasks'])
            if (day.get('next') or {}).get('label'):
                line += ' · ' + T['day_next'].format(label=day['next']['label'])
            col = ERR if day.get('status') == 'capitulated' else (ACC if day.get('status') == 'running' else MUTED)
            text(self.screen, line, tx, y, 16 if compact else 19, col, bold=True, maxw=tw)
            y += 21 if compact else 25

        # Report of the previous week: in the first seconds after the login instead of the step list
        rv = sl.get('review')
        if rv and time.time() - (sl.get('login_ts') or 0) < 40:
            # The Report fills the card; devices/events appear afterwards
            self.review_card(rv, tx, y, tw, rect.bottom - pad - y, compact)
            return

        # Neutral instruction (break, eating, waiting): large instead of the step list — the
        # slave must be able to read it across the room (decision Philine).
        instr = (day or {}).get('instruction')
        if instr and instr.get('text'):
            self.instruction_card(instr, tx, y, tw, pr.bottom + 30 - y, compact)
            self._card_footer(sl, rect, pr, pad, snap, compact)
            return

        pgs = sl.get('progress') or {}
        steps = pgs.get('steps') or []
        total = pgs.get('total', len(steps))
        pos = pgs.get('pos', 0)
        # Keep counting the countdown locally: the central unit publishes the state only on changes
        elapsed = max(0, time.time() - (snap['session'].get('ts_ms', 0) or 0) / 1000.0)
        if pgs.get('finished'):
            text(self.screen, T['finished'], tx, y, 20, OK)
        elif total:
            nxt = pgs.get('next_in_s')
            if nxt is not None:
                nxt = max(0, int(nxt - elapsed))
            if pos == 0 and nxt:
                text(self.screen, T['waiting'].format(s=nxt), tx, y, 20, WARN)
            else:
                line = T['step_of'].format(pos=min(pos + 1, total), total=total)
                wf = pgs.get('waiting_for')
                if wf:
                    line += f" · {wf.get('action')} {T['running']} {int((wf.get('elapsed_s') or 0) + elapsed)} s"
                elif nxt is not None:
                    line += ' · ' + T['next_in'].format(s=nxt)
                text(self.screen, line, tx, y, 20, MUTED)
            # progress bar
            bar = pygame.Rect(tx, y + 28, tw, 6)
            pygame.draw.rect(self.screen, LINE, bar, border_radius=3)
            pygame.draw.rect(self.screen, ACC, (bar.x, bar.y, int(bar.width * min(pos, total) / total), 6), border_radius=3)

        # Step list: window around the current step
        ly = y + 42
        lh = 26 if compact else 30
        # The step list may reach to just short of the device tiles; the foot area
        # takes the space back further down (the day line needs a line up top).
        avail = max(1, (pr.bottom + 34 - ly) // lh)
        start = max(0, min(pos - 1, max(0, len(steps) - avail)))
        for st in steps[start:start + avail]:
            col = MUTED if st.get('done') else (FG if st.get('current') else (200, 204, 212))
            if st.get('current'):
                pygame.draw.rect(self.screen, (40, 56, 82), (tx - 8, ly - 2, tw + 8, lh - 2), border_radius=6)
            my = ly + lh // 2 - 1
            if st.get('done'):                       # done: tick
                pygame.draw.lines(self.screen, OK, False, [(tx + 2, my), (tx + 6, my + 4), (tx + 13, my - 5)], 2)
            elif st.get('current'):                  # current: triangle
                pygame.draw.polygon(self.screen, ACC, [(tx + 2, my - 6), (tx + 2, my + 6), (tx + 13, my)])
            else:                                    # open: ring
                pygame.draw.circle(self.screen, MUTED, (tx + 8, my), 4, 1)
            text(self.screen, f"{st['i']}. {st['name']}", tx + 22, ly, 20 if compact else 22, col, maxw=int(tw * 0.55) - 22)
            text(self.screen, st.get('text') or '', tx + int(tw * 0.57), ly + 2, 16 if compact else 18, MUTED, maxw=int(tw * 0.43))
            ly += lh

        self._card_footer(sl, rect, pr, pad, snap, compact)

    def _card_footer(self, sl, rect, pr, pad, snap, compact):
        # Devices of the slave
        dy = pr.bottom + 14
        text(self.screen, T['devices_title'], rect.left + pad, dy, 16, MUTED)
        dx = rect.left + pad
        dy += 22
        devs = list(sl.get('devices') or []) + list(sl.get('devices_offline') or [])
        # Height of the TALLEST tile of this row. Without it everything that
        # follows slides into the tiles: `dy` grew so far only at the line
        # break, and with 44-pixel tiles `dy + 34` lay just barely at the lower
        # edge. That was always tight - with the new condition line it becomes
        # noticeable (counter-proof Philine 2026-09-11).
        rowh = 0
        for uuid in devs[:4]:
            st = snap['devices'].get(uuid, {})
            online = uuid in (sl.get('devices') or [])
            label = (sl.get('device_labels') or {}).get(uuid) or st.get('fw', '').split('-')[0] or uuid[:6]
            s_txt, s_col = dev_state_text(st if online else None)
            c_txt, c_col = dev_cond_text(st if online else None)
            g_txt, g_col, g_fill = cage_info(st if online else None)
            # The tile grows only when there really is something to show - a
            # MagLock has no condition, and an empty third line would be mere
            # air. The cage bar is a fourth line, only in cage mode.
            th = 62 if c_txt else 44
            if g_txt:
                th += 26
            tile = pygame.Rect(dx, dy, (rect.width - 2 * pad) // 2 - 6, th)
            panel(self.screen, tile, (30, 33, 40), 8)
            pygame.draw.circle(self.screen, s_col if online else MUTED, (tile.left + 14, tile.top + 14), 5)
            text(self.screen, label, tile.left + 26, tile.top + 4, 16, FG, maxw=tile.width - 32)
            text(self.screen, s_txt, tile.left + 26, tile.top + 23, 15, s_col, maxw=tile.width - 32)
            if c_txt:
                text(self.screen, c_txt, tile.left + 26, tile.top + 41, 15, c_col, maxw=tile.width - 32)
            if g_txt:
                by = tile.top + (60 if c_txt else 42)
                bar = pygame.Rect(tile.left + 26, by + 4, 90, 8)
                pygame.draw.rect(self.screen, (50, 54, 64), bar, border_radius=4)
                if g_fill > 0:
                    pygame.draw.rect(self.screen, g_col, pygame.Rect(bar.left, bar.top, int(bar.width * g_fill), bar.height), border_radius=4)
                mx = bar.left + bar.width // 3          # the threshold
                pygame.draw.line(self.screen, FG, (mx, bar.top - 2), (mx, bar.bottom + 2), 2)
                text(self.screen, g_txt, bar.right + 8, by, 13, g_col, maxw=tile.width - 32 - 98)
            rowh = max(rowh, th)
            dx += tile.width + 12
            if dx + tile.width > rect.right - pad:
                dx = rect.left + pad
                dy += rowh + 8
                rowh = 0
        dy += rowh          # the last, possibly incomplete row

        # last events (left) and Weekly plan / running runs (right)
        evs = sl.get('events') or []
        ey = dy + 16
        half = (rect.width - 2 * pad) // 2
        L = sl.get('logbook') or {}
        plan = L.get('plan') or []
        runs = L.get('runs') or []
        px = rect.left + pad + half + 8
        text(self.screen, T['plan'], px, ey, 16, MUTED)
        py = ey + 22

        # Running Sanctions (doc 26) first in the left column - BEFORE the
        # events. A sanction that is in force and that nobody sees is a trap
        # instead of a notice, and the slave stands in front of exactly this
        # screen. What is in force now weighs more than what just was.
        sanc = L.get('sanctions') or []
        if sanc:
            text(self.screen, T['sanctions_title'], rect.left + pad, ey, 16, MUTED)
            ey += 20
            for sa in sanc[:3]:
                line = sa.get('name') or sa.get('key')
                if sa.get('until'):
                    line += ' · ' + str(sa['until'])[11:16]
                elif sa.get('runs_left'):
                    line += f" · {sa['runs_left']}×"
                elif sa.get('until_day'):
                    line += ' · ' + T['st'].get('day', 'Tag')
                text(self.screen, f"▪ {line}", rect.left + pad, ey, 16, ERR, maxw=half - 12)
                ey += 20
            ey += 6
        # Streaks (doc 44 §3): the running count, and a loss of the last day in
        # red - that is the line the concept asked to be seen.
        stk = [x for x in (L.get('streaks') or []) if x.get('count') or x.get('broken_recent')]
        if stk:
            text(self.screen, T['streaks_title'], rect.left + pad, ey, 16, MUTED)
            ey += 20
            for x in stk[:3]:
                unit = T['unit'].get(x.get('unit'), x.get('unit', ''))
                if x.get('broken_recent') and not x.get('count'):
                    text(self.screen, f"× {x.get('name')} · {T['streak_lost'].format(n=x.get('broken_count', 0))} {unit}",
                         rect.left + pad, ey, 16, ERR, maxw=half - 12)
                else:
                    line = f"▲ {x.get('name')} · {x.get('count', 0)} {unit}"
                    if x.get('next'):
                        line += f" → {x['next']}"
                    text(self.screen, line, rect.left + pad, ey, 16, OK, maxw=half - 12)
                ey += 20
            ey += 6
        if evs:
            text(self.screen, T['events_title'], rect.left + pad, ey, 16, MUTED)
        ey += 22
        for e in evs[-5:]:
            name = T['ev'].get(e.get('event'), e.get('event'))
            col = {'punish': ERR, 'warn': WARN, 'fault': ERR, 'result': ACC, 'reward': OK}.get(e.get('cls'), (200, 204, 212))
            text(self.screen, f"{time.strftime('%H:%M:%S', time.localtime(e.get('ts', 0)))}  {name}", rect.left + pad, ey, 16, col, maxw=half - 12)
            ey += 20
        for r in runs[:2]:
            text(self.screen, f"▶ {r.get('action')} · {int(r.get('elapsed_s', 0))} s · {r.get('punish', 0)} {T['punish_short']}", px, py, 16, WARN, maxw=half - 8)
            py += 20
        if sl.get('attention'):
            a = sl['attention']
            text(self.screen, T['attention'].format(hits=a.get('hits', 0), cues=a.get('cues', 0)), px, py, 16, WARN, maxw=half - 8)
            py += 20
        if not plan:
            text(self.screen, T['no_plan'], px, py, 15, MUTED)
        for t in plan[:5]:
            done = t.get('wt_status') == 'done'
            col = OK if done else (ERR if t.get('wt_status') == 'failed' else (200, 204, 212))
            box = pygame.Rect(px, py + 3, 13, 13)
            pygame.draw.rect(self.screen, col, box, 1, border_radius=2)
            if done:
                pygame.draw.lines(self.screen, col, False, [(px + 3, py + 9), (px + 6, py + 12), (px + 11, py + 5)], 2)
            elif t.get('wt_status') == 'failed':
                pygame.draw.line(self.screen, col, (px + 3, py + 6), (px + 10, py + 13), 2)
                pygame.draw.line(self.screen, col, (px + 10, py + 6), (px + 3, py + 13), 2)
            text(self.screen, f"{t.get('name')} {t.get('target_text', '')}", px + 20, py, 16, col, maxw=half - 28)
            py += 20

    def instruction_card(self, instr, x, y, w, h, compact):
        """Neutral instruction large and calm — no alarm red, it is not a punishment.
        The box stays within the assigned height: font size and number of lines
        follow from it, otherwise the text runs into the device tiles."""
        h = max(64, int(h))
        r = pygame.Rect(x - 6, y, w + 6, h)
        panel(self.screen, r, (22, 30, 40), 10, ACC)
        left = int(instr.get('remaining_s') or 0)
        text(self.screen, T['instruction'], r.left + 12, r.top + 6, 16, ACC, bold=True)
        if left > 0:
            text(self.screen, T['instruction_left'].format(min=max(1, (left + 59) // 60)),
                 r.right - 12, r.top + 6, 16, MUTED, align='right')
        size = 26 if compact else 34
        avail = h - 34
        lines = max(1, min(3, avail // int(size * 1.25)))
        if lines == 1 and avail < size + 6:
            size = max(18, avail - 6)
        wrap(self.screen, instr['text'], r.left + 12, r.top + 30, w - 18,
             size=size, color=FG, maxlines=lines)

    def review_card(self, rv, x, y, w, h, compact):
        """Weekly Report (first 40 s after the login)."""
        panel(self.screen, pygame.Rect(x - 6, y, w + 6, max(200, h)), (34, 30, 22), 10, WARN)
        text(self.screen, T['review_title'].format(week=rv.get('week', '')), x + 8, y + 8, 22 if compact else 26, WARN, bold=True, maxw=w - 16)
        a, b = rv.get('rank_before'), rv.get('rank_after')
        col = OK if (b or 0) > (a or 0) else (ERR if (b or 0) < (a or 0) else FG)
        text(self.screen, T['review_rank'].format(a=a, b=b, name=rv.get('rank_name_after', '')), x + 8, y + 42, 19 if compact else 22, col, bold=True, maxw=w - 16)
        text(self.screen, T['review_score'].format(score=rv.get('score', 0), place=rv.get('place') or '–'), x + 8, y + 70, 17 if compact else 19, FG, maxw=w - 16)
        text(self.screen, T['review_plan'].format(done=rv.get('plan_done', 0), total=rv.get('plan_total', 0), punish=rv.get('punish', 0)), x + 8, y + 94, 17 if compact else 19, FG, maxw=w - 16)
        gy = y + 122
        text(self.screen, T['review_grades'] + ':', x + 8, gy, 16, MUTED)
        gx = x + 90
        for g in [g for g in (rv.get('grades') or '').split(',') if g][:12]:
            draw_grade(self.screen, g, gx, gy - 4, 26)
            gx += 32
        if rv.get('reason'):
            text(self.screen, rv['reason'], x + 8, gy + 30, 15, MUTED, maxw=w - 16)

    def session(self, snap):
        self.background(60)
        slaves = snap['session'].get('slaves') or []
        margin = 16
        if len(slaves) == 1:
            self.slave_card(slaves[0], pygame.Rect(margin, margin, W - 2 * margin, H - 34 - 2 * margin), snap)
        else:
            per_page = 2
            pages = max(1, math.ceil(len(slaves) / per_page))
            if time.time() - self.page_t > 8:
                self.page_t = time.time()
                self.page = (self.page + 1) % pages
            self.page %= pages
            shown = slaves[self.page * per_page:(self.page + 1) * per_page]
            cw = (W - 3 * margin) // 2
            for i, sl in enumerate(shown):
                self.slave_card(sl, pygame.Rect(margin + i * (cw + margin), margin, cw, H - 34 - 2 * margin), snap, compact=True)
            if pages > 1:
                text(self.screen, f"{self.page + 1}/{pages}", W - 24, 8, 16, MUTED, align='right')
        self.statusbar(snap)

    # --- Overlays -------------------------------------------------------------------
    def toasts(self, snap):
        # Login/logout/unknown tag: large and centred (idle) or top right (session);
        # step messages: small, top right.
        in_session = bool(snap['session'].get('slaves'))
        has_lb = bool((snap.get('leaderboard') or {}).get('week'))
        y = 60 if in_session else (40 if has_lb else H // 2 + 90)
        for t in snap['toasts'][-3:]:
            kind, txt = t[1], t[2]          # t[0] is the deadline that the cleaner checks
            extra = t[3] if len(t) > 3 else None
            col = {'login': OK, 'logout': ACC, 'unknown': WARN, 'step': FG, 'grade': GRADE_COL.get(extra, FG), 'badge': WARN}.get(kind, FG)
            size = 20 if (in_session or kind == 'step') else 28
            f = font(size, True)
            icon = (size + 14) if kind == 'grade' and extra else 0
            w = min(W - 80, f.size(txt)[0] + 40 + icon)
            x = W - 30 - w if in_session else (W - w) // 2
            r = pygame.Rect(x, y, w, size + 22)
            panel(self.screen, r, (24, 26, 32), 10, col)
            if icon:
                draw_grade(self.screen, extra, r.left + 12, y + 8, size + 6)
            text(self.screen, txt, r.centerx + icon // 2, y + 10, size, col, bold=True, align='center', maxw=w - 30 - icon)
            y += size + 32

    def special(self, sp):
        """Special image promotion/demotion (9 s)."""
        col = OK if sp.get('up') else ERR
        band = pygame.Surface((W, 200), pygame.SRCALPHA)
        band.fill((*col, 230))
        self.screen.blit(band, (0, H // 2 - 100))
        img = slave_photo(sp.get('slave_id'), (104, 130))
        cx = W // 2 + (60 if img else 0)
        if img:
            self.screen.blit(img, (W // 2 - 340, H // 2 - 65))
            pygame.draw.rect(self.screen, (255, 255, 255), (W // 2 - 340, H // 2 - 65, 104, 130), 2, border_radius=6)
        text(self.screen, T['promotion'] if sp.get('up') else T['demotion'], cx, H // 2 - 84, 56, (255, 255, 255), bold=True, align='center')
        text(self.screen, T['rank_now'].format(name=sp.get('name', ''), rank_name=sp.get('rank_name', ''), rank=sp.get('rank')),
             cx, H // 2 + 8, 30, (255, 255, 255), align='center', maxw=W - 300 if img else W - 60)
        text(self.screen, f"{T['rank']} {sp.get('from')} → {sp.get('rank')}", cx, H // 2 + 50, 24, (255, 255, 255), align='center')

    def emergency(self):
        band = pygame.Surface((W, 150), pygame.SRCALPHA)
        band.fill((*EMG, 235))
        self.screen.blit(band, (0, H // 2 - 75))
        text(self.screen, T['emergency'], W // 2, H // 2 - 58, 40, (255, 255, 255), bold=True, align='center', maxw=W - 40)
        text(self.screen, T['emergency_sub'], W // 2, H // 2 + 6, 22, (255, 230, 235), align='center', maxw=W - 40)

    def central_lost(self):
        band = pygame.Surface((W, 40), pygame.SRCALPHA)
        band.fill((*ERR, 220))
        self.screen.blit(band, (0, 0))
        text(self.screen, T['central_off'], W // 2, 8, 22, (255, 255, 255), bold=True, align='center')

    def frame(self, snap):
        if snap['session'].get('slaves'):
            self.session(snap)
        else:
            self.attract(snap)
        if not snap['central_alive'] and snap['connected']:
            self.central_lost()
        self.toasts(snap)
        if snap.get('special'):
            self.special(snap['special'])
        if snap['emergency']:
            self.emergency()


# --------------------------------------------------------------------------- #
def demo_state():
    now = time.time()
    S.last_hb = now
    S.connected = True
    S.devices['collar'] = {'state': 'active', 'mode': 'timer', 'remaining_s': 187, 'fw': 'Collar-3.0.3', '_seen': now}
    S.devices['lock'] = {'state': 'active', 'lock': 'locked', 'remaining_s': 254, 'fw': 'MagLock-3.0', '_seen': now}
    steps = [('Halsband-Einstellungen', 'Impulsstärke 10, Vibrationsstärke 25'), ('Magnetschloss', 'Haltezeit 5 min, Zeit zum Anlegen 60 s'),
             ('Warten', 'Dauer 1 min'), ('Modus: Timer', 'Maximaldauer 4 min, Takt 60 s, Anzahl 4'), ('Warten', 'Dauer 5 min'),
             ('Modus: aus / Fernsteuerung', '')]
    S.session = {'slaves': [{
        'slave_id': 3, 'name': 'Test Beide', 'program': {'id': 4, 'name': 'TEST Beide'}, 'login_ts': now - 200,
        'progress': {'pos': 3, 'total': 6, 'finished': False, 'next_in_s': 42,
                     'steps': [{'i': i + 1, 'name': n, 'text': t, 'done': i < 3, 'current': i == 3} for i, (n, t) in enumerate(steps)]},
        'devices': ['collar', 'lock'], 'devices_offline': [],
        'events': [{'ts': now - 90, 'event': 'locked'}, {'ts': now - 30, 'event': 'warn', 'cls': 'warn'}, {'ts': now - 28, 'event': 'shock', 'cls': 'punish'}],
        'logbook': {'rank': 4, 'rank_name': 'Köter', 'score_week': 129, 'place_week': 1, 'points_total': 812, 'place_total': 2,
                    'forecast': {'risk': 'up', 'text': 'Aufstieg in Reichweite — Wochenplan halten'},
                    'plan': [{'name': 'Modus: Pet', 'target_text': '30 min', 'wt_status': 'done'}, {'name': 'Nasenknopf', 'target_text': '2 min', 'wt_status': 'open'},
                             {'name': 'Trainer: Ausdauer', 'target_text': '45 s', 'wt_status': 'open'}],
                    'runs': [{'action': 'TIMER', 'elapsed_s': 61, 'punish': 1}], 'badges': [{'key': 'first_a', 'name': 'Erste A'}]},
        'attention': {'active': True, 'cues': 3, 'hits': 2, 'missed': 1, 'cue_open': False},
        'day': {'status': 'running', 'started': '2026-09-10 09:00:00', 'end': '2026-09-10 15:00:00',
                'remaining_s': 7200, 'remaining_min': 120, 'plan': 'Standardtag', 'block': 'plan',
                'block_label': 'Aufgabe aus dem Wochenplan', 'blocks_done': 2, 'tasks': 3,
                'free_min': 0, 'train_min': 28, 'next': {'kind': 'pause', 'label': 'Pause. Du darfst jetzt etwas essen.', 'minutes': 30}},
    }]}
    S.leaderboard = {'week': [{'place': 1, 'name': 'Test Beide', 'rank': 4, 'rank_name': 'Köter', 'points': 129},
                              {'place': 2, 'name': 'Test Collar', 'rank': 2, 'rank_name': 'Wurm', 'points': 77}],
                     'challenges': [{'id': 1, 'week': '2026-W37', 'action': 'NOSE_BUTTON', 'action_name': 'Nasenknopf',
                                     'target': 40, 'target_text': '40 s', 'unit': 's', 'metric': 'Haltezeit',
                                     'status': 'decided', 'winner': 3,
                                     'entries': [{'place': 1, 'slave_id': 3, 'name': 'Test Beide', 'points': 34, 'grade': 'A', 'best': 52, 'punish': 0, 'note': None},
                                                 {'place': 2, 'slave_id': 2, 'name': 'Test Collar', 'points': 21, 'grade': 'C', 'best': 41, 'punish': 2, 'note': None},
                                                 {'place': 3, 'slave_id': 1, 'name': 'Test MagLock', 'points': None, 'grade': None, 'best': None, 'punish': None, 'note': 'nicht angetreten'}]}]}
    S.toasts.append((now + 30, 'grade', 'Test Beide: Nasenknopf — Note A, 30 Punkte · Bestleistung!', 'A'))
    if opts.snapshot and 'instr' in opts.snapshot:
        S.session['slaves'][0]['day'].update({'block': 'pause', 'block_label': 'Pause',
                                              'instruction': {'text': 'Pause. Du darfst jetzt etwas essen.', 'remaining_s': 1500}})
        S.toasts.clear()
    if opts.snapshot and 'chal' in opts.snapshot:
        S.session = {'slaves': []}
        S.leaderboard.pop('week', None)      # show only the second Leaderboard
        S.toasts.clear()
    if opts.snapshot and 'review' in opts.snapshot:
        S.session['slaves'][0]['login_ts'] = now
        S.session['slaves'][0]['review'] = {'week': '2026-W36', 'rank_before': 3, 'rank_after': 4, 'rank_name_after': 'Köter',
                                            'reason': '4 Aufgaben ≥ B, 1× Wochenbester', 'score': 240, 'place': 1, 'grades': 'A,B,A,C,A',
                                            'plan_done': 4, 'plan_total': 4, 'punish': 3}
    if opts.snapshot and 'rank' in opts.snapshot:
        S.special = {'until': now + 30, 'up': True, 'name': 'Test Beide', 'rank': 4, 'rank_name': 'Köter', 'from': 3, 'slave_id': 3}
    if opts.snapshot and 'idle' in opts.snapshot:
        S.session = {'slaves': []}


def main():
    pygame.init()
    pygame.mouse.set_visible(False)
    flags = pygame.FULLSCREEN if FULLSCREEN and not opts.snapshot else 0
    try:
        screen = pygame.display.set_mode((W, H), flags)
    except pygame.error as e:
        log.error('Kein Bildschirm ueber Treiber %s: %s', os.environ.get('SDL_VIDEODRIVER', 'auto'), e)
        log.error('Pi OS Lite: Benutzer in den Gruppen video, render, input, tty? Laeuft schon ein anderes '
                  'Programm am Bildschirm (X, zweite Instanz)? Test: ls -l /dev/dri/  und  id')
        sys.exit(1)
    pygame.display.set_caption('Punisher Display')
    log.info('display %dx%d driver=%s fullscreen=%s', W, H, pygame.display.get_driver(), bool(flags))

    if opts.demo:
        demo_state()
    else:
        bus = Bus()
        m = config['mqtt'] if 'mqtt' in config else {}
        # An account of its own where one exists (2.1.1) — see
        # libs/mqttaccount.py. The display's account carries NO write right at
        # all; that is a statement, not caution: what stands on the screen can
        # trigger nothing.
        user, pw, own = mqttaccount.account(config, 'mqtt_display')
        if user:
            bus.username_pw_set(user, pw)
        if own:
            log.info('mqtt: Konto %s', user)
        else:
            log.warning('mqtt: kein eigenes Brokerkonto ([mqtt_display] fehlt) — '
                        'die Zugriffsliste des Brokers wirkt fuer die Anzeige nicht')
        bus.reconnect_delay_set(1, 30)
        try:
            mqtttls.configure(bus, config, log)        # TLS (2.3, doc 53)
            bus.connect_async(m.get('hostname', 'localhost'), mqtttls.port(config), 60)
        except (OSError, ValueError, FileNotFoundError) as e:
            log.error('mqtt: %s', e)
        bus.loop_start()

    r = Renderer(screen)
    clock = pygame.time.Clock()
    started = time.time()
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_q)):
                running = False
        snap = S.snapshot()
        r.frame(snap)
        pygame.display.flip()
        if opts.snapshot and time.time() - started > 1.5:
            pygame.image.save(screen, opts.snapshot)
            log.info('snapshot -> %s', opts.snapshot)
            running = False
        clock.tick(FPS)
    pygame.quit()


if __name__ == '__main__':
    main()
