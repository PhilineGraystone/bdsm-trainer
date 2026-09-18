# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Automatic database migration (decision Philine 2026-09-10).

At start-up the central unit checks the table `schema_migrations` against the files
in `sql/` (NNN_name.sql, NNN < 900; 9xx are test data and are never applied
automatically) and applies the missing migrations one after another. Beforehand —
when `mysqldump` is present — a backup is written to logs/.

Configuration ([database] in config/config.ini, all optional):
  auto_migrate          = 1   apply missing migrations at start-up (0 = only check/warn)
  backup_before_migrate = 1   mysqldump before applying (logs/db-backup-*.sql.gz: timestamp,
                              then the version it precedes; see backup())
  require_backup        = 0   1 = without a successful backup, do not migrate

Rules:
  - Every file is executed statement by statement (DDL is not transactional in
    MariaDB). If a statement fails, the migration aborts naming file, statement
    and error; the central unit then does NOT start (half a schema is worse
    than a clear stop). The files are written so that a repeated run after the
    repair carries on (IF NOT EXISTS, INSERT IGNORE).
  - Empty database: everything from 001 on. An existing V1 database without
    `schema_migrations` (table `devices` present): 001 counts as applied.
  - Only the central unit migrates. The web side only checks (`pending()`) and shows a
    note when the database is behind the code.

Calling by hand (update without starting the central unit, from the program directory):
  python3 libs/dbmigrate.py            # apply
  python3 libs/dbmigrate.py --dry-run  # only show what is missing
"""

import datetime
import gzip
import logging
import os
import re
import shutil
import subprocess
import sys

import pymysql

logger = logging.getLogger('Punisher')

FILE_RE = re.compile(r'^(\d{3})_[^/\\]+\.sql$')
TESTDATA_FROM = '900'          # from here on: test data, never automatic


class MigrationError(Exception):
    pass


# --------------------------------------------------------------------------- #
def split_statements(text):
    """Split SQL text into statements: drop '--' comments, split at ';' outside
    of quotes. Good enough for the migration files (no DELIMITER)."""
    out, buf = [], []
    in_str = None
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_str:
            buf.append(ch)
            if ch == '\\' and i + 1 < n:
                buf.append(text[i + 1]); i += 2; continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('\'', '"', '`'):
            in_str = ch; buf.append(ch); i += 1; continue
        if ch == '-' and text.startswith('--', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if ch == '#':
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if ch == '/' and text.startswith('/*', i):
            j = text.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch == ';':
            stmt = ''.join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    stmt = ''.join(buf).strip()
    if stmt:
        out.append(stmt)
    return out


def available(sql_dir):
    """[(version, path)] of the migration files (< 900), sorted by version."""
    if not os.path.isdir(sql_dir):
        return []
    files = []
    for name in os.listdir(sql_dir):
        m = FILE_RE.match(name)
        if m and m.group(1) < TESTDATA_FROM:
            files.append((m.group(1), os.path.join(sql_dir, name)))
    files.sort()
    versions = [v for v, _ in files]
    dups = {v for v in versions if versions.count(v) > 1}
    if dups:
        raise MigrationError(f'mehrdeutige Migrationsnummern in {sql_dir}: {sorted(dups)}')
    return files


def _table_exists(cur, name):
    cur.execute('SHOW TABLES LIKE %s', (name,))
    return cur.fetchone() is not None


def applied(cur):
    """Set of applied versions; creates schema_migrations with '001' on a
    V1 database (tables there, the record missing)."""
    if not _table_exists(cur, 'schema_migrations'):
        if _table_exists(cur, 'devices'):
            cur.execute('CREATE TABLE IF NOT EXISTS schema_migrations ('
                        ' version varchar(32) NOT NULL, applied_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,'
                        ' PRIMARY KEY (version)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci')
            cur.execute("INSERT IGNORE INTO schema_migrations (version) VALUES ('001')")
            logger.warning('dbmigrate: V1-Datenbank ohne schema_migrations - 001 als eingespielt vermerkt')
            return {'001'}
        return set()
    cur.execute('SELECT version FROM schema_migrations')
    return {str(r[0] if not isinstance(r, dict) else r['version']) for r in cur.fetchall()}


def pending(cur, sql_dir):
    """[(version, path)] of the migrations still missing."""
    done = applied(cur)
    return [(v, p) for v, p in available(sql_dir) if v not in done]


# --------------------------------------------------------------------------- #
def backup(db_cfg, log_dir, tag):
    """mysqldump into <log_dir>, file name db-backup-*.sql.gz: timestamp, then the
    <tag> it precedes (assembled below, the German infix kept so older backups stay
    findable). Returns the path or None (mysqldump missing / failed; the reason goes
    to the log)."""
    exe = shutil.which('mysqldump') or shutil.which('mariadb-dump')
    if not exe:
        logger.warning('dbmigrate: mysqldump nicht gefunden - keine Sicherung vor der Migration')
        return None
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    path = os.path.join(log_dir, f'db-backup-{stamp}-vor-{tag}.sql.gz')
    cmd = [exe, '-h', db_cfg['hostname'], '-u', db_cfg['username'], '--single-transaction', '--routines',
           '--default-character-set=utf8mb4', db_cfg['database']]
    if db_cfg.get('port'):
        cmd[1:1] = ['-P', str(db_cfg['port'])]
    env = dict(os.environ, MYSQL_PWD=db_cfg['password'])
    try:
        with gzip.open(path, 'wb') as f:
            proc = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.PIPE, timeout=600, check=False)
        if proc.returncode != 0:
            logger.error('dbmigrate: Sicherung fehlgeschlagen (rc=%d): %s', proc.returncode,
                         proc.stderr.decode('utf-8', 'replace').strip()[:300])
            try:
                os.remove(path)
            except OSError:
                pass
            return None
    except (OSError, subprocess.SubprocessError) as e:
        logger.error('dbmigrate: Sicherung fehlgeschlagen: %s', e)
        return None
    logger.info('dbmigrate: Sicherung geschrieben: %s (%d Bytes)', path, os.path.getsize(path))
    return path


def apply_file(cur, version, path):
    """Apply one migration file; MigrationError naming file/statement on errors."""
    with open(path, encoding='utf-8') as f:
        text = f.read()
    stmts = split_statements(text)
    logger.info('dbmigrate: %s (%s) - %d Anweisungen', version, os.path.basename(path), len(stmts))
    for k, stmt in enumerate(stmts, 1):
        try:
            cur.execute(stmt)
        except pymysql.Error as e:
            head = ' '.join(stmt.split())[:160]
            raise MigrationError(f'Migration {version} ({os.path.basename(path)}), Anweisung {k}/{len(stmts)} '
                                 f'fehlgeschlagen: {e} -- {head}') from e
    # safety net in case a file does not record its own version
    cur.execute('INSERT IGNORE INTO schema_migrations (version) VALUES (%s)', (version,))


def run(db_cfg, sql_dir, log_dir='logs', auto=True, do_backup=True, require_backup=False, dry_run=False):
    """Check and (auto) apply. Returns dict {applied: [...], pending: [...], backup: path|None}.
    MigrationError on errors -> the central unit must not start."""
    conn = pymysql.connect(host=db_cfg['hostname'], user=db_cfg['username'], password=db_cfg['password'],
                           database=db_cfg['database'], port=int(db_cfg.get('port') or 3306),
                           autocommit=True, charset='utf8mb4')
    result = {'applied': [], 'pending': [], 'backup': None}
    try:
        with conn.cursor() as cur:
            todo = pending(cur, sql_dir)
            result['pending'] = [v for v, _ in todo]
            if not todo:
                logger.info('dbmigrate: Datenbank aktuell (%d Migrationen)', len(available(sql_dir)))
                return result
            names = ', '.join(v for v, _ in todo)
            if dry_run or not auto:
                logger.warning('dbmigrate: fehlende Migrationen: %s (%s)', names,
                               'dry-run' if dry_run else 'auto_migrate=0 - von Hand einspielen')
                return result
            logger.warning('dbmigrate: spiele fehlende Migrationen ein: %s', names)
            if do_backup:
                result['backup'] = backup(db_cfg, log_dir, todo[0][0])
                if result['backup'] is None and require_backup:
                    raise MigrationError('keine Sicherung möglich und require_backup=1 - Migration nicht ausgeführt')
            for v, p in todo:
                apply_file(cur, v, p)
                result['applied'].append(v)
                result['pending'].remove(v)
            logger.info('dbmigrate: eingespielt: %s', ', '.join(result['applied']))
            return result
    finally:
        conn.close()


def config_flags(db_section):
    """(auto, backup, require_backup) from the [database] section (ConfigParser section or dict)."""
    def flag(key, default):
        v = db_section.get(key, default) if hasattr(db_section, 'get') else default
        return str(v).strip().lower() not in ('0', 'false', 'no', 'nein', 'off', '')
    return flag('auto_migrate', '1'), flag('backup_before_migrate', '1'), flag('require_backup', '0')


# --------------------------------------------------------------------------- #
if __name__ == '__main__':
    import argparse
    import configparser
    ap = argparse.ArgumentParser(description='Punisher: Datenbankmigrationen prüfen/einspielen')
    ap.add_argument('--config', default='config/config.ini')
    ap.add_argument('--sql', default='sql')
    ap.add_argument('--dry-run', action='store_true', help='nur anzeigen, was fehlt')
    ap.add_argument('--no-backup', action='store_true')
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)-7s %(message)s')
    cfg = configparser.ConfigParser()
    if not cfg.read(a.config):
        print(f'Konfiguration {a.config} nicht gefunden', file=sys.stderr)
        sys.exit(2)
    try:
        r = run(cfg['database'], a.sql, auto=True, do_backup=not a.no_backup, dry_run=a.dry_run)
    except MigrationError as e:
        print(f'FEHLER: {e}', file=sys.stderr)
        sys.exit(1)
    print('eingespielt:', r['applied'] or '-', '| fehlt noch:', r['pending'] or '-',
          '| Sicherung:', r['backup'] or '-')
