# -*- coding: utf-8 -*-
"""Replay PicaComic's importer against a generated .picadata.

Usage: python simulate_import.py out.picadata

Mirrors Appdata.readDataFromJson(), LocalFavoritesManager.readData() and
HistoryManager.tryUpdateDb() -- same SQL, same column names, same loop bounds,
same int.parse strictness -- against a freshly created PicaComic-shaped
destination database, and resolves every row's comic type the way
FavoriteType.comicSource and HistoryType.name do. A row that would throw when
its source is dereferenced fails here instead of in the app.
"""
import json, os, sqlite3, sys, tempfile, zipfile

# same reason as verify.py: an emoji in a folder name must not crash the report
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(errors='replace')

COMIC_TYPE = ['picacg', 'ehentai', 'jm', 'hitomi', 'htManga', 'htFavorite',
              'nhentai', 'other']
BUILT_IN = {'picacg', 'ehentai', 'jm', 'hitomi', 'htmanga', 'nhentai'}
HISTORY_NAMES = ['picacg', 'ehentai', 'jm', 'hitomi', 'htmanga', 'nhentai']

FOLDER_DDL = ('create table %s(target text, name TEXT, author TEXT, type int,'
              ' tags TEXT, cover_path TEXT, time TEXT, last_update_time TEXT'
              ' DEFAULT NULL, has_new_update INTEGER DEFAULT 0, last_check_time'
              ' INTEGER DEFAULT NULL, display_order int, primary key (target, type))')


def quote(name):
    """Folder names become table names verbatim, and PicaComic's createFolder
    only rejects empty and duplicate names -- so a name may contain a quote."""
    return '"' + name.replace('"', '""') + '"'


tmp = tempfile.mkdtemp()
zipfile.ZipFile(sys.argv[1]).extractall(tmp)

# ---- appdata: Appdata.readDataFromJson --------------------------------------
app = json.loads(open(os.path.join(tmp, 'appdata'), encoding='utf-8').read())
file_version = int((app['settings'][46:47] or ['1'])[0])   # elementAtOrNull(46) ?? "1"
new_settings = list(app['settings'])       # List<String>.from -> throws on null
new_first = list(app['firstUse'])          # ditto
local = ['user-value-%d' % i for i in range(105)]   # pretend a configured install
before = list(local)
saved22, saved13 = local[22], local[13]
for i in range(min(len(local), len(new_settings))):
    local[i] = new_settings[i]
local[22], local[13] = saved22, saved13
assert local == before, 'the import would overwrite user settings'
first, before_first = ['1'] * 5, ['1'] * 5
for i in range(min(len(first), len(new_first))):
    first[i] = new_first[i]
assert first == before_first, 'the import would overwrite firstUse'
print('appdata replayed: fileVersion =', file_version,
      '| user settings untouched:', local == before)

# ---- favourites: LocalFavoritesManager.readData() ---------------------------
dest = sqlite3.connect(os.path.join(tmp, 'dest_fav.db'))
dest.execute('create table folder_sync (folder_name text primary key, time TEXT,'
             ' key TEXT, sync_data TEXT)')
dest.execute('create table folder_order (folder_name text primary key, order_value int)')
src = sqlite3.connect(os.path.join(tmp, 'local_favorite.db'))
src.row_factory = sqlite3.Row
folders = [r['name'] for r in src.execute(
    "SELECT name FROM sqlite_master WHERE type='table';")]
for excluded in ('folder_sync', 'folder_order'):
    folders.remove(excluded)
order = {}
for folder in folders:
    res = src.execute('select * from folder_order where folder_name == ?',
                      (folder,)).fetchall()
    order[folder] = res[0]['order_value'] if res else 0
folders.sort(key=lambda name: order[name])
items = []
for folder in folders:
    for row in src.execute('select * from %s;' % quote(folder)):
        items.append({'folder': folder, 'target': row['target'],
                      'name': str(row['name']), 'author': str(row['author']),
                      'type': int(row['type']),
                      # FavoriteItem.fromRow: (row["tags"] as String).split(",")
                      'tags': [t for t in str(row['tags']).split(',') if t != ''],
                      'coverPath': str(row['cover_path']), 'time': str(row['time'])})
created, added, skips, js_rows = [], 0, 0, 0
for it in items:
    # FavoriteType.comicSource: for key <= 6 it is
    # ComicSource.find(comicType.name.toLowerCase())! -- the ! throws on no match
    key = it['type']
    if 0 <= key <= 6:
        label = COMIC_TYPE[key]
        assert label.lower() in BUILT_IN, (
            'favourite %r has type %d, which resolves to %s; '
            'ComicSource.find("%s")! would throw'
            % (it['target'], key, label, label.lower()))
    else:
        js_rows += 1
    if it['folder'] not in created:
        assert it['folder'] != '', 'createFolder throws on an empty folder name'
        dest.execute(FOLDER_DDL % quote(it['folder']))
        created.append(it['folder'])
    if dest.execute('select * from %s where target == ? and type == ?'
                    % quote(it['folder']), (it['target'], key)).fetchall():
        skips += 1
        continue
    mx = dest.execute('select max(display_order) from %s' % quote(it['folder'])).fetchone()[0]
    dest.execute('insert into %s (target, name, author, type, tags, cover_path,'
                 ' time, display_order) values (?,?,?,?,?,?,?,?)' % quote(it['folder']),
                 (it['target'], it['name'], it['author'], key, ','.join(it['tags']),
                  it['coverPath'], it['time'], (mx or 0) + 1))
    added += 1
dest.commit()
print('favourites merged: %d folders, %d comics added, %d skipped as duplicates,'
      ' %d rows on JS sources' % (len(created), added, skips, js_rows))

# ---- history: HistoryManager.tryUpdateDb() ----------------------------------
hdest = sqlite3.connect(os.path.join(tmp, 'dest_his.db'))
hdest.execute('create table history (target text primary key, title text,'
              ' subtitle text, cover text, time int, type int, ep int, page int,'
              ' readEpisode text, max_page int)')
hsrc = sqlite3.connect(os.path.join(tmp, 'history.db'))
hsrc.row_factory = sqlite3.Row
merged = 0
for row in hsrc.execute('select * from history order by time DESC;'):
    rec = {'type': int(row['type']), 'time': int(row['time']),
           'title': str(row['title']), 'subtitle': str(row['subtitle']),
           'cover': str(row['cover']), 'ep': int(row['ep']),
           'page': int(row['page']), 'target': row['target'],
           # History.fromRow: split(',') then int.parse on each element
           'readEpisode': {int(e) for e in str(row['readEpisode']).split(',') if e != ''},
           'maxPage': int(row['max_page'])}
    assert not 6 <= rec['type'] <= 7, (
        'history row %r has type %d, which HistoryType cannot name'
        % (rec['target'], rec['type']))
    if not hdest.execute('select * from history where target == ?',
                         (rec['target'],)).fetchall():
        hdest.execute('insert into history (target, title, subtitle, cover, time,'
                      ' type, ep, page, readEpisode, max_page)'
                      ' values (?,?,?,?,?,?,?,?,?,?)',
                      (rec['target'], rec['title'], rec['subtitle'], rec['cover'],
                       rec['time'], rec['type'], rec['ep'], rec['page'],
                       ','.join(str(e) for e in sorted(rec['readEpisode'])),
                       rec['maxPage']))
        merged += 1
hdest.commit()
print('history merged:', merged)

# the select that runs right after the history merge, uncaught in PicaComic
imgs = 0
for row in hsrc.execute('select * from image_favorites;'):
    json.loads(row['other'])
    _ = (row['id'], row['cover'], row['title'], int(row['ep']), int(row['page']))
    imgs += 1
print('image favourites read:', imgs)
print()
print('SIMULATED IMPORT COMPLETED WITH NO ERRORS')
