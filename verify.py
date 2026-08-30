# -*- coding: utf-8 -*-
"""Check a generated .picadata against what PicaComic's importer requires.

Usage: python verify.py out.picadata

Every check below corresponds to something the importer actually does, so a
failure here means the import would misbehave rather than merely look odd.
"""
import json, re, sqlite3, sys, tempfile, zipfile, os

# lib/foundation/def.dart -- enum ComicType, in declaration order
COMIC_TYPE = ['picacg', 'ehentai', 'jm', 'hitomi', 'htManga', 'htFavorite',
              'nhentai', 'other']
# def.dart -- builtInSources: the keys ComicSource.find() can actually resolve
BUILT_IN = {'picacg', 'ehentai', 'jm', 'hitomi', 'htmanga', 'nhentai'}
# history.dart -- HistoryType.name indexes this list for values 0..5
HISTORY_NAMES = ['picacg', 'ehentai', 'jm', 'hitomi', 'htmanga', 'nhentai']

ok = True


def check(label, cond, detail=''):
    global ok
    ok = ok and cond
    print(('  OK   ' if cond else '  FAIL ') + label + (('  ' + detail) if detail else ''))


path = sys.argv[1]
z = zipfile.ZipFile(path)
names = z.namelist()
print('zip entries:', names)
check('appdata present (the importer throws without it)', 'appdata' in names)
check('local_favorite.db present (the importer copies it with no existence guard)',
      'local_favorite.db' in names)
check('history.db present', 'history.db' in names)
check('no directory entries (an unknown top-level dir is renamed to download/,'
      ' which then wipes the user download folder)',
      not [n for n in names if n.endswith('/') or '/' in n])
check('zip CRCs valid (the importer decodes with verify: true)', z.testzip() is None)

app = json.loads(z.read('appdata').decode('utf-8'))
check('appdata.settings is a list (List<String>.from, not null-guarded)',
      isinstance(app.get('settings'), list))
check('appdata.firstUse is a list (List<String>.from, not null-guarded)',
      isinstance(app.get('firstUse'), list))
check('settings empty, so the min-of-both copy loop overwrites no user setting',
      app['settings'] == [])
check('firstUse empty, so nothing is overwritten there either', app['firstUse'] == [])
check('settings has no index 46, so fileVersion falls back to "1" via'
      ' elementAtOrNull(46) ?? "1"',
      len(app['settings']) < 47 or str(app['settings'][46]).isdigit())
for key in ('blockingKeywords', 'favoriteTags'):
    check('appdata.%s is a list' % key, isinstance(app.get(key), list))
check('appdata has no history key (it would rewrite the history manager)',
      app.get('history') is None)

tmp = tempfile.mkdtemp()
z.extractall(tmp)
z.close()

h = sqlite3.connect(os.path.join(tmp, 'history.db'))
h.row_factory = sqlite3.Row
check('history columns match PicaComic exactly',
      [c[1] for c in h.execute('pragma table_info(history)')]
      == ['target', 'title', 'subtitle', 'cover', 'time', 'type', 'ep', 'page',
          'readEpisode', 'max_page'])
check('image_favorites table present with PicaComic columns (tryUpdateDb selects'
      ' from it with no try/catch)',
      [c[1] for c in h.execute('pragma table_info(image_favorites)')]
      == ['id', 'title', 'cover', 'ep', 'page', 'other'])
bad = [r['readEpisode'] for r in h.execute('select readEpisode from history')
       if not re.fullmatch(r'(\d+(,\d+)*)?', r['readEpisode'] or '')]
check('every readEpisode is int.parse-safe (one bad row aborts the whole merge)',
      not bad, str(bad[:5]))
check('no nulls in history columns that are cast on read',
      h.execute('select count(*) from history where title is null or cover is null'
                ' or ep is null or page is null or time is null or max_page is'
                ' null or subtitle is null').fetchone()[0] == 0)
htypes = {t: n for t, n in h.execute('select type, count(*) from history group by type')}
check('no history type in 6..7 (HistoryType only names 0..5; higher values are'
      ' looked up as JS-source key hashes)',
      not [t for t in htypes if 6 <= t <= 7], str([t for t in htypes if 6 <= t <= 7]))
print('  history rows:', h.execute('select count(*) from history').fetchone()[0])
print('  history type -> count:', sorted(htypes.items(), key=lambda kv: -kv[1]),
      {t: HISTORY_NAMES[t] for t in sorted(htypes) if t < len(HISTORY_NAMES)})

f = sqlite3.connect(os.path.join(tmp, 'local_favorite.db'))
f.row_factory = sqlite3.Row
tables = [r[0] for r in f.execute("select name from sqlite_master where type='table'")]
check('folder_order exists', 'folder_order' in tables)
check('folder_sync exists with PicaComic columns',
      [c[1] for c in f.execute('pragma table_info(folder_sync)')]
      == ['folder_name', 'time', 'key', 'sync_data'])
total, layout_ok, null_ok, ftypes = 0, True, True, {}
for t in tables:
    if t in ('folder_order', 'folder_sync'):
        continue
    layout_ok = layout_ok and [c[1] for c in f.execute('pragma table_info("%s")' % t)] == [
        'target', 'name', 'author', 'type', 'tags', 'cover_path', 'time',
        'last_update_time', 'has_new_update', 'last_check_time', 'display_order']
    total += f.execute('select count(*) from "%s"' % t).fetchone()[0]
    null_ok = null_ok and not f.execute(
        'select count(*) from "%s" where target is null or name is null or author'
        ' is null or tags is null or cover_path is null or time is null' % t).fetchone()[0]
    for ty, n in f.execute('select type, count(*) from "%s" group by type' % t):
        ftypes[ty] = ftypes.get(ty, 0) + n
check('every folder table has the PicaComic column layout', layout_ok)
check('no nulls in folder columns that are cast on read', null_ok)
unresolvable = [ty for ty in ftypes if 0 <= ty <= 6
                and COMIC_TYPE[ty].lower() not in BUILT_IN]
check('no favourite type resolves to a key ComicSource.find() cannot resolve'
      ' (type 5 is htFavorite and throws on the null-assertion)',
      not unresolvable, str([(ty, COMIC_TYPE[ty]) for ty in unresolvable]))
orders = [tuple(r) for r in f.execute('select * from folder_order order by order_value')]
check('folder_order values are unique', len({o for _, o in orders}) == len(orders))
print('  favourite folders:', len(tables) - 2, ' comics:', total)
print('  favourite type -> count:', sorted(ftypes.items(), key=lambda kv: -kv[1]),
      {ty: COMIC_TYPE[ty] for ty in sorted(ftypes) if 0 <= ty <= 6})
for name, o in orders:
    print('   %-3d %s' % (o, name))

print()
print('RESULT:', 'all checks passed' if ok else 'PROBLEMS FOUND')
sys.exit(0 if ok else 1)
