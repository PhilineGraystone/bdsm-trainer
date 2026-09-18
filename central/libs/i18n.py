# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Multilingual support of the installation — German is the source language, English is a translation.

Same principle as with the action catalogue (doc 01): the texts live in the code, not in
the database. No extra package, no gettext tooling in the build — one table per
language in `lang_<code>.py`, so that a further language is one single new file.

Usage
-----
    import i18n
    i18n.configure('de')                 # installation default out of config.ini
    i18n.set_lang('en')                  # per thread (web: per request)
    i18n.t('web.weekly.title')           # text out of the table
    i18n.t('action.PET', 'Modus: Pet')   # source text sits in the code -> second argument
    i18n.t('day.rest', min=42)           # placeholders as with str.format

Resolution: table of the current language -> source text passed along -> German
table -> the key itself. A missing English text therefore falls back to the
German one and never breaks a page.

The language is **thread-local**: the web interface runs threaded, every request sets
its own language, central unit and display stay on the installation default.
"""

import logging
import threading

logger = logging.getLogger(__name__)

LANGS = ('de', 'en')
FALLBACK = 'de'

LANG_NAMES = {'de': 'Deutsch', 'en': 'English'}

_tables = {}
_default = FALLBACK
_cur = threading.local()


def _load(lang):
    """Load one language's table (lang_de.py / lang_en.py)."""
    if lang in _tables:
        return _tables[lang]
    try:
        mod = __import__('lang_' + lang)
        _tables[lang] = dict(getattr(mod, 'TEXTS', {}))
    except ImportError:
        if lang != FALLBACK:          # German is the source language and has no table
            logger.warning('i18n: no table for language %r', lang)
        _tables[lang] = {}
    return _tables[lang]


def configure(lang):
    """Set the installation default (config.ini). Unknown language -> fallback."""
    global _default
    lang = (lang or '').strip().lower()
    if lang not in LANGS:
        if lang:
            logger.warning('i18n: unknown language %r, using %r', lang, FALLBACK)
        lang = FALLBACK
    _default = lang
    _load(lang)
    _load(FALLBACK)
    return _default


def default_lang():
    return _default


def set_lang(lang):
    """Set the language of this thread (web: per request). None = installation default."""
    lang = (lang or '').strip().lower()
    _cur.lang = lang if lang in LANGS else None
    return lang


def lang():
    return getattr(_cur, 'lang', None) or _default


def t(key, src=None, lang_=None, **kw):
    """Return the translated text. `src` is the German source text when it sits in the code."""
    cur = lang_ or lang()
    text = _load(cur).get(key)
    if text is None:
        text = src
    if text is None:
        text = _load(FALLBACK).get(key)
    if text is None:
        return key
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        logger.warning('i18n: placeholder mismatch in %r (%s)', key, cur)
        return text


def _(text, **kw):
    """Translation of a German source text — the German text IS the key.

    For interface texts that sit in the code or in the templates. Where a
    translation is missing, the German text stays; so nothing ever breaks.
    Placeholders as with str.format:  _('Block {n} von {m}', n=1, m=5)
    """
    cur = lang()
    if cur == FALLBACK:
        out = text
    else:
        out = _load(cur).get(text, text)
    if not kw:
        return out
    try:
        return out.format(**kw)
    except (KeyError, IndexError, ValueError):
        logger.warning('i18n: placeholder mismatch in %r (%s)', text[:60], cur)
        return out


def d(mapping):
    """Translate the values of a registry dictionary (text or tuple of texts).

    For the fixed tables out of the code — badges, privileges, rule set,
    device capabilities — that go to a template as a whole.
    """
    out = {}
    for k, v in mapping.items():
        if isinstance(v, (tuple, list)):
            out[k] = type(v)(_(x) if isinstance(x, str) else x for x in v)
        elif isinstance(v, str):
            out[k] = _(v)
        else:
            out[k] = v
    return out


def has(key, lang_=None):
    return _load(lang_ or lang()).get(key) is not None


def missing(lang_='en'):
    """How many known keys are still missing in a language — for a checklist."""
    return len(_load(lang_))


def choices():
    """[(code, display name)] for the language picker in the web interface."""
    return [(c, LANG_NAMES.get(c, c)) for c in LANGS]
