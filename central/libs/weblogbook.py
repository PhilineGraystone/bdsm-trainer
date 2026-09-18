# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Web interface: Logbook, Leaderboard, Weekly plan, Ranks, Points, Report,
Export, Challenges (doc 14). Pages (blueprint 'lb') and
REST API (/api/v1, blueprint 'lbapi'), registered from punisher-web.py.

Reading and simple changes (plan, setting/freezing a rank, level, privileges,
names, numbers) go straight into the DB + notify_reload('logbook'); everything
that runs over the punishment channel or triggers a grading goes as a request
to the central unit (mq.request) — only the central unit publishes on that channel.
"""

import csv
import datetime
import hashlib
import io
import json
import zipfile

from flask import (Blueprint, Response, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

import actions
import audit
import budgets as budgetsmod
import pauses as pausesmod
import streaks as streaksmod
import dayform as dayformmod
import devicemodels
import i18n
import logbook as lbmod
import mystery
import profiles
import routines
import scenarios as scenariosmod
import taskblocks
import tasktypes

GRADE_ORDER = 'ABCDEF'


BLOCK_KINDS = {
    'plan':    ('Wochenplan', 'Zeitbudget: die Zentrale arbeitet offene Planaufgaben ab'),
    'program': ('Programm', 'ein festes Programm läuft einmal durch'),
    'free':    ('freies Training', 'Zeitbudget: die Zentrale wählt passende Aufgaben, halbe Gewichtung'),
    'pause':   ('Pause / Anweisung', 'neutrale Anweisung, zählt als Pause'),
    'mystery': ('Mystery', 'die Zentrale zieht im Fenster Zeitpunkt und Eintrag aus dem Pool; der Bildschirm zeigt „?“'),
}

# What the VIEWS have to be able to name, on top of the block kinds one can
# choose. `idle` is not a block: it is the state of a day that currently has
# nothing to do (doc 58 §4). It must never show up in the editor's selection,
# which is why this is a second dict and not an entry above — the editor
# renders BLOCK_KINDS, the slave page renders this one.
VIEW_KINDS = dict(BLOCK_KINDS,
                  idle=('Leerlauf', 'gerade ist nichts möglich — der Tag wartet und sieht wieder nach'))


def _week_list(n=8):
    w = lbmod.week_str()
    out = [w]
    for _ in range(n - 1):
        w = lbmod.prev_week(w)
        out.append(w)
    return out


def _pseudonym(slave_id, salt):
    return 'T' + hashlib.sha256(f'{salt}:{slave_id}'.encode()).hexdigest()[:8]


def _grade_icon_svg(g):
    """Simple glyphs A–F as inline SVG (default; pics/grades/<A-F>.png replaces them)."""
    g = (g or '').upper()
    col = {'A': '#f0c040', 'B': '#7cb7ff', 'C': '#5ec27a', 'D': '#e8b84a', 'E': '#e5646b', 'F': '#9aa3ad'}.get(g, '#9aa3ad')
    body = {
        'A': '<path d="M4 20 L7 9 L12 14 L17 6 L22 14 L27 9 L30 20 Z" fill="{c}"/><rect x="4" y="22" width="26" height="4" fill="{c}"/>',  # crown
        'B': '<circle cx="17" cy="20" r="8" fill="{c}"/><path d="M11 4 L17 12 L23 4 Z" fill="{c}" opacity=".8"/>',                       # medal
        'C': '<path d="M6 18 L14 26 L28 8" stroke="{c}" stroke-width="5" fill="none" stroke-linecap="round"/>',                          # check mark
        'D': '<rect x="15" y="5" width="4" height="15" fill="{c}"/><circle cx="17" cy="26" r="2.6" fill="{c}"/>',                          # exclamation mark
        'E': '<path d="M17 4 L31 28 L3 28 Z" fill="none" stroke="{c}" stroke-width="3"/><rect x="15.5" y="12" width="3" height="9" fill="{c}"/><circle cx="17" cy="24.5" r="1.8" fill="{c}"/>',  # warning sign
        'F': '<path d="M7 7 L27 27 M27 7 L7 27" stroke="{c}" stroke-width="5" stroke-linecap="round"/>',                                  # cross
    }.get(g, '<circle cx="17" cy="17" r="10" fill="none" stroke="{c}" stroke-width="3"/>').format(c=col)
    return f'<svg class="grade grade-{g}" viewBox="0 0 34 34" width="22" height="22" aria-label="Note {g}" title="Note {g}">{body}</svg>'


def register(app, ctx):
    """ctx: namespace from punisher-web.py (q, x, db, mq, config, WEB_USER, LB, GRADE_DIR, photo_file ...)."""
    lb = ctx.LB
    q, x = ctx.q, ctx.x
    pages = Blueprint('lb', __name__)
    api = Blueprint('lbapi', __name__, url_prefix='/api/v1')

    # ------------------------------------------------------------------ #
    @app.template_filter('grade_icon')
    def grade_icon(g):
        from markupsafe import Markup
        g = (g or '').upper()
        if g and ctx.grade_file(g):
            return Markup(f'<img class="grade" src="{url_for("lb.grade_png", g=g)}" width="22" height="22" alt="Note {g}" title="Note {g}">')
        return Markup(_grade_icon_svg(g))

    @app.template_filter('action_name')
    def action_name(code):
        a = actions.get(code)
        if a:
            return a.name
        return {'BONUS_WEEK': 'Bonus: Wochenplan', 'BONUS_CHALLENGE': 'Bonus: Herausforderung'}.get(code, code)

    @app.template_filter('target_text')
    def target_text(v, unit='s'):
        return lbmod.Logbook.target_text(v, unit)

    @app.template_filter('metrics_text')
    def metrics_text(m):
        if not m:
            return ''
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except ValueError:
                return m
        parts = []
        for k, v in m.items():
            if k in ('punish', 'warn', 'faults', 'ratio', 'points_core', 'streak_days', 'max_min', 'shocks'):
                continue
            parts.append(f"{tasktypes.metric_label(k)}: {v}")
        return ' · '.join(parts)

    @app.context_processor
    def _inject_lb():
        return {'lb_enabled': lb.enabled, 'day_enabled': lb.day_enabled,
                'budgets_enabled': lb.budgets.enabled, 'pauses_enabled': lb.pauses.enabled,
                'streaks_enabled': lb.streaks.enabled, 'dayform_enabled': lb.dayform.enabled,
                'scenarios_enabled': lb.scenarios.enabled,
                'scenario_list': (lambda: q('SELECT sn_id, sn_name FROM scenarios ORDER BY sn_name') or []) if lb.scenarios.enabled else (lambda: []),
                'DAYFORMS': i18n.d(dayformmod.LABELS), 'DAYFORM_HELP': i18n.d(dayformmod.HELP),
                'BADGES': i18n.d(lbmod.BADGES), 'PRIVILEGES': i18n.d(lbmod.PRIVILEGES),
                'SANCTIONS': i18n.d(lbmod.SANCTIONS),
                'cur_week': lbmod.week_str(), 'next_week': lbmod.next_week(lbmod.week_str()),
                'TRAINABLE': [a for a in actions.ACTIONS if a.trainable], 'tasktypes': tasktypes,
                'limits': lb.limits, 'BLOCK_KINDS': i18n.d(VIEW_KINDS),
                'routines_enabled': lb.routines_enabled,
                # as a function, so that not every page reloads the waveforms
                # Only tasks on the time axis: the list fills the selection for
                # the weekly plan and the challenge, and a stimulus or a reward
                # cannot be graded there (check 2026-09-11).
                'routine_list': (lambda: routines.task_routines(q)) if lb.routines_enabled else (lambda: [])}

    def login_required(f):
        return ctx.login_required(f)

    # Invalid numbers out of forms/JSON (int('abc')) are input errors, not a 500
    # (review 2026-09-10).
    @pages.errorhandler(ValueError)
    def _bad_value_page(e):
        flash(f'Ungültige Eingabe: {e}', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    @api.errorhandler(ValueError)
    def _bad_value_api(e):
        return jsonify(ok=False, error=f'ungültiger Wert: {e}'), 400

    def user():
        return session.get('user') or ctx.WEB_USER

    def slave_or_404(sid):
        row = q('SELECT slave_id, slave_name FROM slaves WHERE slave_id=%s', (sid,), one=True)
        if not row:
            abort(404)
        return row

    def runs(where='', params=(), limit=100):
        rows = q('SELECT a.*, s.slave_name FROM achievements a JOIN slaves s ON s.slave_id=a.ach_slave '
                 + ('WHERE ' + where if where else '') + ' ORDER BY a.ach_id DESC LIMIT %s', tuple(params) + (limit,))
        for r in rows:
            try:
                r['metrics'] = json.loads(r['ach_metrics']) if r['ach_metrics'] else {}
            except ValueError:
                r['metrics'] = {}
        return rows

    def weekly(sid, week):
        rows = q('SELECT * FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s ORDER BY wt_kind, wt_id', (sid, week))
        names = {}
        for r in rows:
            t = tasktypes.get(r['wt_action'])
            r['unit'] = t.target_unit if t else 's'
            ro = r.get('wt_routine')
            if ro:
                if ro not in names:
                    row = routines.get(q, ro)
                    names[ro] = row['ro_name'] if row else '?'
                r['routine_name'] = names[ro]
        return rows

    # ================================================================== #
    # Pages
    @pages.route('/grades/<g>.png')
    @login_required
    def grade_png(g):
        if len(g) != 1 or g.upper() not in GRADE_ORDER:
            abort(404)
        f = ctx.grade_file(g.upper())
        if not f:
            abort(404)
        return send_from_directory(ctx.GRADE_DIR, f, max_age=300)

    @pages.route('/logbook')
    @login_required
    def logbook_view():
        f = {k: request.args.get(k, '').strip() for k in ('slave', 'action', 'week', 'status')}
        where, params = [], []
        if f['slave'].isdigit():
            where.append('a.ach_slave=%s'); params.append(int(f['slave']))
        if f['action']:
            where.append('a.ach_action=%s'); params.append(f['action'])
        if f['week']:
            where.append('a.ach_week=%s'); params.append(f['week'])
        if f['status']:
            where.append('a.ach_status=%s'); params.append(f['status'])
        rows = runs(' AND '.join(where), params, 200)
        slaves = q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name')
        return render_template('lb_logbook.html', rows=rows, f=f, slaves=slaves, weeks=_week_list(),
                               actions_all=[a for a in actions.ACTIONS if a.trainable])

    @pages.route('/leaderboard')
    @login_required
    def leaderboard_view():
        week = request.args.get('week') or lbmod.week_str()
        board = lb.leaderboard(week) if lb.enabled else {'week': [], 'total': [], 'ranks': []}
        reviews = q('SELECT r.*, s.slave_name FROM weekly_review r JOIN slaves s ON s.slave_id=r.wr_slave WHERE r.wr_week=%s ORDER BY r.wr_score DESC', (week,))
        return render_template('lb_leaderboard.html', board=board, week=week, weeks=_week_list(12), reviews=reviews)

    @pages.route('/weekly')
    @login_required
    def weekly_view():
        week = request.args.get('week') or lbmod.week_str()
        slaves = q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name')
        known = ctx.known_capabilities()
        for s in slaves:
            s['tasks'] = weekly(s['slave_id'], week)
            s['rank'] = lb.rank_of(s['slave_id'])[0] if lb.enabled else 1
            s['forecast'] = lb.forecast(s['slave_id'], week) if (lb.enabled and week == lbmod.week_str()) else None
            # Device filter (decision Philine 2026-09-10): a task for which the slave
            # has no device he cannot fulfil — make that visible here.
            caps = ctx.slave_capabilities(s['slave_id'])
            for t in s['tasks']:
                a = actions.get(t['wt_action'])
                need = a.capability if a else None
                t['missing'] = bool(need and need not in caps)
                t['unknown_dev'] = bool(need and need not in known)
                t['cap_label'] = devicemodels.cap_label(need)[0] if need else None
        weeks = [lbmod.next_week(lbmod.week_str())] + _week_list(6)
        # 'proposed' no longer arises (doc 14 §12.2: the plan is valid at once); old
        # rows should still be settable to valid by the supervisor, though.
        prop = q("SELECT COUNT(*) AS n FROM weekly_tasks WHERE wt_week=%s AND wt_status='proposed'", (week,), one=True)
        return render_template('lb_weekly.html', slaves=slaves, week=week, weeks=weeks,
                               has_proposed=bool(prop and prop['n']))

    @pages.route('/weekly/action', methods=['POST'])
    @login_required
    def weekly_action():
        what = request.form.get('what')
        week = request.form.get('week') or lbmod.week_str()
        if what in ('propose', 'activate', 'review'):
            ctx.mq.request(what, user=user(), week=week if what != 'review' else request.form.get('review_week') or lbmod.prev_week(lbmod.week_str()))
            flash({'propose': f'Plan für {week} angefordert — er ist sofort gültig und kann hier geändert werden.',
                   'activate': f'Vorschläge für {week} werden aktiviert.',
                   'review': 'Wochenbewertung angefordert — Ergebnis in wenigen Sekunden unter Rangliste.'}[what], 'ok')
        elif what == 'confirm_all':
            x("UPDATE weekly_tasks SET wt_status='open', wt_by=%s WHERE wt_week=%s AND wt_status='proposed'", (user(), week))
            ctx.db().commit(); ctx.mq.notify_reload('logbook')
            audit.web('weekly_confirm_all', user(), data={'week': week})
            flash(i18n._('Alle Vorschläge bestätigt.'), 'ok')
        else:
            abort(400)
        return redirect(url_for('lb.weekly_view', week=week))

    @pages.route('/slaves/<int:sid>/weekly', methods=['POST'])
    @login_required
    def slave_weekly(sid):
        slave_or_404(sid)
        op = request.form.get('op')
        week = request.form.get('week') or lbmod.week_str()
        if op == 'add':
            code = request.form.get('action', '')
            t = tasktypes.get(code)
            if not t:
                flash('Unbekannte Aufgabe.', 'error')
                return redirect(url_for('slave_detail', sid=sid))
            target = int(request.form.get('target') or t.plan_default)
            if t.target_unit == 's' and request.form.get('unit') == 'min':
                target *= 60
            mp = int(request.form.get('max_punish') or lb.default_max_punish())
            # waveform only for a routine task; empty = the central unit picks by level
            ro = int(request.form.get('routine') or 0) or None
            if ro and not (t.level_select and lb.routines_enabled and routines.is_task(routines.get(q, ro))):
                ro = None       # not a task on the time axis -> the central unit picks by level
            if lb.routines_enabled:
                x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_routine, wt_target, wt_max_punish, wt_kind, wt_status, wt_by) "
                  "VALUES (%s,%s,%s,%s,%s,%s,'plan','open',%s)", (sid, week, code, ro, target, mp, user()))
            else:
                x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_by) "
                  "VALUES (%s,%s,%s,%s,%s,'plan','open',%s)", (sid, week, code, target, mp, user()))
            audit.web('weekly_add', user(), slave_id=sid,
                      data={'week': week, 'action': code, 'target': target, 'max_punish': mp, 'routine': ro})
        elif op in ('confirm', 'delete', 'reopen'):
            wid = int(request.form.get('wt_id') or 0)
            if op == 'confirm':
                x("UPDATE weekly_tasks SET wt_status='open', wt_by=%s WHERE wt_id=%s AND wt_slave=%s AND wt_status='proposed'", (user(), wid, sid))
            elif op == 'reopen':
                x("UPDATE weekly_tasks SET wt_status='open', wt_done_ach=NULL WHERE wt_id=%s AND wt_slave=%s", (wid, sid))
            else:
                x('DELETE FROM weekly_tasks WHERE wt_id=%s AND wt_slave=%s', (wid, sid))
            audit.web('weekly_' + op, user(), slave_id=sid, data={'wt_id': wid})
        else:
            abort(400)
        ctx.db().commit()
        ctx.mq.notify_reload('logbook', sid)
        flash('Wochenplan gespeichert.', 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#wochenplan')

    @pages.route('/slaves/<int:sid>/rank', methods=['POST'])
    @login_required
    def slave_rank(sid):
        slave_or_404(sid)
        rank_no = int(request.form.get('rank') or 1)
        frozen = request.form.get('frozen') == '1'
        lb.set_rank(sid, rank_no, by=user(), frozen=frozen, reason='Aufsicht')
        audit.web('rank_set', user(), slave_id=sid, data={'rank': rank_no, 'frozen': frozen})
        ctx.mq.notify_reload('logbook', sid)
        flash(f'Rang {rank_no} gesetzt{" und eingefroren" if frozen else ""}.', 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#rang')

    @pages.route('/slaves/<int:sid>/level', methods=['POST'])
    @login_required
    def slave_level(sid):
        slave_or_404(sid)
        code = request.form.get('action', '')
        if not tasktypes.get(code):
            abort(400)
        level = lb.set_level(sid, code, int(request.form.get('level') or 1), by=user())
        audit.web('level_set', user(), slave_id=sid, data={'action': code, 'level': level})
        ctx.mq.notify_reload('logbook', sid)
        flash(f'Aufgabenstufe {code} = {level}.', 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#wochenplan')

    @pages.route('/slaves/<int:sid>/dayform', methods=['POST'])
    @login_required
    def slave_dayform(sid):
        """Day form by the supervisor (doc 44 §5) — today, or tomorrow with `tomorrow=1`."""
        slave_or_404(sid)
        if not lb.dayform.enabled:
            flash(i18n._('Tagesform nicht verfügbar — Migration 009 fehlt.'), 'error')
            return redirect(url_for('slave_detail', sid=sid) + '#rang')
        form = request.form.get('form', 'normal')
        if form not in dayformmod.FORMS:
            abort(400)
        day = datetime.date.today() + datetime.timedelta(days=1 if request.form.get('tomorrow') else 0)
        lb.dayform.set(sid, form, user(), reason=(request.form.get('reason') or '')[:160], day=day)
        audit.web('dayform_set', user(), slave_id=sid, data={'form': form, 'day': day.isoformat(),
                                                               'reason': request.form.get('reason')})
        ctx.mq.notify_reload('logbook', sid)
        flash(i18n._('Tagesform {form} für {day} gesetzt — gilt bis Tagesende, dann wieder normal.',
                     form=i18n._(dayformmod.LABELS[form]), day=day.strftime('%d.%m.')), 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#rang')

    @pages.route('/slaves/<int:sid>/level_bounds', methods=['POST'])
    @login_required
    def slave_level_bounds(sid):
        """Bounds for the automatic level, per task (doc 44 §4). Empty = installation-wide."""
        slave_or_404(sid)
        code = request.form.get('action', '')
        if not tasktypes.get(code):
            abort(400)
        if not lb.level_bounds_enabled:
            flash(i18n._('Stufengrenzen nicht verfügbar — Migration 008 fehlt.'), 'error')
            return redirect(url_for('slave_detail', sid=sid) + '#wochenplan')
        lo = (request.form.get('min') or '').strip()
        hi = (request.form.get('max') or '').strip()
        res = lb.set_level_bounds(sid, code, int(lo) if lo.isdigit() else None, int(hi) if hi.isdigit() else None, by=user())
        audit.web('level_bounds', user(), slave_id=sid, data={'action': code, 'min': res[0] if res else None, 'max': res[1] if res else None})
        ctx.mq.notify_reload('logbook', sid)
        flash(i18n._('Stufengrenzen {code}: {lo}–{hi}.', code=code, lo=res[0] or 1, hi=res[1] or lb.sc_int('level_max', 10)), 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#wochenplan')

    @pages.route('/slaves/<int:sid>/privilege', methods=['POST'])
    @login_required
    def slave_privilege(sid):
        slave_or_404(sid)
        key = request.form.get('key', '')
        if key not in lbmod.PRIVILEGES:
            abort(400)
        if request.form.get('op') == 'revoke':
            lb.revoke_privilege(sid, key, by=user())
            flash('Privileg entzogen.', 'ok')
        else:
            lb.grant_privilege(sid, key, by=user())
            flash('Privileg erteilt.', 'ok')
        audit.web('privilege_' + request.form.get('op', 'grant'), user(), slave_id=sid, data={'key': key})
        ctx.mq.notify_reload('logbook', sid)
        return redirect(url_for('slave_detail', sid=sid) + '#rang')

    @pages.route('/slaves/<int:sid>/sanction', methods=['POST'])
    @login_required
    def slave_sanction(sid):
        """Impose or lift a sanction (doc 26).

        The counterpart to slave_privilege. Deliberately a route of its own: a
        privilege is granted, a sanction is imposed — whoever operates both from
        one button with a sign will sooner or later impose the wrong thing by
        accident.
        """
        slave_or_404(sid)
        key = request.form.get('key', '')
        if key not in lbmod.SANCTIONS:
            abort(400)
        if request.form.get('op') == 'lift':
            lb.lift_sanction(sid, key, by=user())
            flash(i18n._('Auflage aufgehoben.'), 'ok')
        else:
            hours = (request.form.get('hours') or '').strip()
            runs = (request.form.get('runs') or '').strip()
            until_day = bool(request.form.get('until_day'))
            ok = lb.impose_sanction(
                sid, key, by=user(), reason=(request.form.get('reason') or '')[:160],
                hours=float(hours) if hours.replace('.', '', 1).isdigit() and float(hours) > 0 else None,
                until_day=until_day, runs=int(runs) if runs.isdigit() and int(runs) > 0 else None)
            if not ok:
                flash(i18n._('Diese Auflage läuft schon.'), 'warn')
            elif not (hours or runs or until_day):
                # A sanction without an end is allowed - but that is exactly the
                # one that gets forgotten, so it is said out loud.
                flash(i18n._('Auflage verhängt — OHNE Ende. Sie läuft, bis jemand sie aufhebt.'), 'warn')
            else:
                flash(i18n._('Auflage verhängt.'), 'ok')
        audit.web('sanction_' + (request.form.get('op') or 'impose'), user(), slave_id=sid,
                  data={'key': key, 'hours': request.form.get('hours'),
                        'runs': request.form.get('runs'),
                        'until_day': bool(request.form.get('until_day')),
                        'reason': request.form.get('reason')})
        ctx.mq.notify_reload('logbook', sid)
        return redirect(url_for('slave_detail', sid=sid) + '#rang')

    @pages.route('/slaves/<int:sid>/channel', methods=['POST'])
    @login_required
    def slave_channel(sid):
        slave_or_404(sid)
        what = 'reward' if request.form.get('what') == 'reward' else 'punish'
        ctx.mq.request(what, user=user(), slave_id=sid, level=int(request.form.get('level') or 1),
                       kind=request.form.get('kind') or 'any', reason=request.form.get('reason') or 'aufsicht')
        flash(('Bestrafung' if what == 'punish' else 'Belohnung') + ' über den Kanal angefordert (nur wenn der Sklave angemeldet ist und ein Reizgeber horcht).', 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#rang')

    @pages.route('/slaves/<int:sid>/remark', methods=['POST'])
    @login_required
    def slave_remark(sid):
        slave_or_404(sid)
        week = request.form.get('week', '')
        x('UPDATE weekly_review SET wr_remark=%s WHERE wr_slave=%s AND wr_week=%s', (request.form.get('remark', '')[:500], sid, week))
        ctx.db().commit()
        audit.web('review_remark', user(), slave_id=sid, data={'week': week})
        flash('Bemerkung gespeichert.', 'ok')
        return redirect(url_for('lb.zeugnis', sid=sid, week=week))

    @pages.route('/zeugnis/<int:sid>/<week>')
    @login_required
    def zeugnis(sid, week):
        s = slave_or_404(sid)
        rev = q('SELECT * FROM weekly_review WHERE wr_slave=%s AND wr_week=%s', (sid, week), one=True)
        rows = runs('a.ach_slave=%s AND a.ach_week=%s', (sid, week), 200)
        tasks = weekly(sid, week)
        rank_names = {r['rank_no']: r['name'] for r in lb.ranks()}
        data = dict(slave=s, rev=rev, rows=[r for r in reversed(rows)], tasks=tasks, week=week, rank_names=rank_names,
                    monday=lbmod.week_monday(week), sunday=lbmod.week_monday(week) + datetime.timedelta(days=6))
        if request.args.get('pdf'):
            pdf = _zeugnis_pdf(data)
            if pdf is None:
                flash(i18n._('PDF-Erzeugung nicht verfügbar (reportlab fehlt) — Seite im Browser drucken.'), 'warn')
            else:
                safe = ''.join(ch if ch.isalnum() else '_' for ch in str(s['slave_name']).encode('ascii', 'ignore').decode()) or 'Sklaven'
                return Response(pdf, mimetype='application/pdf',
                                headers={'Content-Disposition': f'inline; filename="Zeugnis_{safe}_{week}.pdf"'})
        return render_template('lb_zeugnis.html', **data)

    @pages.route('/ranks', methods=['GET', 'POST'])
    @login_required
    def ranks_view():
        if request.method == 'POST':
            for no in range(1, 11):
                name = request.form.get(f'name_{no}', '').strip()[:40]
                alt = request.form.get(f'alt_{no}', '').strip()[:40]
                if not name:
                    continue
                if no == 10 or f'tasks_{no}' not in request.form:
                    # Rank 10 has no promotion rule (fields disabled in the form and
                    # therefore not transmitted): change only the names (review 2026-09-10)
                    x('UPDATE ranks SET rank_name=%s, rank_name_alt=%s WHERE rank_no=%s', (name, alt, no))
                    continue
                up_t = max(0, min(20, int(request.form.get(f'tasks_{no}') or 0)))
                up_g = (request.form.get(f'grade_{no}') or 'C').upper()[:1]
                up_b = max(0, min(10, int(request.form.get(f'best_{no}') or 0)))
                up_p = 1 if request.form.get(f'plan_{no}') else 0
                if up_g in GRADE_ORDER:
                    x('UPDATE ranks SET rank_name=%s, rank_name_alt=%s, rank_up_tasks=%s, rank_up_grade=%s, rank_up_best=%s, rank_up_plan=%s WHERE rank_no=%s',
                      (name, alt, up_t, up_g, up_b, up_p, no))
            lb.set_scoring('rank_names', 'alt' if request.form.get('rank_names') == 'alt' else 'main')
            ctx.db().commit()
            audit.web('ranks_update', user())
            ctx.mq.notify_reload('logbook')
            flash(i18n._('Ränge gespeichert.'), 'ok')
            return redirect(url_for('lb.ranks_view'))
        rows = q('SELECT * FROM ranks ORDER BY rank_no')
        holders = q('SELECT sr_rank, COUNT(*) AS n FROM slave_rank GROUP BY sr_rank')
        return render_template('lb_ranks.html', rows=rows, holders={h['sr_rank']: h['n'] for h in holders},
                               rank_names=lb.sc_str('rank_names', 'main'))

    @pages.route('/scoring', methods=['GET', 'POST'])
    @login_required
    def scoring_view():
        if request.method == 'POST':
            for k, v in request.form.items():
                if k.startswith('sc_') and not k.startswith('sc_last_'):
                    lb.set_scoring(k[3:], v.strip()[:64])
            ctx.db().commit()
            audit.web('scoring_update', user(), data={k[3:]: v for k, v in request.form.items() if k.startswith('sc_')})
            ctx.mq.notify_reload('logbook')
            flash(i18n._('Punktesystem gespeichert — gilt für alle folgenden Durchgänge.'), 'ok')
            return redirect(url_for('lb.scoring_view'))
        rows = q("SELECT * FROM scoring WHERE sc_key NOT LIKE 'last_%%' ORDER BY sc_key")
        return render_template('lb_scoring.html', rows=rows)

    # ------------------------------------------------------------------ #
    # Challenge (doc 14 §12.4): leaderboard across ALL slaves, not a duel
    def _challenge_add(code, week, target, field, by, routine=None):
        """Create a challenge: field in challenge_entries, task into every weekly plan.
        Returns (id, n_slaves).

        The waveform applies to ALL (doc 17 §14): without a fixed routine every
        slave would run a different curve by his own level — they would then run
        alongside each other instead of against each other."""
        if lb.routines_enabled:
            cid = x('INSERT INTO challenges (ch_week, ch_action, ch_routine, ch_target, ch_set_by) '
                    'VALUES (%s,%s,%s,%s,%s)', (week, code, routine, target, by))
        else:
            cid = x('INSERT INTO challenges (ch_week, ch_action, ch_target, ch_set_by) VALUES (%s,%s,%s,%s)',
                    (week, code, target, by))
        mp = lb.default_max_punish()
        for sid in field:
            x('INSERT IGNORE INTO challenge_entries (ce_challenge, ce_slave) VALUES (%s,%s)', (cid, sid))
            if lb.routines_enabled:
                x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_routine, wt_target, wt_max_punish, wt_kind, wt_status, wt_by, wt_challenge) "
                  "VALUES (%s,%s,%s,%s,%s,%s,'challenge','open',%s,%s)",
                  (sid, week, code, routine, target, mp, by, cid))
            else:
                x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_by, wt_challenge) "
                  "VALUES (%s,%s,%s,%s,%s,'challenge','open',%s,%s)", (sid, week, code, target, mp, by, cid))
        ctx.db().commit()
        audit.web('challenge_create', by, data={'id': cid, 'week': week, 'action': code, 'target': target,
                                                'routine': routine, 'field': list(field)})
        ctx.mq.notify_reload('logbook')
        return cid, len(field)

    def _challenge_field_form(form_field):
        """Ticked slaves, empty = all."""
        ids = [int(v) for v in form_field if str(v).isdigit()]
        if ids:
            rows = q('SELECT slave_id FROM slaves WHERE slave_id IN (%s)' % ','.join(['%s'] * len(ids)), tuple(ids))
        else:
            rows = q('SELECT slave_id FROM slaves ORDER BY slave_name')
        return [int(r['slave_id']) for r in rows or []]

    @pages.route('/challenges', methods=['GET', 'POST'])
    @login_required
    def challenges_view():
        if request.method == 'POST':
            op = request.form.get('op') or 'add'
            if op == 'add':
                code = request.form.get('action', '')
                week = request.form.get('week') or lbmod.week_str()
                t = tasktypes.get(code)
                field = _challenge_field_form(request.form.getlist('field'))
                ro = int(request.form.get('routine') or 0) or None
                needs_ro = bool(t and t.level_select)
                if ro and not (needs_ro and lb.routines_enabled and routines.is_task(routines.get(q, ro))):
                    ro = None   # not a task on the time axis -> same as "none picked"
                if not t:
                    flash(i18n._('Unbekannte oder nicht trainierbare Aufgabe.'), 'error')
                elif needs_ro and not ro:
                    flash(i18n._('Diese Aufgabe braucht eine feste Wellenform — sonst läuft jeden Sklaven '
                                 'nach ihrer eigenen Stufe eine andere Kurve und sie liefen nebeneinander '
                                 'statt gegeneinander.'), 'error')
                elif len(field) < 2:
                    flash('Eine Herausforderung braucht mindestens zwei Sklaven.', 'error')
                elif q("SELECT ch_id FROM challenges WHERE ch_week=%s AND ch_action=%s AND ch_status='open'",
                       (week, code), one=True) and not request.form.get('confirm_dup'):
                    flash(i18n._('Für diese Woche läuft schon eine offene Herausforderung in dieser Aufgabe — '
                                 'entscheide oder lösche sie erst, sonst zählt derselbe Durchgang für beide.'),
                          'error')
                else:
                    target = int(request.form.get('target') or t.plan_default)
                    if t.target_unit == 's' and request.form.get('unit') == 'min':
                        target *= 60
                    if needs_ro:
                        # the target value is the minimum score and comes from the waveform
                        ro_row = routines.get(q, ro)
                        target = int(request.form.get('target') or ro_row['ro_min_score'])
                    _, n = _challenge_add(code, week, target, field, user(), routine=ro)
                    flash(f'Herausforderung angesetzt — {n} Sklaven haben sie jetzt im Wochenplan.', 'ok')
                return redirect(url_for('lb.challenges_view', week=request.form.get('week') or None))
            cid = int(request.form.get('ch_id') or 0)
            ch = q('SELECT * FROM challenges WHERE ch_id=%s', (cid,), one=True)
            if not ch:
                abort(404)
            if op == 'decide':
                res = lb.decide_challenge(cid, by=user()) if lb.enabled else None
                ctx.db().commit()
                audit.web('challenge_decide', user(), data={'id': cid, 'places': res})
                ctx.mq.notify_reload('logbook')
                flash('Herausforderung entschieden — Platzierungen stehen, die Regeln sind gelaufen.' if res
                      else 'Nicht entschieden: weniger als zwei Sklaven im Feld — als ungültig geschlossen.',
                      'ok' if res else 'warn')
            elif op == 'delete':
                x('DELETE FROM weekly_tasks WHERE wt_challenge=%s', (cid,))
                x('DELETE FROM challenges WHERE ch_id=%s', (cid,))     # entries per ON DELETE CASCADE
                ctx.db().commit()
                audit.web('challenge_delete', user(), data={'id': cid})
                ctx.mq.notify_reload('logbook')
                flash(i18n._('Herausforderung gelöscht.'), 'ok')
            else:
                abort(400)
            return redirect(url_for('lb.challenges_view', week=ch['ch_week']))
        week = request.args.get('week') or lbmod.week_str()
        board = lb.challenge_board(week) if lb.day_enabled else []
        slaves = q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name')
        for s in slaves:
            s['caps'] = sorted(ctx.slave_capabilities(s['slave_id']))
        weeks = [lbmod.next_week(lbmod.week_str())] + _week_list(8)
        return render_template('lb_challenges.html', board=board, slaves=slaves, week=week, weeks=weeks,
                               action_caps={a.code: (a.capability or '') for a in actions.ACTIONS if a.trainable})

    # ------------------------------------------------------------------ #
    # Day plan templates (doc 14 §12.1): the supervisor lays down the structure

    def _dayplans():
        plans = q('SELECT * FROM day_plans ORDER BY dp_default DESC, dp_name') or []
        for p in plans:
            p['blocks'] = q('SELECT b.*, pr.pro_name AS program_name FROM day_blocks b '
                            'LEFT JOIN program pr ON pr.pro_id=b.db_program '
                            'WHERE b.db_plan=%s ORDER BY b.db_pos, b.db_id', (p['dp_id'],)) or []
            p['total_min'] = sum(int(b['db_minutes'] or 0) for b in p['blocks'])
            n = q('SELECT COUNT(*) AS n FROM slave_settings WHERE ss_day_plan=%s', (p['dp_id'],), one=True)
            p['n_slaves'] = int(n['n']) if n else 0
            # How many tasks this plan keeps the central unit away from (doc 58).
            # Visible in the list, because a plan that silently forbids half the
            # catalogue is exactly what one wants to see without opening it.
            b = q("SELECT COUNT(*) AS n FROM dayplan_actions WHERE dpa_plan=%s AND dpa_mode<>'allow'",
                  (p['dp_id'],), one=True)
            p['n_blocked'] = int(b['n']) if b else 0
        return plans

    def _dayplan_or_404(pid):
        row = q('SELECT * FROM day_plans WHERE dp_id=%s', (pid,), one=True)
        if not row:
            abort(404)
        return row

    @pages.route('/dayplans', methods=['GET', 'POST'])
    @login_required
    def dayplans_view():
        if not lb.day_enabled:
            flash(i18n._('Tagesmodell nicht verfügbar — Migration 007 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()[:120]
            if not name:
                flash('Der Tagesplan braucht einen Namen.', 'error')
            elif q('SELECT dp_id FROM day_plans WHERE dp_name=%s', (name,), one=True):
                flash(i18n._('Ein Tagesplan mit diesem Namen gibt es schon.'), 'error')
            else:
                pid = x('INSERT INTO day_plans (dp_name, dp_note) VALUES (%s,%s)',
                        (name, (request.form.get('note') or '').strip()[:255] or None))
                ctx.db().commit()
                audit.web('dayplan_create', user(), data={'id': pid, 'name': name})
                ctx.mq.notify_reload('logbook')
                flash(i18n._('Tagesplan angelegt — jetzt Blöcke hinzufügen.'), 'ok')
            return redirect(url_for('lb.dayplans_view'))
        return render_template('lb_dayplans.html', plans=_dayplans(), KINDS=i18n.d(BLOCK_KINDS),
                               programs=q('SELECT pro_id, pro_name FROM program ORDER BY pro_name'))

    @pages.route('/dayplans/<int:pid>', methods=['POST'])
    @login_required
    def dayplan_edit(pid):
        p = _dayplan_or_404(pid)
        op = request.form.get('op')
        if op == 'save':
            name = (request.form.get('name') or '').strip()[:120] or p['dp_name']
            other = q('SELECT dp_id FROM day_plans WHERE dp_name=%s AND dp_id<>%s', (name, pid), one=True)
            if other:
                flash(i18n._('Ein anderer Tagesplan hat diesen Namen schon.'), 'error')
                return redirect(url_for('lb.dayplans_view'))
            default = 1 if request.form.get('default') else 0
            if default:
                x('UPDATE day_plans SET dp_default=0 WHERE dp_id<>%s', (pid,))
            x('UPDATE day_plans SET dp_name=%s, dp_note=%s, dp_default=%s WHERE dp_id=%s',
              (name, (request.form.get('note') or '').strip()[:255] or None, default, pid))
            audit.web('dayplan_update', user(), data={'id': pid, 'name': name, 'default': default})
            flash('Tagesplan gespeichert.', 'ok')
        elif op == 'copy':
            # "Duplicate and adjust" (doc 58 §9). "Night shift" comes out of
            # "Museum day" with two changes instead of being built anew.
            #
            # THE TASK DECISIONS TRAVEL ALONG. A copy without them would
            # silently allow more than the original - exactly the kind of
            # surprise this whole concept is written against.
            name = (p['dp_name'] + ' ' + i18n._('(Kopie)'))[:120]
            n = 2
            while q('SELECT dp_id FROM day_plans WHERE dp_name=%s', (name,), one=True):
                name = (p['dp_name'] + ' ' + i18n._('(Kopie)') + ' %d' % n)[:120]
                n += 1
            # never the default: a copy that took the assignment of every slave
            # without an own plan would be live from the moment it was made.
            new = x('INSERT INTO day_plans (dp_name, dp_note, dp_default) VALUES (%s,%s,0)',
                    (name, p['dp_note']))
            x('INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_program, db_action, db_text) '
              'SELECT %s, db_pos, db_kind, db_minutes, db_program, db_action, db_text '
              'FROM day_blocks WHERE db_plan=%s ORDER BY db_pos, db_id', (new, pid))
            x('INSERT INTO dayplan_actions (dpa_plan, dpa_action, dpa_mode, dpa_from, dpa_to, dpa_by) '
              'SELECT %s, dpa_action, dpa_mode, dpa_from, dpa_to, %s FROM dayplan_actions WHERE dpa_plan=%s',
              (new, user(), pid))
            audit.web('dayplan_copy', user(), data={'from': pid, 'id': new, 'name': name})
            flash(i18n._('„{name}“ angelegt — Blöcke und Aufgabenentscheidungen sind mitgekommen.',
                         name=name), 'ok')
        elif op == 'delete':
            x('DELETE FROM day_plans WHERE dp_id=%s', (pid,))          # blocks via CASCADE, assignment to NULL
            audit.web('dayplan_delete', user(), data={'id': pid, 'name': p['dp_name']})
            flash(i18n._('Tagesplan gelöscht — betroffene Sklaven fallen auf die Vorgabe zurück.'), 'ok')
        else:
            abort(400)
        ctx.db().commit()
        ctx.mq.notify_reload('logbook')
        return redirect(url_for('lb.dayplans_view'))

    @pages.route('/dayplans/<int:pid>/blocks', methods=['POST'])
    @login_required
    def dayplan_block(pid):
        _dayplan_or_404(pid)
        op = request.form.get('op')
        if op == 'add':
            kind = request.form.get('kind', '')
            if kind not in BLOCK_KINDS:
                abort(400)
            minutes = max(1, min(240, int(request.form.get('minutes') or 30)))
            prog = int(request.form.get('program') or 0) or None
            code = (request.form.get('action') or '').strip() or None
            text = (request.form.get('text') or '').strip()[:255] or None
            if kind == 'program' and not prog:
                flash('Ein Programm-Block braucht ein Programm.', 'error')
                return redirect(url_for('lb.dayplans_view'))
            if kind == 'plan' and code and not tasktypes.get(code):
                flash('Unbekannte Aufgabe.', 'error')
                return redirect(url_for('lb.dayplans_view'))
            if kind == 'mystery':
                # the pool is the safety boundary (doc 44 §6): checked up front,
                # entry by entry, so a typo cannot become a silent empty pool.
                # SINCE 2.4 it may also stay empty here (doc 58 §6): the block is
                # then created and the pool is picked on its own screen instead
                # of being typed. An empty pool is not hidden - the plan list
                # marks it, because a mystery block without a pool does nothing.
                pool_text = (request.form.get('pool') or '').strip()[:255]
                if pool_text:
                    bad = mystery.pool_error(pool_text)
                    if bad is not None:
                        flash(i18n._('Mystery-Pool: „{entry}“ ist kein Aufgabencode und kein punish:N / reward:N.',
                                     entry=bad), 'error')
                        return redirect(url_for('lb.dayplans_view'))
                text = pool_text
            if kind != 'program':
                prog = None
            if kind != 'plan':
                code = None
            if kind not in ('pause', 'mystery'):
                text = None
            nxt = q('SELECT COALESCE(MAX(db_pos), 0) + 1 AS p FROM day_blocks WHERE db_plan=%s', (pid,), one=True)
            bid = x('INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_program, db_action, db_text) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s)', (pid, int(nxt['p']), kind, minutes, prog, code, text))
            audit.web('dayblock_add', user(), data={'plan': pid, 'kind': kind, 'minutes': minutes})
            flash(f'Block hinzugefügt: {BLOCK_KINDS[kind][0]}, {minutes} min.', 'ok')
            if kind == 'mystery' and not text:
                ctx.db().commit()
                ctx.mq.notify_reload('logbook')
                return redirect(url_for('lb.dayblock_pool', pid=pid, bid=bid))
        elif op in ('up', 'down', 'delete'):
            bid = int(request.form.get('db_id') or 0)
            b = q('SELECT * FROM day_blocks WHERE db_id=%s AND db_plan=%s', (bid, pid), one=True)
            if not b:
                abort(404)
            if op == 'delete':
                x('DELETE FROM day_blocks WHERE db_id=%s', (bid,))
            else:
                # Swap with the neighbour; db_pos can have gaps, hence via the ordering
                order = q('SELECT db_id, db_pos FROM day_blocks WHERE db_plan=%s ORDER BY db_pos, db_id', (pid,)) or []
                idx = [r['db_id'] for r in order].index(bid)
                j = idx - 1 if op == 'up' else idx + 1
                if 0 <= j < len(order):
                    for pos, r in enumerate(order, start=1):
                        x('UPDATE day_blocks SET db_pos=%s WHERE db_id=%s', (pos, r['db_id']))
                    x('UPDATE day_blocks SET db_pos=%s WHERE db_id=%s', (j + 1, bid))
                    x('UPDATE day_blocks SET db_pos=%s WHERE db_id=%s', (idx + 1, order[j]['db_id']))
            audit.web('dayblock_' + op, user(), data={'plan': pid, 'block': bid})
            flash('Block gelöscht.' if op == 'delete' else 'Reihenfolge geändert.', 'ok')
        else:
            abort(400)
        ctx.db().commit()
        ctx.mq.notify_reload('logbook')
        return redirect(url_for('lb.dayplans_view'))

    # ------------------------------------------------------------------ #
    # Task decisions of a day plan (doc 58 §1-3, §5)
    #
    # The first screen in the new style: the WHOLE catalogue with a box each,
    # settings only for what is ticked, folded away behind a line that says
    # what is set. Saving therefore states something about every action - which
    # is what turns the storage from a block list into a decision record, and
    # what lets an action that enters the catalogue later be shown as new
    # instead of slipping in unnoticed.
    #
    # Everything here can only make the day SMALLER. That is what makes it a
    # screen one can hand to a supervisor who is not the author.
    @pages.route('/dayplans/<int:pid>/actions', methods=['GET', 'POST'])
    @login_required
    def dayplan_actions(pid):
        p = _dayplan_or_404(pid)
        codes = [a for a in actions.ACTIONS if a.trainable]
        ro_rows = [r for r in (routines.all_routines(q) if lb.routines_enabled else []) if routines.is_task(r)]
        if request.method == 'POST':
            rows, bad = [], None
            for a in codes:
                # The narrowing limits (doc 60) are independent of the tick: a
                # task can be allowed AND capped.
                caps = {}
                for p in taskblocks.lowerable(a):
                    v = (request.form.get('cap_%s_%s' % (a.code, p.name)) or '').strip()
                    if not v.lstrip('-').isdigit():
                        continue
                    # A limit at or above what is possible anyway is none, and it
                    # is not stored - otherwise the line claims a narrowing that
                    # narrows nothing (doc 60 §4).
                    if p.max is not None and int(v) >= int(p.max):
                        continue
                    caps[p.name] = max(int(p.min or 0), int(v))
                no_ro = {int(r) for r in request.form.getlist('noro_' + a.code) if str(r).isdigit()} \
                    if taskblocks.lowerable(a) is not None else set()
                no_ro &= {int(r['ro_id']) for r in ro_rows}
                if not request.form.get('blocked_' + a.code):
                    rows.append((a.code, taskblocks.MODE_ALLOW, None, None, caps, no_ro))
                    continue
                mode = request.form.get('mode_' + a.code) or taskblocks.MODE_BLOCK
                if mode not in (taskblocks.MODE_BLOCK,) + taskblocks.WINDOW_MODES:
                    abort(400)
                frm = to = None
                if mode in taskblocks.WINDOW_MODES:
                    frm = taskblocks.parse_hhmm(request.form.get('from_' + a.code))
                    to = taskblocks.parse_hhmm(request.form.get('to_' + a.code))
                    # A window mode without a window would be read as a full
                    # block by the day model. Refusing it up front is the
                    # honest version: nobody meant "always" when they picked
                    # "only between".
                    if frm is None or to is None or frm == to:
                        bad = a.name
                        break
                rows.append((a.code, mode, frm, to, caps, no_ro))
            if bad:
                flash(i18n._('„{task}“: das Zeitfenster fehlt oder ist leer — von und bis müssen '
                             'verschiedene Uhrzeiten sein.', task=bad), 'error')
                return redirect(url_for('lb.dayplan_actions', pid=pid))
            x('DELETE FROM dayplan_actions WHERE dpa_plan=%s', (pid,))
            for code, mode, frm, to, caps, no_ro in rows:
                x('INSERT INTO dayplan_actions (dpa_plan, dpa_action, dpa_mode, dpa_from, dpa_to, '
                  'dpa_caps, dpa_no_routines, dpa_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                  (pid, code, mode, frm, to, taskblocks.format_caps(caps),
                   taskblocks.format_ids(no_ro), user()))
            ctx.db().commit()
            blocked = [c for c, m, _f, _t, _c, _n in rows if m != taskblocks.MODE_ALLOW]
            narrowed = [c for c, _m, _f, _t, c2, n in rows if c2 or n]
            audit.web('dayplan_actions', user(), data={'plan': pid, 'blocked': blocked, 'narrowed': narrowed})
            ctx.mq.notify_reload('logbook')
            flash(i18n._('Entscheidungen gespeichert — {n} von {all} Aufgaben gesperrt.',
                         n=len(blocked), all=len(rows)), 'ok')
            return redirect(url_for('lb.dayplan_actions', pid=pid))
        tb = taskblocks.TaskBlocks.load(lb, pid)
        # "New, not decided yet" only once the plan has said something at all -
        # on an untouched plan every task would carry the mark and it would say
        # nothing (doc 58 §1).
        fresh = set(tb.undecided([a.code for a in codes])) if tb.rows else set()
        rows = []
        for a in codes:
            r = tb.get(a.code) or {}
            caps = tb.caps_of(a.code)
            rows.append({'code': a.code, 'name': a.name, 'desc': a.description,
                         'capability': a.capability or '',
                         'mode': r.get('mode', taskblocks.MODE_ALLOW),
                         'from': r.get('from'), 'to': r.get('to'),
                         'from_hhmm': taskblocks.hhmm(r.get('from')) or '22:00',
                         'to_hhmm': taskblocks.hhmm(r.get('to')) or '06:00',
                         'summary': tb.summary_of(a.code),
                         'fresh': a.code in fresh,
                         # doc 60: the parameters where smaller undoubtedly means
                         # less, and the waveforms ruled out here
                         'caps': [{'name': p.name, 'label': p.label or p.name, 'unit': p.unit or '',
                                   'min': p.min, 'max': p.max, 'value': caps.get(p.name, '')}
                                  for p in taskblocks.lowerable(a)],
                         'routine_param': any(p.ref for p in a.params if p.name == 'routine'),
                         'no_routines': tb.no_routines_of(a.code),
                         'narrowed': bool(caps or tb.no_routines_of(a.code))})
        return render_template('lb_dayplan_actions.html', plan=p, rows=rows, routines=ro_rows,
                               MODES=i18n.d(taskblocks.LABELS),
                               BLOCK_MODES=(taskblocks.MODE_BLOCK,) + taskblocks.WINDOW_MODES,
                               WINDOW_MODES=taskblocks.WINDOW_MODES, STEP=taskblocks.STEP_MIN)

    # ------------------------------------------------------------------ #
    # The mystery pool of one block (doc 58 §6) — the same screen as the task
    # decisions, with the sign reversed: ticked means IN the pool.
    #
    # Until 2.4 this was a free-text field with comma separated codes, one of
    # the three places where somebody had to reproduce a string exactly. The
    # pool is the safety boundary of the draw, so a typo there was the most
    # expensive of the three: `parse_pool()` drops what it does not understand,
    # and a pool that silently lost an entry still looks like a pool.
    @pages.route('/dayplans/<int:pid>/blocks/<int:bid>/pool', methods=['GET', 'POST'])
    @login_required
    def dayblock_pool(pid, bid):
        p = _dayplan_or_404(pid)
        b = q("SELECT * FROM day_blocks WHERE db_id=%s AND db_plan=%s AND db_kind='mystery'",
              (bid, pid), one=True)
        if not b:
            abort(404)
        codes = [a for a in actions.ACTIONS if a.trainable and tasktypes.get(a.code)]
        channel = ['%s:%d' % (k, n) for k in (mystery.PUNISH, mystery.REWARD) for n in (1, 2, 3)]
        if request.method == 'POST':
            want = [e for e in request.form.getlist('entry') if e in channel or any(a.code == e for a in codes)]
            text = ', '.join(want)
            if len(text) > 255:
                flash(i18n._('Der Pool ist zu lang — höchstens 255 Zeichen, also rund zwanzig Einträge.'), 'error')
                return redirect(url_for('lb.dayblock_pool', pid=pid, bid=bid))
            # Counter-check through the very code the draw uses: what does not
            # survive parse_pool() is not in the pool, whatever the screen shows.
            if text and len(mystery.parse_pool(text)) != len(want):
                flash(i18n._('Der Pool wurde nicht vollständig erkannt — bitte melden.'), 'error')
                return redirect(url_for('lb.dayblock_pool', pid=pid, bid=bid))
            x('UPDATE day_blocks SET db_text=%s WHERE db_id=%s', (text, bid))
            ctx.db().commit()
            audit.web('dayblock_pool', user(), data={'plan': pid, 'block': bid, 'pool': want})
            ctx.mq.notify_reload('logbook')
            flash(i18n._('Pool gespeichert — {n} Einträge.', n=len(want)) if want
                  else i18n._('Der Pool ist jetzt leer — dieser Block zieht nichts.'), 'ok' if want else 'warn')
            return redirect(url_for('lb.dayplans_view'))
        # What is ticked comes out of the stored pool through the SAME parser the
        # draw uses: an entry the parser drops is not in the pool, so it must not
        # show as ticked either.
        chosen = {e[1] if e[0] == mystery.TASK else '%s:%d' % (e[0], e[2])
                  for e in mystery.parse_pool(b['db_text'])}
        return render_template('lb_dayblock_pool.html', plan=p, block=b, chosen=chosen,
                               rows=[{'code': a.code, 'name': a.name, 'desc': a.description,
                                      'capability': a.capability or ''} for a in codes],
                               channel=channel)

    # ------------------------------------------------------------------ #
    # Waveform editor (doc 17 §8). Two views on the same data model:
    # a box is a line with a wide tolerance band.
    def _routine_or_404(rid):
        row = routines.get(q, rid)
        if not row:
            abort(404)
        return row

    def _routine_view(rid):
        """Head, tracks, notices and the plain-text line of a waveform."""
        row = _routine_or_404(rid)
        axis = row.get('ro_axis') or routines.AXIS_TIME
        loaded = []
        for t in routines.tracks(q, rid):
            pts = routines.as_tuples(routines.points(q, rid, t['rt_track']))
            loaded.append((t, pts))
        warn = [dict(w, text=i18n._(w['text_de'])) for w in routines.waveform_warnings(row, loaded)]
        used_w = q('SELECT COUNT(*) AS n FROM weekly_tasks WHERE wt_routine=%s', (rid,), one=True)
        used_c = q('SELECT COUNT(*) AS n FROM challenges WHERE ch_routine=%s', (rid,), one=True)
        whole = bytearray()
        for _t, pts in loaded:
            whole += routines.serialise(pts, axis)
        tracks_out = []
        for t, pts in loaded:
            d = dict(t)
            d['points'] = [{'x': x, 'value': v, 'tol': l} for x, v, l in pts]
            d['role_label'] = profiles.role_label(t['rt_role'])[0]
            d['channel_label'] = profiles.channel_label(t['rt_channel'])[0] if t['rt_channel'] else ''
            pr = profiles.get(t['rt_profile'])
            d['profile_label'] = pr.name if pr else ''
            d['crc'] = routines.crc32(routines.serialise(pts, axis))
            tracks_out.append(d)
        return {'r': row, 'axis': axis, 'tracks': tracks_out, 'warnings': warn,
                'summary': routines.summary_line(row, loaded),
                'used': int(used_w['n']) + int(used_c['n']),
                'crc': routines.crc32(bytes(whole)) if whole else 0,
                'seconds': round(max([routines.duration_ms(p) for _t, p in loaded] or [0]) / 1000.0, 1),
                'n_points': sum(len(p) for _t, p in loaded),
                'max_points': routines.MAX_POINTS, 'max_tracks': routines.MAX_TRACKS}

    def _routine_form(row=None):
        """Numbers of the head out of the form, clamped. Returns (values, error)."""
        f = request.form
        def num(name, lo, hi, default):
            try:
                return max(lo, min(hi, int(f.get(name) if f.get(name) not in (None, '') else default)))
            except (TypeError, ValueError):
                return default
        name = (f.get('name') or '').strip()[:120]
        if not name:
            return None, i18n._('Die Wellenform braucht einen Namen.')
        other = q('SELECT ro_id FROM routines WHERE ro_name=%s' + (' AND ro_id<>%s' if row else ''),
                  (name, row['ro_id']) if row else (name,), one=True)
        if other:
            return None, i18n._('Eine Wellenform mit diesem Namen gibt es schon.')
        axis = f.get('axis') if f.get('axis') in routines.AXES else routines.AXIS_TIME
        purpose = f.get('purpose') if f.get('purpose') in routines.PURPOSES else routines.PURPOSE_TASK
        if purpose == routines.PURPOSE_TASK and axis != routines.AXIS_TIME:
            # A task is graded and runs its course - on the depth axis there is
            # nothing to run through and nothing to grade (check 2026-09-11).
            return None, i18n._('Eine Aufgabe läuft ab und wird bewertet — sie braucht die Zeitachse. '
                                'Für eine Kurve über der Tiefe den Zweck „Reiz" oder „Belohnung" wählen.')
        return {'name': name, 'note': (f.get('note') or '').strip()[:255] or None,
                'axis': axis, 'purpose': purpose,
                'level': num('level', 1, int(lb.sc_int('level_max', 10)), 1),
                'tol': num('tol_default', 1, 50, 10),
                'fullscale': num('fullscale_pct', 5, 100, lb.sc_int('routine_fullscale_pct', 25)),
                'loop': num('loop_ms', 0, 30000, 1500),
                'min_score': num('min_score', 0, 10000, lb.sc_int('routine_min_score', 6000)),
                'punish': num('punish_level', 0, 3, 1),
                'reward': num('reward_level', 0, 3, 0)}, None

    @pages.route('/routines', methods=['GET', 'POST'])
    @login_required
    def routines_view():
        if not lb.routines_enabled:
            flash(i18n._('Wellenformen nicht verfügbar - Migration 008 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            vals, err = _routine_form()
            if err:
                flash(err, 'error')
                return redirect(url_for('lb.routines_view'))
            rid = x('INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_level, '
                    ' ro_tol_default, ro_fullscale_pct, ro_loop_ms, ro_min_score, ro_punish_level, '
                    ' ro_reward_level, ro_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (vals['name'], vals['note'], vals['axis'], vals['purpose'], vals['level'],
                     vals['tol'], vals['fullscale'], vals['loop'], vals['min_score'],
                     vals['punish'], vals['reward'], user()))
            # A waveform without a track cannot be drawn: the first one matches the
            # purpose — a task measures, everything else outputs.
            if vals['purpose'] == routines.PURPOSE_TASK:
                x('INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_channel) '
                  "VALUES (%s,0,'zieltiefe','')", (rid,))
            else:
                role = (profiles.ROLE_REWARD if vals['purpose'] == routines.PURPOSE_REWARD
                        else profiles.ROLE_STIM)
                x('INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel) '
                  "VALUES (%s,0,%s,%s,'a')", (rid, role, profiles.default_for(role)))
            ctx.db().commit()
            audit.web('routine_create', user(), data={'id': rid, 'name': vals['name'], 'level': vals['level']})
            ctx.mq.notify_reload('logbook')
            flash(i18n._('Wellenform angelegt — jetzt die Kurve zeichnen.'), 'ok')
            return redirect(url_for('lb.routine_edit', rid=rid))
        rows = routines.all_routines(q)
        for r in rows:
            r['seconds'] = round(int(r['ro_duration_ms'] or 0) / 1000.0, 1)
        for r in rows:
            trs = routines.tracks(q, r['ro_id'])
            loaded = [(t, routines.as_tuples(routines.points(q, r['ro_id'], t['rt_track']))) for t in trs]
            r['summary'] = routines.summary_line(r, loaded)
            r['n_tracks'] = len(trs)
        return render_template('lb_routines.html', rows=rows,
                               level_max=lb.sc_int('level_max', 10), **_routine_catalogues(),
                               defaults={'fullscale': lb.sc_int('routine_fullscale_pct', 25),
                                         'min_score': lb.sc_int('routine_min_score', 6000)})

    @pages.route('/routines/<int:rid>')
    @login_required
    def routine_edit(rid):
        if not lb.routines_enabled:
            abort(404)
        return render_template('lb_routine.html', level_max=lb.sc_int('level_max', 10),
                               **_routine_catalogues(), **_routine_view(rid))

    def _routine_catalogues():
        """Everything the editor needs in order to explain — translated, in display order."""
        return {
            'AXES': {k: (i18n._(v[0]), i18n._(v[1]), i18n._(v[2])) for k, v in routines.AXES.items()},
            'PURPOSES': {k: (i18n._(v[0]), i18n._(v[1])) for k, v in routines.PURPOSES.items()},
            'ROLES': {k: profiles.role_label(k) for k in profiles.ROLES},
            'CHANNELS': {k: profiles.channel_label(k) for k in profiles.CHANNELS},
            'MODES': {k: profiles.mode_label(k) for k in profiles.MODE_LABELS},
            'COUPLES': {k: profiles.couple_label(k) for k in profiles.COUPLE_LABELS},
            'PROFILES': [{'key': pr.key, 'role': pr.role, 'name': pr.name,
                          'desc': pr.description, 'hz': '%g–%g Hz' % (pr.hz_low, pr.hz_high),
                          'loop_ms': pr.loop_ms, 'shape': list(pr.shape)} for pr in profiles.PROFILES],
        }

    @pages.route('/routines/<int:rid>/head', methods=['POST'])
    @login_required
    def routine_head(rid):
        row = _routine_or_404(rid)
        op = request.form.get('op')
        if op == 'save':
            vals, err = _routine_form(row)
            if err:
                flash(err, 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            if vals['axis'] == routines.AXIS_DEPTH and \
                    any(t['rt_role'] == profiles.ROLE_TARGET for t in routines.tracks(q, rid)):
                # On the depth axis there is no target depth (X IS the depth).
                flash(i18n._('Auf der Tiefenachse gibt es keine Zieltiefen-Spur — erst die Rolle '
                             'der Spur ändern, dann die Achse wechseln.'), 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            x('UPDATE routines SET ro_name=%s, ro_note=%s, ro_axis=%s, ro_purpose=%s, ro_level=%s, '
              ' ro_tol_default=%s, ro_fullscale_pct=%s, ro_loop_ms=%s, ro_min_score=%s, '
              ' ro_punish_level=%s, ro_reward_level=%s, ro_by=%s WHERE ro_id=%s',
              (vals['name'], vals['note'], vals['axis'], vals['purpose'], vals['level'], vals['tol'],
               vals['fullscale'], vals['loop'], vals['min_score'], vals['punish'], vals['reward'],
               user(), rid))
            routines.recompute(q, x, rid)      # a change of axis changes the byte stream
            audit.web('routine_update', user(), data={'id': rid, 'name': vals['name'], 'level': vals['level']})
            flash(i18n._('Wellenform gespeichert.'), 'ok')
        elif op == 'copy':
            name = (row['ro_name'] + ' ' + i18n._('(Kopie)'))[:120]
            if q('SELECT ro_id FROM routines WHERE ro_name=%s', (name,), one=True):
                flash(i18n._('Eine Wellenform mit diesem Namen gibt es schon.'), 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            new = x('INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_level, ro_tol_default, '
                    ' ro_fullscale_pct, ro_loop_ms, ro_min_score, ro_punish_level, ro_reward_level, ro_by) '
                    'SELECT %s, ro_note, ro_axis, ro_purpose, ro_level, ro_tol_default, ro_fullscale_pct, '
                    ' ro_loop_ms, ro_min_score, ro_punish_level, ro_reward_level, %s '
                    'FROM routines WHERE ro_id=%s', (name, user(), rid))
            x('INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, '
              ' rt_mode, rt_couple, rt_note) '
              'SELECT %s, rt_track, rt_role, rt_profile, rt_channel, rt_mode, rt_couple, rt_note '
              'FROM routine_tracks WHERE rt_routine=%s', (new, rid))
            x('INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) '
              'SELECT %s, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct FROM routine_points WHERE rp_routine=%s',
              (new, rid))
            routines.recompute(q, x, new)
            ctx.db().commit()
            audit.web('routine_copy', user(), data={'from': rid, 'id': new})
            flash(i18n._('Wellenform kopiert.'), 'ok')
            return redirect(url_for('lb.routine_edit', rid=new))
        elif op == 'delete':
            # Assignments fall back via ON DELETE SET NULL to "the central unit picks
            # by level"; an open challenge, however, needs a fixed waveform.
            open_ch = q("SELECT COUNT(*) AS n FROM challenges WHERE ch_routine=%s AND ch_status='open'",
                        (rid,), one=True)
            if int(open_ch['n']):
                flash(i18n._('Eine offene Herausforderung nutzt diese Wellenform.'), 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            x('DELETE FROM routines WHERE ro_id=%s', (rid,))
            ctx.db().commit()
            audit.web('routine_delete', user(), data={'id': rid, 'name': row['ro_name']})
            ctx.mq.notify_reload('logbook')
            flash(i18n._('Wellenform gelöscht.'), 'ok')
            return redirect(url_for('lb.routines_view'))
        else:
            abort(400)
        ctx.db().commit()
        ctx.mq.notify_reload('logbook')
        return redirect(url_for('lb.routine_edit', rid=rid))

    def _routine_renumber(rid, track_no):
        """Order the support points of a track along the axis, renumber them and
        bring the derived values (checksum, count, duration) up to date."""
        rows = q('SELECT rp_seq FROM routine_points WHERE rp_routine=%s AND rp_track=%s '
                 'ORDER BY rp_x, rp_seq', (rid, track_no)) or []
        # Push them far back first, so that the primary key becomes free
        for i, r in enumerate(rows):
            x('UPDATE routine_points SET rp_seq=%s WHERE rp_routine=%s AND rp_track=%s AND rp_seq=%s',
              (5000 + i, rid, track_no, r['rp_seq']))
        for i in range(len(rows)):
            x('UPDATE routine_points SET rp_seq=%s WHERE rp_routine=%s AND rp_track=%s AND rp_seq=%s',
              (i, rid, track_no, 5000 + i))
        return routines.recompute(q, x, rid)

    @pages.route('/routines/<int:rid>/tracks', methods=['POST'])
    @login_required
    def routine_tracks(rid):
        """Create, change, delete tracks (doc 19 §2.3)."""
        head = _routine_or_404(rid)
        op = request.form.get('op')
        f = request.form

        def clean(role, channel, mode, couple, profile):
            role = role if role in profiles.ROLES else profiles.ROLE_TARGET
            if role == profiles.ROLE_TARGET and (head.get('ro_axis') or routines.AXIS_TIME) != routines.AXIS_TIME:
                # On the depth axis there is nothing to trace: X IS the measured
                # depth. A target-depth track there would be pointless and would on
                # top of that get warning texts in seconds (check 2026-09-11).
                role = profiles.ROLE_STIM
            if role == profiles.ROLE_TARGET:
                # The graded track is not an output: no channel, no profile,
                # no coupling — otherwise nonsense stands in the database.
                return role, '', profiles.MODE_ABSOLUTE, None, None
            if profile not in profiles.BY_KEY or profiles.BY_KEY[profile].role != role:
                profile = profiles.default_for(role)       # roles are fixed (doc 19 §3)
            channel = channel if channel in profiles.CHANNELS else 'a'
            mode = mode if mode in profiles.MODE_LABELS else profiles.MODE_ABSOLUTE
            couple = couple if couple in profiles.COUPLE_LABELS else profiles.COUPLE_POSITION
            return role, channel, mode, (couple if mode == profiles.MODE_COUPLED else None), profile

        if op == 'add':
            n = len(routines.tracks(q, rid))
            if n >= routines.MAX_TRACKS:
                flash(i18n._('Mehr als {n} Spuren gehen nicht.', n=routines.MAX_TRACKS), 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            role, channel, mode, couple, profile = clean(
                f.get('role'), f.get('channel'), f.get('mode'), f.get('couple'), f.get('profile'))
            nxt = int((q('SELECT COALESCE(MAX(rt_track)+1,0) AS t FROM routine_tracks WHERE rt_routine=%s',
                         (rid,), one=True) or {'t': 0})['t'])
            x('INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, '
              ' rt_mode, rt_couple, rt_note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
              (rid, nxt, role, profile, channel, mode, couple,
               (f.get('note') or '').strip()[:255] or None))
            audit.web('routine_track_add', user(), data={'id': rid, 'track': nxt, 'role': role})
            flash(i18n._('Spur {n} angelegt.', n=nxt), 'ok')
        elif op == 'save':
            no = int(f.get('track') or -1)
            t = routines.track(q, rid, no)
            if not t:
                abort(404)
            role, channel, mode, couple, profile = clean(
                f.get('role'), f.get('channel'), f.get('mode'), f.get('couple'), f.get('profile'))
            x('UPDATE routine_tracks SET rt_role=%s, rt_profile=%s, rt_channel=%s, rt_mode=%s, '
              ' rt_couple=%s, rt_note=%s WHERE rt_routine=%s AND rt_track=%s',
              (role, profile, channel, mode, couple, (f.get('note') or '').strip()[:255] or None,
               rid, no))
            audit.web('routine_track_save', user(), data={'id': rid, 'track': no, 'role': role})
            flash(i18n._('Spur {n} gespeichert.', n=no), 'ok')
        elif op == 'delete':
            no = int(f.get('track') or -1)
            if not routines.track(q, rid, no):
                abort(404)
            if len(routines.tracks(q, rid)) < 2:
                flash(i18n._('Die letzte Spur lässt sich nicht löschen — sonst gäbe es nichts zu zeichnen.'),
                      'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            x('DELETE FROM routine_points WHERE rp_routine=%s AND rp_track=%s', (rid, no))
            x('DELETE FROM routine_tracks WHERE rt_routine=%s AND rt_track=%s', (rid, no))
            routines.recompute(q, x, rid)
            audit.web('routine_track_delete', user(), data={'id': rid, 'track': no})
            flash(i18n._('Spur {n} gelöscht.', n=no), 'ok')
        else:
            abort(400)
        ctx.db().commit()
        ctx.mq.notify_reload('logbook')
        return redirect(url_for('lb.routine_edit', rid=rid) + '#spur')

    @pages.route('/routines/<int:rid>/points', methods=['POST'])
    @login_required
    def routine_points(rid):
        """The curve of a track. The editor sends it as a whole (op=replace), so that
        dragging on the drawing surface does not make one round trip to the server per point;
        the form-based operation (op=box/ramp/clear) stays alongside it."""
        row = _routine_or_404(rid)
        axis = row.get('ro_axis') or routines.AXIS_TIME
        op = request.form.get('op')
        f = request.form
        track_no = int(f.get('track') or 0)
        if not routines.track(q, rid, track_no):
            abort(404)
        # On the time axis X counts in milliseconds, on the depth axis in
        # 0.1 percent. Both are whole numbers and are clamped here once.
        x_max = 36000 * 1000 if axis == routines.AXIS_TIME else 1000
        n = int((q('SELECT COUNT(*) AS n FROM routine_points WHERE rp_routine=%s AND rp_track=%s',
                   (rid, track_no), one=True) or {'n': 0})['n'])
        last = q('SELECT MAX(rp_x) AS x FROM routine_points WHERE rp_routine=%s AND rp_track=%s',
                 (rid, track_no), one=True)
        end_x = int((last or {}).get('x') or 0)

        def val(name, lo, hi, default):
            try:
                return max(lo, min(hi, int(round(float(f.get(name) if f.get(name) not in (None, '') else default)))))
            except (TypeError, ValueError):
                return default

        def add(xv, value, tol):
            seq = int((q('SELECT COALESCE(MAX(rp_seq)+1, 0) AS s FROM routine_points '
                         'WHERE rp_routine=%s AND rp_track=%s', (rid, track_no), one=True) or {'s': 0})['s'])
            x('INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) '
              'VALUES (%s,%s,%s,%s,%s,%s)',
              (rid, track_no, seq, max(0, min(x_max, int(xv))), int(value), int(tol)))

        if op == 'replace':
            # whole curve out of the drawing surface: [[x, value, tol], ...]
            try:
                raw = json.loads(f.get('points') or '[]')
                pts = [(int(a), int(b), int(c)) for a, b, c in raw]
            except (ValueError, TypeError):
                abort(400)
            if len(pts) > routines.MAX_POINTS:
                flash(i18n._('Mehr als {n} Stützpunkte nimmt das Gerät nicht an.', n=routines.MAX_POINTS), 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            pts.sort(key=lambda t: t[0])
            x('DELETE FROM routine_points WHERE rp_routine=%s AND rp_track=%s', (rid, track_no))
            for seq, (xv, v, tol) in enumerate(pts):
                x('INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) '
                  'VALUES (%s,%s,%s,%s,%s,%s)',
                  (rid, track_no, seq, max(0, min(x_max, xv)), max(0, min(100, v)), max(0, min(50, tol))))
            audit.web('routine_curve', user(), data={'id': rid, 'track': track_no, 'points': len(pts)})
        elif op in ('box', 'ramp'):
            value = val('depth', 0, 100, 50)
            tol = val('tol', 0, 50, int(row['ro_tol_default'] or 10))
            unit = 1000 if axis == routines.AXIS_TIME else 10     # one second or one percent
            ramp = val('ramp_s', 0, 3600, 1) * unit
            hold = val('hold_s', 0, 3600, 3) * unit if op == 'box' else 0
            need = (2 if op == 'box' else 1) + (1 if n == 0 else 0)
            if n + need > routines.MAX_POINTS:
                flash(i18n._('Mehr als {n} Stützpunkte nimmt das Gerät nicht an.', n=routines.MAX_POINTS), 'error')
                return redirect(url_for('lb.routine_edit', rid=rid))
            if n == 0:
                add(0, 0, tol)                       # defined start at rest
                end_x = 0
            add(end_x + max(ramp, 10), value, tol)
            if op == 'box':
                add(end_x + max(ramp, 10) + hold, value, tol)
            audit.web('routine_point_add', user(), data={'id': rid, 'track': track_no, 'op': op})
        elif op == 'clear':
            x('DELETE FROM routine_points WHERE rp_routine=%s AND rp_track=%s', (rid, track_no))
            audit.web('routine_clear', user(), data={'id': rid, 'track': track_no})
        else:
            abort(400)
        d = _routine_renumber(rid, track_no)
        ctx.db().commit()
        ctx.mq.notify_reload('logbook')
        flash(i18n._('Kurve geändert: {n} Stützpunkte, {s} s.', n=d['points'],
                     s=round(d['duration_ms'] / 1000.0, 1)), 'ok')
        return redirect(url_for('lb.routine_edit', rid=rid))

    @api.route('/routines')
    @login_required
    def api_routines():
        rows = routines.all_routines(q)
        return jsonify({'routines': [{'id': r['ro_id'], 'name': r['ro_name'], 'level': r['ro_level'],
                                      'axis': r['ro_axis'], 'purpose': r['ro_purpose'],
                                      'example': bool(r['ro_example']),
                                      'points': r['ro_points'], 'duration_ms': r['ro_duration_ms'],
                                      'min_score': r['ro_min_score'], 'crc32': r['ro_crc32'],
                                      'note': r['ro_note']} for r in rows]})

    @api.route('/routines/<int:rid>')
    @login_required
    def api_routine(rid):
        d = _routine_view(rid)
        r = d['r']
        return jsonify({'id': r['ro_id'], 'name': r['ro_name'], 'note': r['ro_note'],
                        'axis': d['axis'], 'purpose': r['ro_purpose'], 'example': bool(r['ro_example']),
                        'level': r['ro_level'], 'summary': d['summary'],
                        'tol_default': r['ro_tol_default'], 'fullscale_pct': r['ro_fullscale_pct'],
                        'loop_ms': r['ro_loop_ms'], 'min_score': r['ro_min_score'],
                        'punish_level': r['ro_punish_level'], 'reward_level': r['ro_reward_level'],
                        'crc32': d['crc'], 'seconds': d['seconds'], 'points': d['n_points'],
                        'tracks': [{'track': t['rt_track'], 'role': t['rt_role'],
                                    'profile': t['rt_profile'], 'channel': t['rt_channel'],
                                    'mode': t['rt_mode'], 'couple': t['rt_couple'],
                                    'note': t['rt_note'], 'crc32': t['crc'],
                                    'points': t['points']} for t in d['tracks']],
                        'warnings': [{'code': w['code'], 'at_ms': w['at_ms'], 'track': w.get('track', 0),
                                      'text': w['text']} for w in d['warnings']]})

    # ------------------------------------------------------------------ #
    # Reward/punishment editor (doc 14 §12.5)
    @pages.route('/rules', methods=['GET', 'POST'])
    @login_required
    def rules_view():
        if not lb.day_enabled:
            flash(i18n._('Regelwerk nicht verfügbar — Migration 007 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            op = request.form.get('op')
            if op == 'add':
                trig = request.form.get('trigger', '')
                # two selects, one stored condition: 'place=1&time>=22:00' (doc 44 §4)
                cond = lbmod.Logbook.join_cond(request.form.get('cond', ''), request.form.get('cond_time', ''))
                eff = request.form.get('effect', '')
                # The pieces beat the free-text field; without them nothing
                # changes (doc 58 §5).
                built = _rule_param_from_form(eff, request.form)
                param = (built if built is not None else (request.form.get('param') or '')).strip()[:64]
                if trig not in lbmod.Logbook.TRIGGERS or eff not in lbmod.Logbook.EFFECTS or not lb.valid_cond(cond):
                    abort(400)
                # THE ONE THAT WAS MISSING (doc 58 §8): the condition has to
                # belong to this trigger. Until 2.4 only membership in the table
                # was checked, so a rule could be saved that `_cond_ok()` then
                # refused for ever - silently, without a log line. The list
                # filters by trigger too, so this is the second lock, not the
                # only one; a hand-built POST must not get past it either.
                if not lbmod.Logbook.cond_fits(trig, cond):
                    flash(i18n._('Diese Bedingung gehört nicht zu diesem Anlass — die Regel könnte nie '
                                 'zutreffen. Die Liste zeigt nur die passenden Bedingungen.'), 'error')
                    return redirect(url_for('lb.rules_view'))
                bad = _rule_param_error(eff, param)
                if bad:
                    flash(bad, 'error')
                    return redirect(url_for('lb.rules_view'))
                x('INSERT INTO rules (ru_trigger, ru_cond, ru_effect, ru_param, ru_note, ru_pos, ru_by) '
                  'VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE ru_enabled=1, ru_note=VALUES(ru_note), '
                  'ru_pos=VALUES(ru_pos), ru_by=VALUES(ru_by)',
                  (trig, cond, eff, param, (request.form.get('note') or '').strip()[:255] or None,
                   max(0, min(999, int(request.form.get('pos') or 50))), user()))
                audit.web('rule_add', user(), data={'trigger': trig, 'cond': cond, 'effect': eff, 'param': param})
                flash('Regel angelegt.', 'ok')
            elif op in ('toggle', 'delete'):
                rid = int(request.form.get('ru_id') or 0)
                if not q('SELECT ru_id FROM rules WHERE ru_id=%s', (rid,), one=True):
                    abort(404)
                if op == 'toggle':
                    x('UPDATE rules SET ru_enabled=1-ru_enabled, ru_by=%s WHERE ru_id=%s', (user(), rid))
                else:
                    x('DELETE FROM rules WHERE ru_id=%s', (rid,))
                audit.web('rule_' + op, user(), data={'id': rid})
                flash('Regel geändert.' if op == 'toggle' else 'Regel gelöscht.', 'ok')
            else:
                abort(400)
            ctx.db().commit()
            ctx.mq.notify_reload('logbook')
            return redirect(url_for('lb.rules_view'))
        # SANCTIONS reaches the template through the context processor
        # (_inject_lb) — the effects sanction_impose/sanction_lift need their
        # keys just as visible there as the privileges need theirs.
        rules = lb.rules()
        conds = lb.conditions()
        for r in rules:
            r['cond_text'] = lb.cond_text(r['ru_cond'])
            # Rules that were built before 2.4 and can never match: marked, not
            # deleted. Which of them is meant is the supervisor's decision.
            r['dead'] = not lbmod.Logbook.cond_fits(r['ru_trigger'], r['ru_cond'])
        # Which condition belongs to which trigger, for the select: the page
        # shows only the fitting ones instead of the full cross product.
        fit = {t: [c for c in conds if lbmod.Logbook.cond_fits(t, c)] for t in lbmod.Logbook.TRIGGERS}
        # "Duplicate and adjust" (doc 58 §9): the form comes pre-filled from an
        # existing rule. NOT a copied row - `uq_rule` forbids two rules that say
        # exactly the same thing, and that is right: the table must not hold the
        # same sentence twice. So one starts from a working example and changes
        # what is meant to differ, which is also the better way to learn the
        # model than an empty form.
        pre = {}
        src = q('SELECT * FROM rules WHERE ru_id=%s', (request.args.get('from'),), one=True) \
            if request.args.get('from') else None
        if src:
            base, when = lbmod.Logbook.split_cond(src['ru_cond'])
            pre = {'trigger': src['ru_trigger'], 'cond': base, 'cond_time': when,
                   'effect': src['ru_effect'], 'param': src['ru_param'], 'pos': src['ru_pos'],
                   'note': src['ru_note'] or ''}
            pre.update(_rule_param_parts(src['ru_effect'], src['ru_param']))
        return render_template('lb_rules.html', rules=rules, pre=pre,
                               TRIGGERS=i18n.d(lbmod.Logbook.TRIGGERS),
                               CONDITIONS=i18n.d(conds),
                               TIME_CONDITIONS=i18n.d(lbmod.Logbook.TIME_CONDITIONS),
                               EFFECTS=i18n.d(lbmod.Logbook.EFFECTS),
                               TRIGGER_HELP=i18n.d(lbmod.Logbook.TRIGGER_HELP),
                               COND_HELP=i18n.d(lb.cond_help()), COND_FIT=fit)

    # ------------------------------------------------------------------ #
    # Budgets and cooldowns (doc 44 §1): one table, one page. The [safety]
    # ceiling of the punishment channel is shown as a row but cannot be edited
    # here — that stays in config.ini (decision Philine 2026-09-10).
    def _budget_form(form, who):
        """Read and check a budget out of a form/JSON dict. Returns (row, error)."""
        key = str(form.get('key') or '').strip()[:40]
        if key == 'activity' and form.get('action'):
            key = budgetsmod.ACTIVITY_PREFIX + str(form.get('action')).strip()
        codes = [a.code for a in actions.ACTIONS if a.trainable]
        if not budgetsmod.valid_key(key, codes):
            return None, i18n._('Unbekannter Schlüssel.')
        try:
            slave = int(form.get('slave') or 0)
        except (TypeError, ValueError):
            return None, i18n._('Teilnehmerin: Zahl erwartet.')
        if slave and not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (slave,), one=True):
            return None, i18n._('Teilnehmerin unbekannt.')
        period = str(form.get('period') or 'day')
        if period not in budgetsmod.PERIODS:
            return None, 'period: day|week'

        def num(name, lo, hi):
            v = str(form.get(name) or '').strip()
            if v == '':
                return None
            n = int(v)
            if not lo <= n <= hi:
                raise ValueError(i18n._('{name}: {lo}..{hi}', name=name, lo=lo, hi=hi))
            return n
        try:
            max_count = num('max_count', 1, 100000)
            min_gap_s = num('min_gap_s', 1, 7 * 86400)
        except ValueError as e:
            return None, str(e)
        if max_count is None and min_gap_s is None:
            return None, i18n._('Anzahl oder Abstand — eins von beiden muss stehen.')
        on_gap = str(form.get('on_gap') or ('drop' if key == 'reward' else 'queue'))
        if on_gap not in budgetsmod.ON_GAP:
            return None, 'on_gap: queue|drop'
        # The ceiling cannot be loosened — it applies anyway (budgets.py). Say so
        # up front rather than let someone wonder why his 200 never took effect.
        if key == 'punish' and period == 'day':
            cap = int(lb.limits.get('channel_day_max') or 0)
            if cap and max_count and max_count > cap:
                return None, i18n._('Über der Decke aus config.ini [safety] ({cap}) — ein Budget kann nur verschärfen.', cap=cap)
        return {'key': key, 'slave': slave, 'period': period, 'max_count': max_count, 'min_gap_s': min_gap_s,
                'on_gap': on_gap, 'note': str(form.get('note') or '').strip()[:255] or None, 'by': who}, None

    def _budget_save(row):
        x('INSERT INTO budgets (bu_key, bu_slave, bu_period, bu_max_count, bu_min_gap_s, bu_on_gap, bu_note, bu_by) '
          'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE bu_enabled=1, bu_max_count=VALUES(bu_max_count), '
          'bu_min_gap_s=VALUES(bu_min_gap_s), bu_on_gap=VALUES(bu_on_gap), bu_note=VALUES(bu_note), bu_by=VALUES(bu_by)',
          (row['key'], row['slave'], row['period'], row['max_count'], row['min_gap_s'], row['on_gap'], row['note'], row['by']))
        ctx.db().commit()
        lb.budgets.invalidate()
        ctx.mq.notify_reload('logbook')

    def _budget_rows():
        rows = q('SELECT b.*, s.slave_name FROM budgets b LEFT JOIN slaves s ON s.slave_id=b.bu_slave '
                 'ORDER BY b.bu_slave, b.bu_key, b.bu_period') or []
        for r in rows:
            r['label'] = i18n._(budgetsmod.key_label(r['bu_key']))
        return rows

    @pages.route('/budgets', methods=['GET', 'POST'])
    @login_required
    def budgets_view():
        if not lb.budgets.enabled:
            flash(i18n._('Budgets nicht verfügbar — Migration 005 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            op = request.form.get('op')
            if op == 'add':
                row, bad = _budget_form(request.form, user())
                if bad:
                    flash(bad, 'error')
                    return redirect(url_for('lb.budgets_view'))
                _budget_save(row)
                audit.web('budget_set', user(), data=row)
                flash(i18n._('Budget gespeichert.'), 'ok')
            elif op in ('toggle', 'delete'):
                bid = int(request.form.get('bu_id') or 0)
                if not q('SELECT bu_id FROM budgets WHERE bu_id=%s', (bid,), one=True):
                    abort(404)
                if op == 'toggle':
                    x('UPDATE budgets SET bu_enabled=1-bu_enabled, bu_by=%s WHERE bu_id=%s', (user(), bid))
                else:
                    x('DELETE FROM budgets WHERE bu_id=%s', (bid,))
                ctx.db().commit()
                lb.budgets.invalidate()
                ctx.mq.notify_reload('logbook')
                audit.web('budget_' + op, user(), data={'id': bid})
                flash(i18n._('Budget geändert.') if op == 'toggle' else i18n._('Budget gelöscht.'), 'ok')
            else:
                abort(400)
            return redirect(url_for('lb.budgets_view'))
        return render_template('lb_budgets.html', rows=_budget_rows(), ceiling=lb.budgets.ceiling(),
                               KEYS=i18n.d(budgetsmod.KEYS),
                               slaves=q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name') or [])

    # ------------------------------------------------------------------ #
    # Pause / holiday (doc 44 §2)
    def _pause_form(form, who):
        """Read and check a pause out of a form/JSON dict. Returns (row, error)."""
        try:
            slave = int(form.get('slave') or 0)
        except (TypeError, ValueError):
            return None, i18n._('Teilnehmerin: Zahl erwartet.')
        if slave and not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (slave,), one=True):
            return None, i18n._('Teilnehmerin unbekannt.')
        try:
            d_from = datetime.date.fromisoformat(str(form.get('from') or ''))
            d_to = datetime.date.fromisoformat(str(form.get('to') or form.get('from') or ''))
        except ValueError:
            return None, i18n._('Datum: JJJJ-MM-TT erwartet.')
        if d_to < d_from:
            return None, i18n._('Das Ende liegt vor dem Anfang.')
        if d_to < datetime.date.today():
            return None, i18n._('Die Pause läge ganz in der Vergangenheit.')
        if (d_to - d_from).days > 366:
            return None, i18n._('Länger als ein Jahr — das ist kein Urlaub mehr.')
        return {'slave': slave, 'from': d_from, 'to': d_to,
                'reason': str(form.get('reason') or '').strip()[:160], 'by': who}, None

    def _pause_save(row):
        pid = x('INSERT INTO pauses (pa_slave, pa_from, pa_to, pa_reason, pa_by) VALUES (%s,%s,%s,%s,%s)',
                (row['slave'], row['from'], row['to'], row['reason'], row['by']))
        ctx.db().commit()
        lb.pauses.invalidate()
        ctx.mq.notify_reload('logbook', row['slave'] or None)
        return pid

    def _pause_rows(include_past=False):
        cond = '' if include_past else 'WHERE p.pa_to >= CURDATE() '
        rows = q(f'SELECT p.*, s.slave_name FROM pauses p LEFT JOIN slaves s ON s.slave_id=p.pa_slave {cond}'
                 'ORDER BY p.pa_from, p.pa_slave') or []
        today = datetime.date.today()
        for r in rows:
            r['state'] = 'active' if r['pa_from'] <= today <= r['pa_to'] else ('past' if r['pa_to'] < today else 'coming')
        return rows

    @pages.route('/pauses', methods=['GET', 'POST'])
    @login_required
    def pauses_view():
        if not lb.pauses.enabled:
            flash(i18n._('Pausen nicht verfügbar — Migration 006 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            op = request.form.get('op')
            if op == 'add':
                row, bad = _pause_form(request.form, user())
                if bad:
                    flash(bad, 'error')
                    return redirect(request.form.get('back') or url_for('lb.pauses_view'))
                pid = _pause_save(row)
                audit.web('pause_add', user(), slave_id=row['slave'] or None,
                          data={'id': pid, 'from': str(row['from']), 'to': str(row['to']), 'reason': row['reason']})
                flash(i18n._('Pause eingetragen — bis {until}.', until=row['to'].strftime('%d.%m.%Y')), 'ok')
            elif op == 'delete':
                pid = int(request.form.get('pa_id') or 0)
                r = q('SELECT * FROM pauses WHERE pa_id=%s', (pid,), one=True)
                if not r:
                    abort(404)
                x('DELETE FROM pauses WHERE pa_id=%s', (pid,))
                ctx.db().commit()
                lb.pauses.invalidate()
                ctx.mq.notify_reload('logbook', r['pa_slave'] or None)
                audit.web('pause_delete', user(), slave_id=r['pa_slave'] or None, data={'id': pid, 'to': str(r['pa_to'])})
                flash(i18n._('Pause beendet.'), 'ok')
            else:
                abort(400)
            return redirect(request.form.get('back') or url_for('lb.pauses_view'))
        return render_template('lb_pauses.html', rows=_pause_rows(include_past=bool(request.args.get('all'))),
                               show_all=bool(request.args.get('all')), today=datetime.date.today(),
                               slaves=q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name') or [])

    # ------------------------------------------------------------------ #
    # Streaks (doc 44 §3): definitions. The counting happens in the logbook,
    # the consequences in the rule set; this page only says WHAT is counted.
    def _streak_form(form, who):
        key = str(form.get('key') or '').strip().lower()[:32]
        if not key or not all(c.isalnum() or c in '_-' for c in key):
            return None, i18n._('Schlüssel: Buchstaben, Ziffern, _ und - — er steht in Regeln und Protokoll.')
        name = str(form.get('name') or '').strip()[:80]
        if not name:
            return None, i18n._('Ein Name fehlt — der steht auf dem Bildschirm.')
        kind = str(form.get('kind') or '')
        if kind not in streaksmod.KINDS:
            return None, 'kind: ' + '|'.join(streaksmod.KINDS)
        action = str(form.get('action') or '').strip() or None
        if action and kind not in streaksmod.RUN_KINDS:
            action = None                       # a task only makes sense for run kinds
        if action and action not in [a.code for a in actions.ACTIONS if a.trainable]:
            return None, i18n._('Unbekannte Aufgabe.')
        ms = streaksmod.parse_milestones(form.get('milestones'))
        return {'key': key, 'name': name, 'kind': kind, 'action': action,
                'milestones': ','.join(str(m) for m in ms), 'by': who}, None

    def _streak_save(row):
        x('INSERT INTO streaks (st_key, st_name, st_kind, st_action, st_milestones, st_by) VALUES (%s,%s,%s,%s,%s,%s) '
          'ON DUPLICATE KEY UPDATE st_enabled=1, st_name=VALUES(st_name), st_kind=VALUES(st_kind), st_action=VALUES(st_action), '
          'st_milestones=VALUES(st_milestones), st_by=VALUES(st_by)',
          (row['key'], row['name'], row['kind'], row['action'], row['milestones'], row['by']))
        ctx.db().commit()
        lb.streaks.invalidate()
        ctx.mq.notify_reload('logbook')

    def _streak_rows():
        rows = q('SELECT s.*, (SELECT COUNT(*) FROM streak_state k WHERE k.sk_streak=s.st_id AND k.sk_count>0) AS running, '
                 '(SELECT MAX(sk_best) FROM streak_state k WHERE k.sk_streak=s.st_id) AS best '
                 'FROM streaks s ORDER BY s.st_id') or []
        for r in rows:
            r['kind_name'] = i18n._(streaksmod.KINDS.get(r['st_kind'], (r['st_kind'], ''))[0])
            a = actions.get(r['st_action']) if r['st_action'] else None
            r['action_name'] = a.name if a else None
        return rows

    @pages.route('/streaks', methods=['GET', 'POST'])
    @login_required
    def streaks_view():
        if not lb.streaks.enabled:
            flash(i18n._('Serien nicht verfügbar — Migration 007 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            op = request.form.get('op')
            if op == 'add':
                row, bad = _streak_form(request.form, user())
                if bad:
                    flash(bad, 'error')
                    return redirect(url_for('lb.streaks_view'))
                _streak_save(row)
                audit.web('streak_set', user(), data=row)
                flash(i18n._('Serie gespeichert.'), 'ok')
            elif op in ('toggle', 'delete', 'reset'):
                sid = int(request.form.get('st_id') or 0)
                r = q('SELECT * FROM streaks WHERE st_id=%s', (sid,), one=True)
                if not r:
                    abort(404)
                if op == 'toggle':
                    x('UPDATE streaks SET st_enabled=1-st_enabled, st_by=%s WHERE st_id=%s', (user(), sid))
                elif op == 'reset':
                    # the counters, not the definition - for a fresh start
                    x('DELETE FROM streak_state WHERE sk_streak=%s', (sid,))
                else:
                    x('DELETE FROM streaks WHERE st_id=%s', (sid,))
                ctx.db().commit()
                lb.streaks.invalidate()
                ctx.mq.notify_reload('logbook')
                audit.web('streak_' + op, user(), data={'id': sid, 'key': r['st_key']})
                flash({'toggle': i18n._('Serie geändert.'), 'delete': i18n._('Serie gelöscht.'),
                       'reset': i18n._('Zähler zurückgesetzt.')}[op], 'ok')
            else:
                abort(400)
            return redirect(url_for('lb.streaks_view'))
        return render_template('lb_streaks.html', rows=_streak_rows(), KINDS=i18n.d(streaksmod.KINDS),
                               RUN_KINDS=streaksmod.RUN_KINDS)

    # ------------------------------------------------------------------ #
    # Scenarios (doc 44 §7): the bundle with a name
    def _scenario_form(form, who):
        name = str(form.get('name') or '').strip()[:80]
        if not name:
            return None, i18n._('Ein Name fehlt.')
        note = str(form.get('note') or '').strip()[:255] or None
        try:
            plan = int(form.get('day_plan') or 0) or None
        except (TypeError, ValueError):
            return None, i18n._('Tagesplan: Zahl erwartet.')
        if plan and not q('SELECT dp_id FROM day_plans WHERE dp_id=%s', (plan,), one=True):
            return None, i18n._('Tagesplan unbekannt.')
        dayform = str(form.get('dayform') or '') or None
        if dayform and dayform not in dayformmod.FORMS:
            return None, 'dayform: easy|normal|strict'
        sanctions = form.getlist('sanctions') if hasattr(form, 'getlist') else list(form.get('sanctions') or [])
        bad_s = [k for k in sanctions if k not in lbmod.SANCTIONS]
        if bad_s:
            return None, i18n._('Unbekannte Auflage: {key}', key=bad_s[0])
        if isinstance(form.get('budgets'), list):
            budgets = scenariosmod.parse_budgets(json.dumps(form.get('budgets')))
        elif form.get('b_key_0') is not None:
            # The rows of the editor (2.5). The text box before it wanted five
            # values in a fixed order and named the possible keys nowhere — the
            # fourth place where an exact string had to be typed (finding Philine
            # 2026-09-17). The line form stays for the REST interface and for
            # older clients, so both roads end in the same list of dicts.
            budgets, codes = [], [a.code for a in actions.ACTIONS if a.trainable]
            for i in range(20):
                key = (form.get('b_key_%d' % i) or '').strip()
                if not key:
                    continue
                if not budgetsmod.valid_key(key, codes):
                    return None, i18n._('Unbekanntes Budget: {key}', key=key)
                period = (form.get('b_period_%d' % i) or 'day').strip()
                if period not in budgetsmod.PERIODS:
                    return None, 'period: ' + '|'.join(budgetsmod.PERIODS)
                cnt = (form.get('b_count_%d' % i) or '').strip()
                gap = (form.get('b_gap_%d' % i) or '').strip()
                if not cnt.isdigit() and not gap.isdigit():
                    return None, i18n._('„{key}“: mindestens eine Angabe — Anzahl oder Abstand.',
                                        key=budgetsmod.key_label(key))
                og = (form.get('b_ongap_%d' % i) or '').strip()
                if og not in budgetsmod.ON_GAP:
                    og = 'drop' if key == 'reward' else 'queue'
                budgets.append({'key': key, 'period': period,
                                'max_count': int(cnt) if cnt.isdigit() else None,
                                'min_gap_s': int(gap) if gap.isdigit() else None, 'on_gap': og})
        else:
            budgets, bad = scenariosmod.parse_budget_lines(form.get('budgets'))
            if bad:
                return None, i18n._('Budget-Zeile {n} passt nicht: „{line}“ — Form: key day|week Anzahl Abstand queue|drop', n=bad[0], line=bad[1])
        cap = int(lb.limits.get('channel_day_max') or 0)
        for b in budgets:
            if b['key'] == 'punish' and b['period'] == 'day' and cap and b['max_count'] and b['max_count'] > cap:
                return None, i18n._('Über der Decke aus config.ini [safety] ({cap}) — ein Budget kann nur verschärfen.', cap=cap)
        return {'name': name, 'note': note, 'day_plan': plan, 'dayform': dayform, 'sanctions': sanctions,
                'budgets': budgets, 'by': who}, None

    @pages.route('/scenarios', methods=['GET', 'POST'])
    @login_required
    def scenarios_view():
        if not lb.scenarios.enabled:
            flash(i18n._('Szenarien nicht verfügbar — Migration 011 fehlt.'), 'error')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            op = request.form.get('op')
            if op in ('add', 'edit'):
                row, bad = _scenario_form(request.form, user())
                if bad:
                    flash(bad, 'error')
                    return redirect(url_for('lb.scenarios_view'))
                sn_id = int(request.form.get('sn_id') or 0) if op == 'edit' else None
                if q('SELECT sn_id FROM scenarios WHERE sn_name=%s AND sn_id<>%s', (row['name'], sn_id or 0), one=True):
                    flash(i18n._('Diesen Namen gibt es schon.'), 'error')
                    return redirect(url_for('lb.scenarios_view'))
                sn_id = lb.scenarios.save(row['name'], row['note'], row['day_plan'], row['dayform'], row['sanctions'],
                                          row['budgets'], user(), sn_id=sn_id)
                ctx.db().commit()
                audit.web('scenario_save', user(), data=dict(row, id=sn_id))
                flash(i18n._('Szenario gespeichert.'), 'ok')
            elif op == 'delete':
                sn_id = int(request.form.get('sn_id') or 0)
                if not lb.scenarios.get(sn_id):
                    abort(404)
                lb.scenarios.delete(sn_id, user())
                ctx.db().commit()
                ctx.mq.notify_reload('logbook')
                audit.web('scenario_delete', user(), data={'id': sn_id})
                flash(i18n._('Szenario gelöscht — wo es lief, ist es beendet.'), 'ok')
            else:
                abort(400)
            return redirect(url_for('lb.scenarios_view'))
        rows = lb.scenarios.list()
        for r in rows:
            r['budget_lines'] = scenariosmod.budget_lines(r['budgets'])
        edit = None
        if request.args.get('edit'):
            edit = next((r for r in rows if str(r['sn_id']) == request.args.get('edit')), None)
        # The keys that exist — so they can be chosen instead of typed, and so
        # the legend names them out of the same source as the list. A task is
        # offered under its speaking name, not under its code: "Runs shock" is
        # a sentence, "activity:SHOCK" is a format.
        bkeys = [(k, v[0], v[1]) for k, v in i18n.d(budgetsmod.KEYS).items()]
        bkeys += [(budgetsmod.ACTIVITY_PREFIX + a.code, i18n._('Durchgänge {task}', task=a.name),
                   i18n._('Nur diese eine Aufgabe: Anzahl zählt für die Rangliste, Abstand ist die '
                          'Pause bis zur Wiederholung.'))
                  for a in actions.ACTIONS if a.trainable]
        # The existing rows plus three empty ones: enough to add something
        # without the page living off empty rows.
        brows = list((edit or {}).get('budgets') or []) + [{}] * 3
        return render_template('lb_scenarios.html', rows=rows, edit=edit,
                               bkeys=bkeys, brows=brows, PERIODS=budgetsmod.PERIODS,
                               ON_GAP=budgetsmod.ON_GAP,
                               plans=q('SELECT dp_id, dp_name FROM day_plans ORDER BY dp_name') or [],
                               active=q('SELECT a.*, s.slave_name, n.sn_name FROM scenario_active a '
                                        'JOIN slaves s ON s.slave_id=a.sx_slave JOIN scenarios n ON n.sn_id=a.sx_scenario '
                                        'ORDER BY a.sx_until') or [])

    @pages.route('/slaves/<int:sid>/scenario', methods=['POST'])
    @login_required
    def slave_scenario(sid):
        slave_or_404(sid)
        if not lb.scenarios.enabled:
            flash(i18n._('Szenarien nicht verfügbar — Migration 011 fehlt.'), 'error')
            return redirect(url_for('slave_detail', sid=sid) + '#rang')
        if request.form.get('op') == 'end':
            lb.scenarios.deactivate(sid, user(), 'ended by supervisor')
            ctx.db().commit()
            audit.web('scenario_end', user(), slave_id=sid, data={})
            flash(i18n._('Szenario beendet — Plan, Auflagen, Budgets und Tagesform sind zurück.'), 'ok')
        else:
            try:
                sn_id = int(request.form.get('scenario') or 0)
                until = datetime.date.fromisoformat(str(request.form.get('until') or ''))
            except ValueError:
                flash(i18n._('Datum: JJJJ-MM-TT erwartet.'), 'error')
                return redirect(url_for('slave_detail', sid=sid) + '#rang')
            ok, why = lb.scenarios.activate(sid, sn_id, until, user())
            ctx.db().commit()
            if not ok:
                flash(i18n._('Szenario nicht aktiviert: {why}', why=why), 'error')
            else:
                audit.web('scenario_activate', user(), slave_id=sid, data={'scenario': sn_id, 'until': until.isoformat()})
                flash(i18n._('Szenario aktiv bis {until}.', until=until.strftime('%d.%m.%Y')), 'ok')
        ctx.mq.notify_reload('logbook', sid)
        return redirect(url_for('slave_detail', sid=sid) + '#rang')

    def _rule_param_from_form(effect, form):
        """Build the effect's value out of the separate fields of the form (doc 58 §5).

        Until 2.4 "Wert" was one free-text field whose syntax changed with the
        effect — `restrained:d:r3` packs three ideas into one string, and the
        keys one had to type stood in the panel on the OTHER side of the screen.
        Three fields do the same without anyone reproducing a string.

        The field `param` stays as the fallback: the REST API sends the composed
        value, and so does anything built before this change. A form that does
        not carry the pieces therefore behaves exactly as it did."""
        g = lambda n: (form.get(n) or '').strip()                       # noqa: E731
        if effect in ('punish', 'reward'):
            return g('p_level') or None
        if effect in ('privilege_grant', 'privilege_revoke'):
            key = g('p_priv')
            if not key:
                return None
            weeks = g('p_weeks')
            return key + (':' + weeks if effect == 'privilege_grant' and weeks and weeks != '0' else '')
        if effect in ('sanction_impose', 'sanction_lift'):
            key = g('p_sanc')
            if not key:
                return None
            if effect == 'sanction_lift':
                return key                       # lifting takes the key and nothing else
            out = key
            dur = g('p_dur')                     # '' = until somebody lifts it, 'd', or hours
            if dur == 'd':
                out += ':d'
            elif dur == 'h' and g('p_hours'):
                out += ':' + g('p_hours')
            runs = g('p_runs')
            if runs and runs != '0':
                out += ':r' + runs
            return out
        if effect == 'detention':
            return g('p_action')                 # empty = the task of the occasion
        if effect == 'day_minutes':
            v = g('p_dm')
            if not v:
                return None
            return ('%+d' % int(v)) if g('p_dm_mode') == 'rel' else str(int(v))
        if effect == 'points':
            return g('p_points') or None
        if effect == 'badge':
            return g('p_badge') or None
        if effect == 'dayform':
            f = g('p_form')
            return (f + (':+1' if g('p_tomorrow') else '')) if f else None
        return None

    def _rule_param_parts(effect, param):
        """The inverse of `_rule_param_from_form`: a stored value back into the
        single fields, so "duplicate and adjust" can fill the form (doc 58 §9)."""
        p = (param or '').strip()
        out = {}
        if effect in ('punish', 'reward'):
            out['p_level'] = p or '1'
        elif effect in ('privilege_grant', 'privilege_revoke'):
            key, _, weeks = p.partition(':')
            out['p_priv'], out['p_weeks'] = key, (weeks or '0')
        elif effect in ('sanction_impose', 'sanction_lift'):
            parts = [t.strip() for t in p.split(':') if t.strip()]
            out['p_sanc'] = parts[0] if parts else ''
            out['p_dur'], out['p_hours'], out['p_runs'] = '', '2', '0'
            for e in parts[1:]:
                if e == 'd':
                    out['p_dur'] = 'd'
                elif e[:1].lower() == 'r' and e[1:].isdigit():
                    out['p_runs'] = e[1:]
                else:
                    out['p_dur'], out['p_hours'] = 'h', e
        elif effect == 'detention':
            out['p_action'] = p
        elif effect == 'day_minutes':
            out['p_dm_mode'] = 'rel' if p[:1] in '+-' else 'abs'
            out['p_dm'] = p.lstrip('+') or '30'
        elif effect == 'points':
            out['p_points'] = p or '10'
        elif effect == 'badge':
            out['p_badge'] = p
        elif effect == 'dayform':
            f, _, when = p.partition(':')
            out['p_form'], out['p_tomorrow'] = f, ('1' if when else '')
        return out

    def _rule_param_error(effect, param):
        """Check the effect's value up front, so a rule is not noticed only at the trigger."""
        try:
            if effect in ('punish', 'reward'):
                if not 1 <= int(param or 0) <= 3:
                    return 'Stärkestufe: 1, 2 oder 3.'
            elif effect in ('privilege_grant', 'privilege_revoke'):
                key = param.split(':', 1)[0]
                if key not in lbmod.PRIVILEGES:
                    return 'Unbekanntes Privileg — Schlüssel aus der Liste rechts.'
                if ':' in param:
                    int(param.split(':', 1)[1])
            elif effect in ('sanction_impose', 'sanction_lift'):
                # Up to here the value of the sanction was NOT checked. A typo
                # in the key was then noticed only at the trigger — and there
                # silently: the rule ran, imposed nothing and wrote a line into
                # the log that nobody reads.
                parts = [t.strip() for t in param.split(':')]
                if parts[0] not in lbmod.SANCTIONS:
                    return 'Unbekannte Auflage — Schlüssel aus der Liste rechts.'
                if effect == 'sanction_lift' and len(parts) > 1:
                    return 'Aufheben nimmt nur den Schlüssel, keine Dauer.'
                for extra in parts[1:]:
                    if extra == 'd' or (extra[:1].lower() == 'r' and extra[1:].isdigit()):
                        continue
                    if float(extra) <= 0:
                        return 'Die Dauer in Stunden muss größer als 0 sein.'
            elif effect == 'day_minutes':
                int(param.lstrip('+'))
            elif effect == 'points':
                int(param)
            elif effect == 'badge':
                if param not in lbmod.BADGES:
                    return 'Unbekanntes Abzeichen — Schlüssel aus der Liste rechts.'
            elif effect == 'dayform':
                form, _, when = param.partition(':')
                if form.strip().lower() not in dayformmod.FORMS:
                    return i18n._('Tagesform: easy, normal oder strict — optional :+1 für morgen.')
                if when and when.strip() not in ('+1', '1'):
                    return i18n._('Tagesform: easy, normal oder strict — optional :+1 für morgen.')
        except (TypeError, ValueError):
            return f'„{param}“ passt nicht zu dieser Wirkung.'
        return None

    # ------------------------------------------------------------------ #
    @pages.route('/slaves/<int:sid>/settings', methods=['POST'])
    @login_required
    def slave_settings(sid):
        slave_or_404(sid)
        if not lb.day_enabled:
            abort(400)
        plan = int(request.form.get('day_plan') or 0) or None
        if plan and not q('SELECT dp_id FROM day_plans WHERE dp_id=%s', (plan,), one=True):
            abort(400)
        hard = int(lb.limits['day_minutes_max'])
        minutes = max(15, min(hard, int(request.form.get('day_minutes') or lb.limits['day_minutes_default'])))
        relogin = 1 if request.form.get('relogin') else 0
        x('INSERT INTO slave_settings (ss_slave, ss_day_plan, ss_day_minutes, ss_relogin, ss_by) VALUES (%s,%s,%s,%s,%s) '
          'ON DUPLICATE KEY UPDATE ss_day_plan=VALUES(ss_day_plan), ss_day_minutes=VALUES(ss_day_minutes), '
          'ss_relogin=VALUES(ss_relogin), ss_by=VALUES(ss_by)', (sid, plan, minutes, relogin, user()))
        ctx.db().commit()
        audit.web('slave_settings', user(), slave_id=sid, data={'day_plan': plan, 'day_minutes': minutes, 'relogin': relogin})
        ctx.mq.notify_reload('logbook', sid)
        flash(f'Tageseinstellungen gespeichert — Tagesdauer {minutes} min'
              + (f' (an der Grenze aus [safety]: {hard} min)' if minutes == hard else '') + '.', 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#tag')

    @pages.route('/export')
    @login_required
    def export_view():
        return render_template('lb_export.html', n=q('SELECT COUNT(*) AS n FROM achievements', one=True)['n'])

    @pages.route('/export/download')
    @login_required
    def export_download():
        data = _export_zip(q, ctx.config)
        audit.web('export', user(), data={'bytes': len(data)})
        return Response(data, mimetype='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="punisher_export_{datetime.date.today().isoformat()}.zip"'})

    # Data for the slave page (panel "Logbook")
    def slave_logbook_context(sid):
        if not lb.enabled:
            return None
        cur = lbmod.week_str()
        nxt = lbmod.next_week(cur)
        ctxd = {
            'summary': lb.summary(sid), 'rank_rows': lb.ranks(),
            'tasks_cur': weekly(sid, cur), 'tasks_next': weekly(sid, nxt),
            'runs': runs('a.ach_slave=%s', (sid,), 12),
            'reviews': q('SELECT wr_week, wr_rank_before, wr_rank_after, wr_score, wr_place, wr_reason FROM weekly_review WHERE wr_slave=%s ORDER BY wr_week DESC LIMIT 8', (sid,)),
            # A challenge is a leaderboard across all slaves (doc 14 §12.4):
            # the field stands in challenge_entries, no longer in ch_slave_a/b.
            'challenges': q('SELECT c.ch_id, c.ch_week, c.ch_action, c.ch_target, c.ch_status, c.ch_winner, '
                            '       e.ce_place, e.ce_points, e.ce_grade, e.ce_best, e.ce_punish, e.ce_note, '
                            '       (SELECT COUNT(*) FROM challenge_entries e2 WHERE e2.ce_challenge=c.ch_id) AS n_field, '
                            '       sw.slave_name AS winner_name '
                            '  FROM challenges c JOIN challenge_entries e ON e.ce_challenge=c.ch_id '
                            '  LEFT JOIN slaves sw ON sw.slave_id=c.ch_winner '
                            ' WHERE e.ce_slave=%s AND c.ch_week>=%s ORDER BY c.ch_id DESC', (sid, cur))
                          if lb.day_enabled else [],
            'level_actions': [a for a in actions.ACTIONS if a.trainable],
        }
        if lb.day_enabled:
            ctxd['settings'] = q('SELECT * FROM slave_settings WHERE ss_slave=%s', (sid,), one=True)
            ctxd['day_plans'] = q('SELECT dp_id, dp_name, dp_default FROM day_plans ORDER BY dp_default DESC, dp_name')
            ctxd['day_minutes'] = lb.day_minutes(sid)
            ctxd['day'] = q("SELECT d.*, p.dp_name FROM day_sessions d LEFT JOIN day_plans p ON p.dp_id=d.ds_plan "
                            "WHERE d.ds_slave=%s ORDER BY d.ds_day DESC LIMIT 1", (sid,), one=True)
        return ctxd
    ctx.slave_logbook_context = slave_logbook_context

    # ================================================================== #
    # REST-API
    def err(msg, code=400):
        return jsonify(ok=False, error=msg), code

    def auth_required(f):
        return ctx.api_auth_required(f)

    def body():
        j = request.get_json(silent=True)
        return j if isinstance(j, dict) else {}

    def api_user():
        return getattr(request, 'api_user', None) or ctx.WEB_USER

    def run_json(r):
        return {'id': r['ach_id'], 'slave_id': r['ach_slave'], 'slave_name': r.get('slave_name'), 'action': r['ach_action'],
                'action_name': action_name(r['ach_action']), 'device': r['ach_device'], 'level': r['ach_level'], 'week': r['ach_week'],
                'day': str(r['ach_day']), 'started': str(r['ach_started']), 'ended': str(r['ach_ended']) if r['ach_ended'] else None,
                'duration_s': r['ach_duration_s'], 'target': r['ach_target'], 'unit': r['ach_target_unit'],
                'target_text': lbmod.Logbook.target_text(r['ach_target'], r['ach_target_unit']),
                'max_punish': r['ach_max_punish'], 'punish': r['ach_punish'], 'warn': r['ach_warn'], 'metrics': r.get('metrics') or {},
                'grade': r['ach_grade'], 'points': r['ach_points'], 'counted': bool(r['ach_counted']), 'best': bool(r['ach_best']),
                'status': r['ach_status'], 'note': r['ach_note']}

    def task_json(t):
        return {'id': t['wt_id'], 'week': t['wt_week'], 'action': t['wt_action'], 'action_name': action_name(t['wt_action']),
                'target': t['wt_target'], 'unit': t['unit'], 'target_text': lbmod.Logbook.target_text(t['wt_target'], t['unit']),
                'max_punish': t['wt_max_punish'], 'kind': t['wt_kind'], 'status': t['wt_status'], 'done_ach': t['wt_done_ach'],
                'by': t['wt_by']}

    @api.route('/logbook')
    @auth_required
    def api_logbook():
        where, params = [], []
        for k, col in (('slave', 'a.ach_slave'), ('action', 'a.ach_action'), ('week', 'a.ach_week'), ('status', 'a.ach_status')):
            v = request.args.get(k, '').strip()
            if v:
                where.append(col + '=%s'); params.append(int(v) if k == 'slave' else v)
        limit = min(int(request.args.get('limit', '100') or 100), 500)
        return jsonify(ok=True, enabled=lb.enabled, runs=[run_json(r) for r in runs(' AND '.join(where), params, limit)])

    @api.route('/leaderboard')
    @auth_required
    def api_leaderboard():
        if not lb.enabled:
            return jsonify(ok=True, enabled=False, week=[], total=[])
        week = request.args.get('week') or lbmod.week_str()
        b = lb.leaderboard(week)
        b['ok'] = True
        b['enabled'] = True
        return jsonify(b)

    @api.route('/ranks')
    @auth_required
    def api_ranks():
        rows = lb.ranks() if lb.enabled else []
        return jsonify(ok=True, ranks=[{'no': r['rank_no'], 'name': r['name'], 'name_main': r['rank_name'], 'name_alt': r['rank_name_alt'],
                                        'up_tasks': r['rank_up_tasks'], 'up_grade': r['rank_up_grade'], 'up_best': r['rank_up_best'],
                                        'up_plan': bool(r['rank_up_plan'])} for r in rows],
                       name_set=lb.sc_str('rank_names', 'main') if lb.enabled else 'main')

    @api.route('/ranks', methods=['PUT'])
    @auth_required
    def api_ranks_put():
        j = body()
        for r in j.get('ranks') or []:
            no = int(r.get('no') or 0)
            if 1 <= no <= 10:
                cur = q('SELECT * FROM ranks WHERE rank_no=%s', (no,), one=True)
                if not cur:
                    continue
                x('UPDATE ranks SET rank_name=%s, rank_name_alt=%s, rank_up_tasks=%s, rank_up_grade=%s, rank_up_best=%s, rank_up_plan=%s WHERE rank_no=%s',
                  (str(r.get('name_main', cur['rank_name']))[:40], str(r.get('name_alt', cur['rank_name_alt']))[:40],
                   int(r.get('up_tasks', cur['rank_up_tasks'])), str(r.get('up_grade', cur['rank_up_grade']))[:1].upper(),
                   int(r.get('up_best', cur['rank_up_best'])), 1 if r.get('up_plan', cur['rank_up_plan']) else 0, no))
        if j.get('name_set') in ('main', 'alt'):
            lb.set_scoring('rank_names', j['name_set'])
        ctx.db().commit()
        audit.web('ranks_update', api_user())
        ctx.mq.notify_reload('logbook')
        return api_ranks()

    @api.route('/scoring')
    @auth_required
    def api_scoring():
        rows = q("SELECT * FROM scoring WHERE sc_key NOT LIKE 'last_%%' ORDER BY sc_key")
        return jsonify(ok=True, scoring=[{'key': r['sc_key'], 'value': r['sc_value'], 'desc': r['sc_desc']} for r in rows])

    @api.route('/scoring', methods=['PUT'])
    @auth_required
    def api_scoring_put():
        j = body()
        for k, v in (j.get('scoring') or {}).items():
            if not str(k).startswith('last_'):
                lb.set_scoring(str(k)[:32], str(v)[:64])
        ctx.db().commit()
        audit.web('scoring_update', api_user(), data=j.get('scoring'))
        ctx.mq.notify_reload('logbook')
        return api_scoring()

    @api.route('/slaves/<int:sid>/logbook')
    @auth_required
    def api_slave_logbook(sid):
        if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
            return err('nicht gefunden', 404)
        if not lb.enabled:
            return jsonify(ok=True, enabled=False)
        cur = lbmod.week_str()
        nxt = lbmod.next_week(cur)
        summ = lb.summary(sid)
        return jsonify(ok=True, enabled=True, summary=summ,
                       tasks_current=[task_json(t) for t in weekly(sid, cur)],
                       tasks_next=[task_json(t) for t in weekly(sid, nxt)],
                       runs=[run_json(r) for r in runs('a.ach_slave=%s', (sid,), int(request.args.get('limit', '30') or 30))],
                       reviews=[{'week': r['wr_week'], 'rank_before': r['wr_rank_before'], 'rank_after': r['wr_rank_after'],
                                 'score': r['wr_score'], 'place': r['wr_place'], 'reason': r['wr_reason'], 'grades': r['wr_grades'],
                                 'plan_done': r['wr_plan_done'], 'plan_total': r['wr_plan_total'], 'punish': r['wr_punish'],
                                 'sanctions': r['wr_sanctions'], 'sanctions_open': r['wr_sanctions_open'],
                                 'remark': r['wr_remark']}
                                for r in q('SELECT * FROM weekly_review WHERE wr_slave=%s ORDER BY wr_week DESC LIMIT 12', (sid,))],
                       ranks=[{'no': r['rank_no'], 'name': r['name']} for r in lb.ranks()],
                       badges_all={k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.BADGES.items()},
                       privileges_all={k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.PRIVILEGES.items()},
                       sanctions_all={k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.SANCTIONS.items()},
                       trainable=[{'code': a.code, 'name': a.name, 'unit': tasktypes.get(a.code).target_unit,
                                   'plan_default': tasktypes.get(a.code).plan_default} for a in actions.ACTIONS if a.trainable])

    @api.route('/slaves/<int:sid>/rank', methods=['PUT'])
    @auth_required
    def api_slave_rank(sid):
        if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
            return err('nicht gefunden', 404)
        j = body()
        cur_rank, cur_frozen = lb.rank_of(sid)
        rank_no = int(j.get('rank', cur_rank))
        frozen = bool(j.get('frozen', cur_frozen))
        lb.set_rank(sid, rank_no, by=api_user(), frozen=frozen, reason='Aufsicht (App)')
        audit.web('rank_set', api_user(), slave_id=sid, data={'rank': rank_no, 'frozen': frozen})
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(ok=True, rank=rank_no, frozen=frozen, rank_name=lb.rank_name(rank_no))

    @api.route('/slaves/<int:sid>/level', methods=['PUT'])
    @auth_required
    def api_slave_level(sid):
        j = body()
        code = str(j.get('action', ''))
        if not tasktypes.get(code):
            return err('unbekannte Aufgabe')
        out = {'ok': True, 'action': code}
        if 'min' in j or 'max' in j:
            res = lb.set_level_bounds(sid, code, j.get('min'), j.get('max'), by=api_user())
            if res is None:
                return err('Stufengrenzen nicht verfügbar (Migration 008 fehlt)', 409)
            out['min'], out['max'] = res
            audit.web('level_bounds', api_user(), slave_id=sid, data={'action': code, 'min': res[0], 'max': res[1]})
        if 'level' in j:
            level = lb.set_level(sid, code, int(j.get('level') or 1), by=api_user())
            audit.web('level_set', api_user(), slave_id=sid, data={'action': code, 'level': level})
            out['level'] = level
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(**out)

    @api.route('/slaves/<int:sid>/privileges', methods=['PUT'])
    @auth_required
    def api_slave_privilege(sid):
        j = body()
        key = str(j.get('key', ''))
        if key not in lbmod.PRIVILEGES:
            return err('unbekanntes Privileg')
        if j.get('granted', True):
            lb.grant_privilege(sid, key, by=api_user())
        else:
            lb.revoke_privilege(sid, key, by=api_user())
        audit.web('privilege_set', api_user(), slave_id=sid, data={'key': key, 'granted': bool(j.get('granted', True))})
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(ok=True, privileges=lb.privileges_of(sid))

    @api.route('/slaves/<int:sid>/sanctions')
    @ctx.api_auth_required
    def api_sanctions(sid):
        return jsonify(ok=True, sanctions=lb.sanctions_of(sid),
                       catalogue={k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.SANCTIONS.items()})

    @api.route('/slaves/<int:sid>/sanctions', methods=['PUT'])
    @ctx.api_auth_required
    def api_sanction_set(sid):
        """Impose or lift a sanction (doc 26).

        {"key": "restrained", "op": "impose", "hours": 2, "until_day": false,
         "runs": 3, "reason": "..."}  or {"key": "...", "op": "lift"}
        """
        j = request.get_json(silent=True) or {}
        key = str(j.get('key', ''))
        if key not in lbmod.SANCTIONS:
            return jsonify(ok=False, error='unbekannte Auflage'), 400
        who = 'api:' + str(getattr(request, 'api_user', '?'))
        if j.get('op') == 'lift':
            lb.lift_sanction(sid, key, by=who)
            imposed = False
        else:
            imposed = lb.impose_sanction(sid, key, by=who, reason=str(j.get('reason', ''))[:160],
                                         hours=j.get('hours'), until_day=bool(j.get('until_day')),
                                         runs=j.get('runs'))
        audit.web('sanction_' + (j.get('op') or 'impose'), who, slave_id=sid, data=j)
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(ok=True, imposed=imposed, sanctions=lb.sanctions_of(sid))

    @api.route('/slaves/<int:sid>/weekly', methods=['POST'])
    @auth_required
    def api_slave_weekly_add(sid):
        if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
            return err('nicht gefunden', 404)
        j = body()
        code = str(j.get('action', ''))
        t = tasktypes.get(code)
        if not t:
            return err('unbekannte Aufgabe')
        week = str(j.get('week') or lbmod.week_str())
        target = int(j.get('target') or t.plan_default)
        mp = int(j.get('max_punish') if j.get('max_punish') is not None else lb.default_max_punish())
        wid = x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_by) "
                "VALUES (%s,%s,%s,%s,%s,'plan','open',%s)", (sid, week, code, target, mp, api_user()))
        ctx.db().commit()
        audit.web('weekly_add', api_user(), slave_id=sid, data={'week': week, 'action': code, 'target': target})
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(ok=True, id=wid, tasks=[task_json(t) for t in weekly(sid, week)]), 201

    @api.route('/weekly/<int:wid>', methods=['PUT', 'DELETE'])
    @auth_required
    def api_weekly_task(wid):
        t = q('SELECT * FROM weekly_tasks WHERE wt_id=%s', (wid,), one=True)
        if not t:
            return err('nicht gefunden', 404)
        if request.method == 'DELETE':
            x('DELETE FROM weekly_tasks WHERE wt_id=%s', (wid,))
            audit.web('weekly_delete', api_user(), slave_id=t['wt_slave'], data={'wt_id': wid})
        else:
            j = body()
            st = str(j.get('status', t['wt_status']))
            if st not in ('proposed', 'open', 'done', 'failed'):
                return err('status')
            x('UPDATE weekly_tasks SET wt_status=%s, wt_target=%s, wt_max_punish=%s, wt_by=%s WHERE wt_id=%s',
              (st, int(j.get('target', t['wt_target'])), int(j.get('max_punish', t['wt_max_punish'])), api_user(), wid))
            audit.web('weekly_update', api_user(), slave_id=t['wt_slave'], data={'wt_id': wid, 'status': st})
        ctx.db().commit()
        ctx.mq.notify_reload('logbook', t['wt_slave'])
        return jsonify(ok=True)

    @api.route('/weekly')
    @auth_required
    def api_weekly_all():
        week = request.args.get('week') or lbmod.week_str()
        out = []
        for s in q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name'):
            out.append({'slave_id': s['slave_id'], 'name': s['slave_name'], 'tasks': [task_json(t) for t in weekly(s['slave_id'], week)]})
        return jsonify(ok=True, week=week, slaves=out)

    @api.route('/weekly/request', methods=['POST'])
    @auth_required
    def api_weekly_request():
        j = body()
        what = str(j.get('what', ''))
        if what not in ('propose', 'activate', 'review'):
            return err('what: propose|activate|review')
        ctx.mq.request(what, user=api_user(), week=j.get('week'))
        return jsonify(ok=True, requested=what)

    @api.route('/slaves/<int:sid>/channel', methods=['POST'])
    @auth_required
    def api_slave_channel(sid):
        if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
            return err('nicht gefunden', 404)
        j = body()
        what = 'reward' if j.get('what') == 'reward' else 'punish'
        ctx.mq.request(what, user=api_user(), slave_id=sid, level=int(j.get('level') or 1),
                       kind=str(j.get('kind') or 'any'), reason=str(j.get('reason') or 'aufsicht'))
        return jsonify(ok=True, requested=what)

    @api.route('/challenges')
    @auth_required
    def api_challenges():
        """Challenges as a leaderboard (doc 14 §12.4). The frozen app 1.1 only knows
        the duel: 'entries' is new, slave_a/slave_b/winner stay filled with the first two
        placed, so that its view shows nothing wrong (decision Philine: the app stays
        untouched)."""
        if not lb.day_enabled:
            return jsonify(ok=True, mode='duel', challenges=[])
        week = request.args.get('week') or lbmod.week_str()
        out = []
        for c in lb.challenge_board(week):
            e = c['entries']
            first = e[0] if len(e) > 0 else None
            second = e[1] if len(e) > 1 else None
            out.append({'id': c['id'], 'week': c['week'], 'action': c['action'], 'action_name': c['action_name'],
                        'target': c['target'], 'unit': c['unit'], 'target_text': c['target_text'],
                        'metric': c['metric'], 'status': c['status'],
                        'routine': c['routine'], 'routine_name': c['routine_name'],
                        'winner': c['winner'],
                        'winner_name': next((r['name'] for r in e if r['slave_id'] == c['winner']), None),
                        'field': len(e), 'entries': e,
                        # backward-compatible fields for app 1.1
                        'slave_a': (first or {}).get('slave_id'), 'name_a': (first or {}).get('name'),
                        'slave_b': (second or {}).get('slave_id'), 'name_b': (second or {}).get('name')})
        return jsonify(ok=True, mode='board', week=week, challenges=out)

    @api.route('/challenges', methods=['POST'])
    @auth_required
    def api_challenge_create():
        if not lb.day_enabled:
            return err('Tagesmodell/Bestenliste nicht verfügbar (Migration 007 fehlt)', 409)
        j = body()
        code = str(j.get('action', ''))
        t = tasktypes.get(code)
        if not t:
            return err('action: trainierbare Aufgabe')
        # 'field' is the new way; slave_a/slave_b is still taken from the old app
        field = [int(v) for v in (j.get('field') or []) if str(v).isdigit()]
        if not field:
            field = [int(v) for v in (j.get('slave_a'), j.get('slave_b')) if v]
        if not field:
            field = [int(r['slave_id']) for r in q('SELECT slave_id FROM slaves ORDER BY slave_name') or []]
        field = sorted({s for s in field if q('SELECT slave_id FROM slaves WHERE slave_id=%s', (s,), one=True)})
        if len(field) < 2:
            return err('mindestens zwei Sklaven')
        week = str(j.get('week') or lbmod.week_str())
        target = int(j.get('target') or t.plan_default)
        if (q("SELECT ch_id FROM challenges WHERE ch_week=%s AND ch_action=%s AND ch_status='open'", (week, code), one=True)
                and not j.get('confirm_dup')):
            return err('in dieser Woche läuft schon eine offene Herausforderung in dieser Aufgabe '
                       '(confirm_dup=true erzwingt es)', 409)
        cid, n = _challenge_add(code, week, target, field, api_user())
        return jsonify(ok=True, id=cid, field=n), 201

    @api.route('/challenges/<int:cid>/decide', methods=['POST'])
    @auth_required
    def api_challenge_decide(cid):
        if not q('SELECT ch_id FROM challenges WHERE ch_id=%s', (cid,), one=True):
            return err('nicht gefunden', 404)
        res = lb.decide_challenge(cid, by=api_user()) if lb.enabled else None
        ctx.db().commit()
        audit.web('challenge_decide', api_user(), data={'id': cid, 'places': res})
        ctx.mq.notify_reload('logbook')
        return jsonify(ok=bool(res), places=res or [], error=None if res else 'weniger als zwei Sklaven — ungültig')

    @api.route('/challenges/<int:cid>', methods=['DELETE'])
    @auth_required
    def api_challenge_delete(cid):
        if not q('SELECT ch_id FROM challenges WHERE ch_id=%s', (cid,), one=True):
            return err('nicht gefunden', 404)
        x('DELETE FROM weekly_tasks WHERE wt_challenge=%s', (cid,))
        x('DELETE FROM challenges WHERE ch_id=%s', (cid,))
        ctx.db().commit()
        audit.web('challenge_delete', api_user(), data={'id': cid})
        ctx.mq.notify_reload('logbook')
        return jsonify(ok=True)

    # ------------------------------------------------------------------ #
    # Day plan, rule set, day settings (doc 14 §12) — API
    @api.route('/dayplans')
    @auth_required
    def api_dayplans():
        if not lb.day_enabled:
            return jsonify(ok=True, enabled=False, plans=[])
        return jsonify(ok=True, enabled=True, kinds={k: v[0] for k, v in BLOCK_KINDS.items()},
                       plans=[{'id': p['dp_id'], 'name': p['dp_name'], 'note': p['dp_note'],
                               'default': bool(p['dp_default']), 'total_min': p['total_min'], 'slaves': p['n_slaves'],
                               'blocks': [{'id': b['db_id'], 'pos': b['db_pos'], 'kind': b['db_kind'],
                                           'minutes': b['db_minutes'], 'program': b['db_program'],
                                           'program_name': b['program_name'], 'action': b['db_action'],
                                           'text': b['db_text']} for b in p['blocks']]} for p in _dayplans()])

    @api.route('/budgets')
    @auth_required
    def api_budgets():
        if not lb.budgets.enabled:
            return jsonify(ok=True, enabled=False, budgets=[])
        c = lb.budgets.ceiling()
        return jsonify(ok=True, enabled=True,
                       keys={k: {'name': v[0], 'desc': v[1]} for k, v in budgetsmod.KEYS.items()},
                       ceiling={'key': c.key, 'period': c.period, 'max_count': c.max_count,
                                'min_gap_s': c.min_gap_s, 'on_gap': c.on_gap, 'source': c.source},
                       budgets=[{'id': r['bu_id'], 'key': r['bu_key'], 'slave': r['bu_slave'] or None,
                                 'period': r['bu_period'], 'max_count': r['bu_max_count'],
                                 'min_gap_s': r['bu_min_gap_s'], 'on_gap': r['bu_on_gap'],
                                 'enabled': bool(r['bu_enabled']), 'note': r['bu_note'], 'by': r['bu_by']}
                                for r in _budget_rows()])

    @api.route('/budgets', methods=['POST'])
    @auth_required
    def api_budgets_post():
        if not lb.budgets.enabled:
            return err('Budgets nicht verfügbar (Migration 005 fehlt)', 409)
        row, bad = _budget_form(body(), api_user())
        if bad:
            return err(bad)
        _budget_save(row)
        audit.web('budget_set', api_user(), data=row)
        r = q('SELECT bu_id FROM budgets WHERE bu_key=%s AND bu_slave=%s AND bu_period=%s',
              (row['key'], row['slave'], row['period']), one=True)
        return jsonify(ok=True, id=r['bu_id'] if r else None), 201

    @api.route('/budgets/<int:bid>', methods=['DELETE'])
    @auth_required
    def api_budget_delete(bid):
        if not q('SELECT bu_id FROM budgets WHERE bu_id=%s', (bid,), one=True):
            return err('nicht gefunden', 404)
        x('DELETE FROM budgets WHERE bu_id=%s', (bid,))
        ctx.db().commit()
        lb.budgets.invalidate()
        ctx.mq.notify_reload('logbook')
        audit.web('budget_delete', api_user(), data={'id': bid})
        return jsonify(ok=True)

    @api.route('/pauses')
    @auth_required
    def api_pauses():
        if not lb.pauses.enabled:
            return jsonify(ok=True, enabled=False, pauses=[])
        return jsonify(ok=True, enabled=True,
                       pauses=[{'id': r['pa_id'], 'slave': r['pa_slave'] or None, 'from': str(r['pa_from']),
                                'to': str(r['pa_to']), 'reason': r['pa_reason'], 'by': r['pa_by'], 'state': r['state']}
                               for r in _pause_rows(include_past=bool(request.args.get('all')))])

    @api.route('/pauses', methods=['POST'])
    @auth_required
    def api_pauses_post():
        if not lb.pauses.enabled:
            return err('Pausen nicht verfügbar (Migration 006 fehlt)', 409)
        row, bad = _pause_form(body(), api_user())
        if bad:
            return err(bad)
        pid = _pause_save(row)
        audit.web('pause_add', api_user(), slave_id=row['slave'] or None,
                  data={'id': pid, 'from': str(row['from']), 'to': str(row['to']), 'reason': row['reason']})
        return jsonify(ok=True, id=pid), 201

    @api.route('/pauses/<int:pid>', methods=['DELETE'])
    @auth_required
    def api_pause_delete(pid):
        r = q('SELECT * FROM pauses WHERE pa_id=%s', (pid,), one=True)
        if not r:
            return err('nicht gefunden', 404)
        x('DELETE FROM pauses WHERE pa_id=%s', (pid,))
        ctx.db().commit()
        lb.pauses.invalidate()
        ctx.mq.notify_reload('logbook', r['pa_slave'] or None)
        audit.web('pause_delete', api_user(), slave_id=r['pa_slave'] or None, data={'id': pid})
        return jsonify(ok=True)

    @api.route('/streaks')
    @auth_required
    def api_streaks():
        if not lb.streaks.enabled:
            return jsonify(ok=True, enabled=False, streaks=[])
        return jsonify(ok=True, enabled=True,
                       kinds={k: {'name': v[0], 'desc': v[1]} for k, v in streaksmod.KINDS.items()},
                       streaks=[{'id': r['st_id'], 'key': r['st_key'], 'name': r['st_name'], 'kind': r['st_kind'],
                                 'action': r['st_action'], 'milestones': streaksmod.parse_milestones(r['st_milestones']),
                                 'enabled': bool(r['st_enabled']), 'running': int(r['running'] or 0),
                                 'best': int(r['best'] or 0), 'by': r['st_by']} for r in _streak_rows()])

    @api.route('/streaks', methods=['POST'])
    @auth_required
    def api_streaks_post():
        if not lb.streaks.enabled:
            return err('Serien nicht verfügbar (Migration 007 fehlt)', 409)
        row, bad = _streak_form(body(), api_user())
        if bad:
            return err(bad)
        _streak_save(row)
        audit.web('streak_set', api_user(), data=row)
        r = q('SELECT st_id FROM streaks WHERE st_key=%s', (row['key'],), one=True)
        return jsonify(ok=True, id=r['st_id'] if r else None), 201

    @api.route('/streaks/<int:sid>', methods=['DELETE'])
    @auth_required
    def api_streak_delete(sid):
        r = q('SELECT st_key FROM streaks WHERE st_id=%s', (sid,), one=True)
        if not r:
            return err('nicht gefunden', 404)
        x('DELETE FROM streaks WHERE st_id=%s', (sid,))
        ctx.db().commit()
        lb.streaks.invalidate()
        ctx.mq.notify_reload('logbook')
        audit.web('streak_delete', api_user(), data={'id': sid, 'key': r['st_key']})
        return jsonify(ok=True)

    @api.route('/slaves/<int:sid>/dayform', methods=['GET', 'PUT'])
    @auth_required
    def api_slave_dayform(sid):
        if not lb.dayform.enabled:
            return err('Tagesform nicht verfügbar (Migration 009 fehlt)', 409)
        if request.method == 'GET':
            return jsonify(ok=True, forms=list(dayformmod.FORMS), **lb.dayform.info(sid))
        j = body()
        form = str(j.get('form', 'normal'))
        if form not in dayformmod.FORMS:
            return err('form: easy|normal|strict')
        day = datetime.date.today() + datetime.timedelta(days=1 if j.get('tomorrow') else 0)
        lb.dayform.set(sid, form, api_user(), reason=str(j.get('reason') or '')[:160], day=day)
        audit.web('dayform_set', api_user(), slave_id=sid, data={'form': form, 'day': day.isoformat(), 'reason': j.get('reason')})
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(ok=True, form=form, day=day.isoformat())

    @api.route('/scenarios')
    @auth_required
    def api_scenarios():
        if not lb.scenarios.enabled:
            return jsonify(ok=True, enabled=False, scenarios=[])
        return jsonify(ok=True, enabled=True,
                       scenarios=[{'id': r['sn_id'], 'name': r['sn_name'], 'note': r['sn_note'], 'day_plan': r['sn_day_plan'],
                                   'plan_name': r['plan_name'], 'dayform': r['sn_dayform'], 'sanctions': r['sanctions'],
                                   'budgets': r['budgets'], 'active_n': int(r['active_n'] or 0)} for r in lb.scenarios.list()])

    @api.route('/scenarios', methods=['POST'])
    @auth_required
    def api_scenarios_post():
        if not lb.scenarios.enabled:
            return err('Szenarien nicht verfügbar (Migration 011 fehlt)', 409)
        row, bad = _scenario_form(body(), api_user())
        if bad:
            return err(bad)
        if q('SELECT sn_id FROM scenarios WHERE sn_name=%s', (row['name'],), one=True):
            return err('Name vergeben', 409)
        sn_id = lb.scenarios.save(row['name'], row['note'], row['day_plan'], row['dayform'], row['sanctions'], row['budgets'], api_user())
        ctx.db().commit()
        audit.web('scenario_save', api_user(), data=dict(row, id=sn_id))
        return jsonify(ok=True, id=sn_id), 201

    @api.route('/scenarios/<int:sn_id>', methods=['DELETE'])
    @auth_required
    def api_scenario_delete(sn_id):
        if not lb.scenarios.get(sn_id):
            return err('nicht gefunden', 404)
        lb.scenarios.delete(sn_id, api_user())
        ctx.db().commit()
        ctx.mq.notify_reload('logbook')
        audit.web('scenario_delete', api_user(), data={'id': sn_id})
        return jsonify(ok=True)

    @api.route('/slaves/<int:sid>/scenario', methods=['GET', 'PUT', 'DELETE'])
    @auth_required
    def api_slave_scenario(sid):
        if not lb.scenarios.enabled:
            return err('Szenarien nicht verfügbar (Migration 011 fehlt)', 409)
        if request.method == 'GET':
            return jsonify(ok=True, scenario=lb.scenarios.info(sid))
        if request.method == 'DELETE':
            lb.scenarios.deactivate(sid, api_user(), 'ended by api')
            ctx.db().commit()
            ctx.mq.notify_reload('logbook', sid)
            return jsonify(ok=True)
        j = body()
        try:
            until = datetime.date.fromisoformat(str(j.get('until') or ''))
        except ValueError:
            return err('until: YYYY-MM-DD')
        ok, why = lb.scenarios.activate(sid, int(j.get('scenario') or 0), until, api_user())
        ctx.db().commit()
        if not ok:
            return err(why)
        audit.web('scenario_activate', api_user(), slave_id=sid, data={'scenario': j.get('scenario'), 'until': until.isoformat()})
        ctx.mq.notify_reload('logbook', sid)
        return jsonify(ok=True, scenario=lb.scenarios.info(sid))

    @api.route('/rules')
    @auth_required
    def api_rules():
        if not lb.day_enabled:
            return jsonify(ok=True, enabled=False, rules=[])
        # The KEYS to the effects that need one.
        #
        # Up to here the enquiry returned only the effects with a sentence of
        # running text beside them ("key, optionally :hours, ..."). Whoever
        # creates a rule over the API could build no selection out of that and
        # could check no key up front — he had to guess and learn from the
        # error. The web interface had these lists long since; the API did not,
        # and that was not a design but an oversight (finding 2026-09-14).
        #
        # `param_keys` says, per effect, WHICH list belongs to it. That way the
        # caller need not know the mapping himself and it stays in one place
        # when an effect is added.
        keys = {'sanctions': {k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.SANCTIONS.items()},
                'privileges': {k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.PRIVILEGES.items()},
                'badges': {k: {'name': v[0], 'desc': v[1]} for k, v in lbmod.BADGES.items()}}
        param_keys = {'sanction_impose': 'sanctions', 'sanction_lift': 'sanctions',
                      'privilege_grant': 'privileges', 'privilege_revoke': 'privileges',
                      'badge': 'badges'}
        return jsonify(ok=True, enabled=True,
                       triggers=lbmod.Logbook.TRIGGERS, conditions=lb.conditions(),
                       time_conditions=lbmod.Logbook.TIME_CONDITIONS,
                       effects={k: {'name': v[0], 'param': v[1], 'keys': param_keys.get(k)}
                                for k, v in lbmod.Logbook.EFFECTS.items()},
                       keys=keys,
                       rules=[{'id': r['ru_id'], 'trigger': r['ru_trigger'], 'cond': r['ru_cond'],
                               'effect': r['ru_effect'], 'param': r['ru_param'], 'note': r['ru_note'],
                               'enabled': bool(r['ru_enabled']), 'pos': r['ru_pos'], 'by': r['ru_by']}
                              for r in lb.rules()])

    @api.route('/rules', methods=['POST'])
    @auth_required
    def api_rules_post():
        if not lb.day_enabled:
            return err('Regelwerk nicht verfügbar (Migration 007 fehlt)', 409)
        j = body()
        trig, cond = str(j.get('trigger', '')), str(j.get('cond', '') or '')
        eff, param = str(j.get('effect', '')), str(j.get('param', '') or '')[:64]
        if trig not in lbmod.Logbook.TRIGGERS:
            return err('trigger: ' + '|'.join(lbmod.Logbook.TRIGGERS))
        if eff not in lbmod.Logbook.EFFECTS:
            return err('effect: ' + '|'.join(lbmod.Logbook.EFFECTS))
        if not lb.valid_cond(cond):
            return err('cond: ' + '|'.join(k for k in lb.conditions() if k) + ' — optionally &' +
                       '|'.join(k for k in lbmod.Logbook.TIME_CONDITIONS if k))
        # The same lock as on the page (doc 58 §8) — otherwise the API would be
        # the back door through which dead rules keep coming into the table.
        if not lbmod.Logbook.cond_fits(trig, cond):
            return err("cond: '%s' can never match trigger '%s' — possible here: %s"
                       % (cond, trig, '|'.join(k or '(always)' for k in lb.conditions()
                                               if lbmod.Logbook.cond_fits(trig, k))))
        bad = _rule_param_error(eff, param)
        if bad:
            return err(bad)
        rid = x('INSERT INTO rules (ru_trigger, ru_cond, ru_effect, ru_param, ru_note, ru_pos, ru_by) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE ru_enabled=1, ru_note=VALUES(ru_note), '
                'ru_pos=VALUES(ru_pos), ru_by=VALUES(ru_by)',
                (trig, cond, eff, param, str(j.get('note') or '')[:255] or None,
                 max(0, min(999, int(j.get('pos') or 50))), api_user()))
        ctx.db().commit()
        audit.web('rule_add', api_user(), data={'trigger': trig, 'cond': cond, 'effect': eff, 'param': param})
        ctx.mq.notify_reload('logbook')
        return jsonify(ok=True, id=rid), 201

    @api.route('/rules/<int:rid>', methods=['PUT', 'DELETE'])
    @auth_required
    def api_rule_put(rid):
        if not q('SELECT ru_id FROM rules WHERE ru_id=%s', (rid,), one=True):
            return err('nicht gefunden', 404)
        if request.method == 'DELETE':
            x('DELETE FROM rules WHERE ru_id=%s', (rid,))
        else:
            j = body()
            x('UPDATE rules SET ru_enabled=%s, ru_pos=%s, ru_note=%s, ru_by=%s WHERE ru_id=%s',
              (1 if j.get('enabled', True) else 0, max(0, min(999, int(j.get('pos') or 50))),
               str(j.get('note') or '')[:255] or None, api_user(), rid))
        ctx.db().commit()
        audit.web('rule_' + request.method.lower(), api_user(), data={'id': rid})
        ctx.mq.notify_reload('logbook')
        return jsonify(ok=True)

    @api.route('/slaves/<int:sid>/settings', methods=['GET', 'PUT'])
    @auth_required
    def api_slave_settings(sid):
        if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
            return err('nicht gefunden', 404)
        if not lb.day_enabled:
            return jsonify(ok=True, enabled=False)
        if request.method == 'PUT':
            j = body()
            plan = int(j.get('day_plan') or 0) or None
            if plan and not q('SELECT dp_id FROM day_plans WHERE dp_id=%s', (plan,), one=True):
                return err('day_plan: unbekannt')
            hard = int(lb.limits['day_minutes_max'])
            minutes = max(15, min(hard, int(j.get('day_minutes') or lb.limits['day_minutes_default'])))
            relogin = 1 if j.get('relogin') else 0
            x('INSERT INTO slave_settings (ss_slave, ss_day_plan, ss_day_minutes, ss_relogin, ss_by) VALUES (%s,%s,%s,%s,%s) '
              'ON DUPLICATE KEY UPDATE ss_day_plan=VALUES(ss_day_plan), ss_day_minutes=VALUES(ss_day_minutes), '
              'ss_relogin=VALUES(ss_relogin), ss_by=VALUES(ss_by)', (sid, plan, minutes, relogin, api_user()))
            ctx.db().commit()
            audit.web('slave_settings', api_user(), slave_id=sid,
                      data={'day_plan': plan, 'day_minutes': minutes, 'relogin': relogin})
            ctx.mq.notify_reload('logbook', sid)
        r = q('SELECT * FROM slave_settings WHERE ss_slave=%s', (sid,), one=True)
        d = q('SELECT * FROM day_sessions WHERE ds_slave=%s ORDER BY ds_day DESC LIMIT 1', (sid,), one=True)
        return jsonify(ok=True, enabled=True, settings={
            'day_plan': r['ss_day_plan'] if r else None,
            'day_minutes': lb.day_minutes(sid), 'relogin': bool(r['ss_relogin']) if r else False,
            'day_minutes_max': int(lb.limits['day_minutes_max'])},
            day=None if not d else {'day': str(d['ds_day']), 'status': d['ds_status'], 'pos': d['ds_pos'],
                                    'block': d['ds_block_kind'], 'text': d['ds_block_text'],
                                    'planned_end': str(d['ds_planned_end']), 'tasks': d['ds_tasks'],
                                    'train_s': d['ds_train_s'], 'free_s': d['ds_free_s']})

    @api.route('/zeugnis/<int:sid>/<week>')
    @auth_required
    def api_zeugnis(sid, week):
        rev = q('SELECT * FROM weekly_review WHERE wr_slave=%s AND wr_week=%s', (sid, week), one=True)
        if not rev:
            return err('keine Bewertung für diese Woche', 404)
        rev = {k: (str(v) if isinstance(v, (datetime.datetime, datetime.date)) else v) for k, v in rev.items()}
        return jsonify(ok=True, review=rev, runs=[run_json(r) for r in runs('a.ach_slave=%s AND a.ach_week=%s', (sid, week), 200)],
                       tasks=[task_json(t) for t in weekly(sid, week)], rank_name_after=lb.rank_name(rev['wr_rank_after']))

    @api.route('/zeugnis/<int:sid>/<week>/remark', methods=['PUT'])
    @auth_required
    def api_zeugnis_remark(sid, week):
        x('UPDATE weekly_review SET wr_remark=%s WHERE wr_slave=%s AND wr_week=%s', (str(body().get('remark', ''))[:500], sid, week))
        ctx.db().commit()
        audit.web('review_remark', api_user(), slave_id=sid, data={'week': week})
        return jsonify(ok=True)

    @api.route('/export')
    @auth_required
    def api_export():
        data = _export_zip(q, ctx.config)
        audit.web('export', api_user(), data={'bytes': len(data)})
        return Response(data, mimetype='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="punisher_export_{datetime.date.today().isoformat()}.zip"'})

    app.register_blueprint(pages)
    app.register_blueprint(api)


class _MqAdapter:
    def __init__(self, mq, user):
        self.mq, self.user = mq, user

    def send_command(self, device, action, args=None, ttl_ms=5000):
        return self.mq.send_command(device, action, args, ttl_ms, user=self.user)

    def emergency(self, device=None):
        self.mq.emergency(user=self.user, device=device)


# ---------------------------------------------------------------------- #
def _export_zip(q, config):
    """Pseudonymised export (CSV) for the content team: runs, weekly reviews,
    weekly plans, ranks, badges — slaves as stable pseudonyms, without names,
    RFID, photos. Salt: [web] export_salt (otherwise the web secret)."""
    salt = config['web'].get('export_salt') or config['web'].get('secret') or 'punisher'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        def table(name, sql, cols, pseud_col):
            out = io.StringIO()
            w = csv.writer(out, delimiter=';')
            w.writerow(cols)
            for r in q(sql):
                row = []
                for c in cols:
                    v = r.get(c)
                    if c == pseud_col:
                        v = _pseudonym(v, salt)
                    row.append(v if v is not None else '')
                w.writerow(row)
            z.writestr(name, out.getvalue())
        table('achievements.csv',
              'SELECT ach_id, ach_slave, ach_action, ach_level, ach_week, ach_day, ach_started, ach_ended, ach_duration_s, ach_target, '
              'ach_target_unit, ach_max_punish, ach_punish, ach_warn, ach_metrics, ach_grade, ach_points, ach_counted, ach_best, ach_status FROM achievements ORDER BY ach_id',
              ['ach_id', 'ach_slave', 'ach_action', 'ach_level', 'ach_week', 'ach_day', 'ach_started', 'ach_ended', 'ach_duration_s', 'ach_target',
               'ach_target_unit', 'ach_max_punish', 'ach_punish', 'ach_warn', 'ach_metrics', 'ach_grade', 'ach_points', 'ach_counted', 'ach_best', 'ach_status'],
              'ach_slave')
        table('weekly_review.csv',
              'SELECT wr_slave, wr_week, wr_runs, wr_tasks_passed, wr_best_count, wr_plan_total, wr_plan_done, wr_plan_complete, wr_trained, '
              'wr_punish, wr_score, wr_place, wr_rank_before, wr_rank_after, wr_reason, wr_grades, '
              'wr_sanctions, wr_sanctions_open FROM weekly_review ORDER BY wr_week, wr_slave',
              ['wr_slave', 'wr_week', 'wr_runs', 'wr_tasks_passed', 'wr_best_count', 'wr_plan_total', 'wr_plan_done', 'wr_plan_complete', 'wr_trained',
               'wr_punish', 'wr_score', 'wr_place', 'wr_rank_before', 'wr_rank_after', 'wr_reason', 'wr_grades',
               'wr_sanctions', 'wr_sanctions_open'], 'wr_slave')
        table('weekly_tasks.csv',
              'SELECT wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_created FROM weekly_tasks ORDER BY wt_id',
              ['wt_slave', 'wt_week', 'wt_action', 'wt_target', 'wt_max_punish', 'wt_kind', 'wt_status', 'wt_created'], 'wt_slave')
        table('slave_rank.csv', 'SELECT sr_slave, sr_rank, sr_frozen, sr_updated FROM slave_rank',
              ['sr_slave', 'sr_rank', 'sr_frozen', 'sr_updated'], 'sr_slave')
        table('badges.csv', 'SELECT bd_slave, bd_key, bd_earned FROM badges ORDER BY bd_id', ['bd_slave', 'bd_key', 'bd_earned'], 'bd_slave')
        table('slave_levels.csv', 'SELECT sl_slave, sl_action, sl_level, sl_updated FROM slave_levels',
              ['sl_slave', 'sl_action', 'sl_level', 'sl_updated'], 'sl_slave')
        z.writestr('README.txt', 'Punisher — pseudonymisierter Export für das Inhaltsteam\n'
                   f'Erzeugt: {datetime.datetime.now().isoformat(timespec="seconds")}\n'
                   'Sklaven erscheinen als stabile Pseudonyme (T + 8 Hex). Keine Namen, keine RFID, keine Fotos.\n'
                   'Noten A-F, Punkte nach scoring, Wochen als ISO-Woche (YYYY-Www). Trennzeichen ;\n')
    return buf.getvalue()


def _zeugnis_pdf(d):
    """Weekly report card as PDF (reportlab); None when reportlab is missing."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        return None
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    rev = d['rev'] or {}
    y = H - 25 * mm
    c.setFont('Helvetica-Bold', 22)
    c.drawString(20 * mm, y, 'ZEUGNIS')
    c.setFont('Helvetica', 11)
    c.drawRightString(W - 20 * mm, y, f"Woche {d['week']}  ({d['monday'].strftime('%d.%m.')} – {d['sunday'].strftime('%d.%m.%Y')})")
    y -= 14 * mm
    c.setFont('Helvetica-Bold', 16)
    c.drawString(20 * mm, y, d['slave']['slave_name'])
    y -= 10 * mm
    c.setFont('Helvetica', 11)
    if rev:
        rn = d['rank_names']
        lines = [
            # only characters out of WinAnsi (standard font Helvetica): no arrow/en dash
            f"Rang: {rn.get(rev['wr_rank_before'], rev['wr_rank_before'])} -> {rn.get(rev['wr_rank_after'], rev['wr_rank_after'])}   ({str(rev.get('wr_reason') or '').replace('≥', '>=').replace('—', '-')})",
            f"Wochenpunkte: {rev['wr_score']}   Platz: {rev['wr_place'] or '-'}",
            f"Durchgänge: {rev['wr_runs']}   bestandene Aufgaben: {rev['wr_tasks_passed']}   Wochenbester: {rev['wr_best_count']}×",
            f"Wochenplan: {rev['wr_plan_done']} von {rev['wr_plan_total']}   Bestrafungen: {rev['wr_punish']}",
            f"Noten: {rev.get('wr_grades') or '-'}",
            # Sanctions of the week: display, no scoring. Deliberately stands
            # BELOW the points, so that nobody takes them for a deduction.
            f"Auflagen: {rev.get('wr_sanctions') or '-'}"
            + (f"   ({rev['wr_sanctions_open']} noch offen)" if rev.get('wr_sanctions_open') else '')
            + '   (ohne Einfluss auf die Wochenpunkte)',
        ]
        for ln in lines:
            c.drawString(20 * mm, y, ln)
            y -= 7 * mm
    else:
        c.drawString(20 * mm, y, 'Für diese Woche liegt noch keine Bewertung vor.')
        y -= 7 * mm
    y -= 4 * mm
    c.setFont('Helvetica-Bold', 12)
    c.drawString(20 * mm, y, 'Durchgänge')
    y -= 7 * mm
    c.setFont('Helvetica', 9.5)
    for r in d['rows']:
        if y < 40 * mm:
            c.showPage(); y = H - 25 * mm; c.setFont('Helvetica', 9.5)
        name = actions.get(r['ach_action']).name if actions.get(r['ach_action']) else r['ach_action']
        c.drawString(20 * mm, y, f"{str(r['ach_started'])[:16]}  {name}")
        c.drawString(105 * mm, y, f"Stufe {r['ach_level']}  Ziel {lbmod.Logbook.target_text(r['ach_target'], r['ach_target_unit'])}")
        c.drawString(150 * mm, y, f"Note {r['ach_grade'] or '-'}  {r['ach_points']} P  Strafen {r['ach_punish']}")
        y -= 5.5 * mm
    y -= 6 * mm
    c.setFont('Helvetica-Bold', 12)
    c.drawString(20 * mm, y, 'Wochenplan')
    y -= 7 * mm
    c.setFont('Helvetica', 9.5)
    for t in d['tasks']:
        if y < 40 * mm:
            c.showPage(); y = H - 25 * mm; c.setFont('Helvetica', 9.5)
        name = actions.get(t['wt_action']).name if actions.get(t['wt_action']) else t['wt_action']
        c.drawString(20 * mm, y, f"[{'x' if t['wt_status'] == 'done' else ' '}] {name}  {lbmod.Logbook.target_text(t['wt_target'], t['unit'])}  ({t['wt_kind']}, {t['wt_status']})")
        y -= 5.5 * mm
    if rev and rev.get('wr_remark'):
        y -= 6 * mm
        c.setFont('Helvetica-Bold', 12)
        c.drawString(20 * mm, y, 'Bemerkung der Aufsicht')
        y -= 7 * mm
        c.setFont('Helvetica-Oblique', 10.5)
        for ln in str(rev['wr_remark']).split('\n'):
            if y < 30 * mm:
                c.showPage(); y = H - 25 * mm; c.setFont('Helvetica-Oblique', 10.5)
            c.drawString(20 * mm, y, ln[:110]); y -= 6 * mm
    c.setFont('Helvetica', 8)
    c.drawString(20 * mm, 15 * mm, 'Punisher · Devious City · automatisch erzeugt aus dem Logbuch')
    c.showPage()
    c.save()
    return buf.getvalue()
