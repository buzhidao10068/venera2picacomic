# -*- coding: utf-8 -*-
"""Convert a Venera export (.venera) into a PicaComic backup (.picadata).

Venera and PicaComic share an ancestor, so the databases are close but not
identical:
  * history table PK column is `id` in Venera, `target` in PicaComic, and
    Venera adds a `chapter_group` column PicaComic does not have.
  * favourite folder tables use `id` vs `target`, and Venera adds
    `translated_tags`.
  * the numeric comic `type`: Venera always uses `sourceKey.hashCode`,
    PicaComic uses fixed small values for its built-in sources and
    `sourceKey.hashCode` only for JS sources -- and its two enums disagree,
    so history and favourites need different tables (see below).
  * archive entry names: `appdata.json`/`cookie.db` vs `appdata`/`cookies.db`.
"""
import json, os, shutil, sqlite3, sys, tempfile, zipfile

# Venera sourceKey.hashCode -> PicaComic built-in type value.
# HistoryType and FavoriteType agree up to htmanga and then diverge:
# FavoriteType resolves through `ComicType.values[key]`, whose index 5 is
# `htFavorite`, so nhentai favourites are 6. Writing 5 there would label the
# row htFavorite and make `ComicSource.find("htfavorite")!` throw the moment
# anything dereferences the source (opening the comic, checking for updates).
HISTORY_TYPE = {
    553570794: 0,  # picacg
    385625716: 1,  # ehentai
    769844263: 2,  # jm
    258019538: 3,  # hitomi
    823512256: 4,  # wnacg -> htmanga
    264196719: 5,  # nhentai      (HistoryType.nhentai == 5)
}
FAVORITE_TYPE = dict(HISTORY_TYPE)
FAVORITE_TYPE[264196719] = 6  # nhentai      (FavoriteType.nhentai == 6)
TYPE_NAMES = {553570794: 'picacg', 385625716: 'ehentai', 769844263: 'jm',
              264196719: 'nhentai', 557997769: 'copy_manga',
              981441865: 'ManHuaGui', 577718694: 'manga_dex',
              233488852: 'baozi', 823512256: 'wnacg', 258019538: 'hitomi'}

HISTORY_DDL = """create table history (
  target text primary key, title text, subtitle text, cover text, time int,
  type int, ep int, page int, readEpisode text, max_page int)"""

# PicaComic's history merge runs `select * from image_favorites` on the imported
# db with no try/catch, so the table has to exist even though Venera's version of
# it has a different (per-comic, not per-image) shape and is left empty here.
IMAGE_FAV_DDL = """create table image_favorites (
  id TEXT, title TEXT NOT NULL, cover TEXT NOT NULL, ep INTEGER NOT NULL,
  page INTEGER NOT NULL, other TEXT NOT NULL, PRIMARY KEY (id, ep, page))"""

FOLDER_DDL = """create table {name} (
  target text, name TEXT, author TEXT, type int, tags TEXT, cover_path TEXT,
  time TEXT, last_update_time TEXT DEFAULT NULL,
  has_new_update INTEGER DEFAULT 0, last_check_time INTEGER DEFAULT NULL,
  display_order int, primary key (target, type))"""

# PicaComic's importer requires an `appdata` entry, but Appdata.readDataFromJson
# copies with `for (i = 0; i < settings.length && i < newSettings.length; i++)`,
# so empty lists overwrite nothing at all and the user keeps every setting.
# `settings` and `firstUse` must still be present (both go through
# List<String>.from, which throws on null); the version probe is
# `settings.elementAtOrNull(46) ?? "1"`, so an empty list is safe there too.
APPDATA = {'settings': [], 'firstUse': [], 'blockingKeywords': [], 'favoriteTags': []}


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def fix_url(url):
    """Venera stores some protocol-relative covers; PicaComic can't load those."""
    if isinstance(url, str) and url.startswith('//'):
        return 'https:' + url
    return url


def clean_read_episode(value):
    """PicaComic parses this column with int.parse. Venera writes "group-chapter"
    for sources that have chapter groups, which would abort the whole merge."""
    out = []
    for part in str(value or '').split(','):
        part = part.strip()
        token = part if part.isdigit() else part.rsplit('-', 1)[-1].strip()
        if token.isdigit() and token not in out:
            out.append(token)
    return ','.join(out)


def text(value):
    """PicaComic casts these columns to String without a null check."""
    return '' if value is None else value


def num(value, default=0):
    return default if value is None else value


def convert(src, out, base=None):
    work = tempfile.mkdtemp(prefix='venera2pica_')
    try:
        ven = os.path.join(work, 'in')
        with zipfile.ZipFile(src) as z:
            z.extractall(ven)
        stats = {'unmapped': {}, 'folders': []}

        # ---- history.db -------------------------------------------------
        his_out = os.path.join(work, 'history.db')
        dst = sqlite3.connect(his_out)
        dst.execute(HISTORY_DDL)
        dst.execute(IMAGE_FAV_DDL)
        v = sqlite3.connect(os.path.join(ven, 'history.db'))
        v.row_factory = sqlite3.Row
        rows = 0
        for r in v.execute('select * from history order by time asc'):
            t = r['type']
            mapped = HISTORY_TYPE.get(t)
            if mapped is None:
                mapped = t
                stats['unmapped'][t] = stats['unmapped'].get(t, 0) + 1
            dst.execute('insert or replace into history (target, title, subtitle,'
                        ' cover, time, type, ep, page, readEpisode, max_page)'
                        ' values (?,?,?,?,?,?,?,?,?,?)',
                        (r['id'], text(r['title']), text(r['subtitle']),
                         text(fix_url(r['cover'])), num(r['time']), mapped,
                         num(r['ep']), num(r['page']),
                         clean_read_episode(r['readEpisode']), num(r['max_page'])))
            rows += 1
        v.close()
        dst.commit()
        dst.close()
        stats['history'] = rows

        # ---- local_favorite.db -----------------------------------------
        fav_out = os.path.join(work, 'local_favorite.db')
        dst = sqlite3.connect(fav_out)
        dst.execute('create table folder_sync (folder_name text primary key,'
                    ' time TEXT, key TEXT, sync_data TEXT)')
        dst.execute('create table folder_order (folder_name text primary key,'
                    ' order_value int)')
        v = sqlite3.connect(os.path.join(ven, 'local_favorite.db'))
        v.row_factory = sqlite3.Row
        order = {r[0]: r[1] for r in v.execute('select folder_name, order_value'
                                               ' from folder_order')}
        tables = [r[0] for r in v.execute("select name from sqlite_master"
                                          " where type='table'")]
        folders = [t for t in tables if t not in ('folder_order', 'folder_sync')]
        # Venera leaves folders it never reordered out of folder_order; give them
        # values after the last known one so no two folders collide.
        next_order = max(order.values()) + 1 if order else 0
        resolved = {}
        for folder in folders:
            if folder in order:
                resolved[folder] = order[folder]
            else:
                resolved[folder] = next_order
                next_order += 1
        folders.sort(key=lambda f: resolved[f])
        for folder in folders:
            dst.execute(FOLDER_DDL.format(name=quote(folder)))
            cols = {c[1] for c in v.execute('pragma table_info(%s)' % quote(folder))}
            n = 0
            src_rows = list(v.execute('select * from %s order by display_order asc'
                                      % quote(folder)))
            for r in src_rows:
                t = r['type']
                mapped = FAVORITE_TYPE.get(t)
                if mapped is None:
                    mapped = t
                    stats['unmapped'][t] = stats['unmapped'].get(t, 0) + 1
                n += 1
                dst.execute('insert or replace into %s (target, name, author,'
                            ' type, tags, cover_path, time, last_update_time,'
                            ' has_new_update, last_check_time, display_order)'
                            ' values (?,?,?,?,?,?,?,?,?,?,?)' % quote(folder),
                            (r['id'], text(r['name']), text(r['author']), mapped,
                             text(r['tags']), text(fix_url(r['cover_path'])),
                             text(r['time']),
                             r['last_update_time'] if 'last_update_time' in cols else None,
                             num(r['has_new_update']) if 'has_new_update' in cols else 0,
                             r['last_check_time'] if 'last_check_time' in cols else None,
                             n))
            dst.execute('insert or replace into folder_order (folder_name,'
                        ' order_value) values (?,?)', (folder, resolved[folder]))
            stats['folders'].append((folder, n))
        v.close()
        dst.commit()
        dst.close()

        # ---- pack -------------------------------------------------------
        appdata = json.dumps(APPDATA, ensure_ascii=False)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            if base:
                with zipfile.ZipFile(base) as b:
                    for info in b.infolist():
                        if info.filename in ('local_favorite.db', 'history.db'):
                            continue
                        z.writestr(info, b.read(info.filename))
                    stats['base_appdata'] = 'appdata' in b.namelist()
            else:
                z.writestr('appdata', appdata)
            z.write(fav_out, 'local_favorite.db')
            z.write(his_out, 'history.db')
        return stats
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    src, out = sys.argv[1], sys.argv[2]
    base = sys.argv[3] if len(sys.argv) > 3 else None
    s = convert(src, out, base)
    print('history rows :', s['history'])
    print('folders      :')
    for name, n in s['folders']:
        print('   %-24s %d' % (name, n))
    print('base appdata reused:', s.get('base_appdata', False))
    if s['unmapped']:
        print('kept as JS-source type (needs the matching source installed in PicaComic):')
        for t, n in sorted(s['unmapped'].items(), key=lambda kv: -kv[1]):
            print('   %-12s %-12s %d entries' % (t, TYPE_NAMES.get(t, '?'), n))
    print('written:', out, os.path.getsize(out), 'bytes')
