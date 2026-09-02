# -*- coding: utf-8 -*-
"""Build a synthetic .venera export that exercises every branch of the converter.

No personal data: every title, id and cover here is made up. The point is to hit
the cases that actually broke things -- chapter-group readEpisode, the nhentai
enum split, JS-source hashes, protocol-relative covers, nulls, a folder missing
from folder_order, odd folder names, and a folder table without the optional
columns.
"""
import os, sqlite3, zipfile, json, tempfile, shutil, sys

JM, PICACG, EHENTAI, NHENTAI = 769844263, 553570794, 385625716, 264196719
COPY, MANGADEX, WNACG, HITOMI = 557997769, 577718694, 823512256, 258019538

out = sys.argv[1]
work = tempfile.mkdtemp()

# ---- history.db, with Venera's column set (note the extra chapter_group) ----
h = sqlite3.connect(os.path.join(work, 'history.db'))
h.execute("""create table history (id text primary key, title text, subtitle text,
  cover text, time int, type int, ep int, page int, readEpisode text,
  max_page int, chapter_group text)""")
HIST = [
    # id, title, subtitle, cover, time, type, ep, page, readEpisode, max_page, chapter_group
    ('jm-1', '标题一', '副标题', 'https://a.example/1.jpg', 1755000000000, JM, 1, 7, '1-1', 20, '1'),
    ('jm-2', '标题二', '', 'https://a.example/2.jpg', 1755000001000, JM, 2, 3, '1-1,1-2,2-1', 30, '1'),
    ('jm-3', '标题三', None, None, 1755000002000, JM, 1, 1, '2,2,3', 10, None),
    ('pic-1', 'picacg 一本', '', 'https://a.example/p.jpg', 1755000003000, PICACG, 1, 2, '1', 40, None),
    ('eh-1', 'ehentai 一本', '', 'https://a.example/e.jpg', 1755000004000, EHENTAI, 1, 1, '', 5, None),
    ('nh-1', 'nhentai 一本', '', '//t4.nhentai.example/n.jpg', 1755000005000, NHENTAI, 1, 9, None, 25, None),
    ('cp-1', '拷贝漫画的一本', '', '//img.copy.example/c.jpg', 1755000006000, COPY, 1, 4, '1-3', 12, '1'),
    ('md-1', 'mangadex 一本', '', 'https://a.example/m.jpg', 1755000007000, MANGADEX, 3, 0, '5', 18, None),
    ('wn-1', 'wnacg 一本', '', 'https://a.example/w.jpg', 1755000008000, WNACG, 1, 1, '1', 8, None),
    ('ht-1', 'hitomi 一本', '', 'https://a.example/h.jpg', 1755000009000, HITOMI, 1, 1, '1', 8, None),
    ('null-1', None, None, None, 1755000010000, JM, None, None, None, None, None),
    ('weird-1', '带 <标签> 与 "引号" 的标题', '', 'https://a.example/x.jpg',
     1755000011000, JM, 1, 1, ' 4 , 5-2 ', 9, None),
]
h.executemany('insert into history values (?,?,?,?,?,?,?,?,?,?,?)', HIST)
h.commit(); h.close()

# ---- local_favorite.db ----
f = sqlite3.connect(os.path.join(work, 'local_favorite.db'))
f.execute('create table folder_sync (folder_name text primary key, time TEXT,'
          ' key TEXT, sync_data TEXT)')
f.execute('create table folder_order (folder_name text primary key, order_value int)')

FULL = """create table "{n}" (id text, name TEXT, author TEXT, type int, tags TEXT,
  cover_path TEXT, time TEXT, last_update_time TEXT DEFAULT NULL,
  has_new_update INTEGER DEFAULT 0, last_check_time INTEGER DEFAULT NULL,
  display_order int, translated_tags TEXT, primary key (id, type))"""
# an older Venera table that never gained the update-tracking columns
LEAN = """create table "{n}" (id text, name TEXT, author TEXT, type int, tags TEXT,
  cover_path TEXT, time TEXT, display_order int, primary key (id, type))"""

def full(name, rows, order=None):
    f.execute(FULL.format(n=name.replace('"', '""')))
    for i, r in enumerate(rows):
        f.execute('insert into "%s" (id, name, author, type, tags, cover_path, time,'
                  ' last_update_time, has_new_update, last_check_time, display_order,'
                  ' translated_tags) values (?,?,?,?,?,?,?,?,?,?,?,?)'
                  % name.replace('"', '""'),
                  r + ('2026-01-01', 0, 1755000000, len(rows) - i, '译名'))
    if order is not None:
        f.execute('insert into folder_order values (?,?)', (name, order))

def lean(name, rows, order=None):
    f.execute(LEAN.format(n=name.replace('"', '""')))
    for i, r in enumerate(rows):
        f.execute('insert into "%s" (id, name, author, type, tags, cover_path, time,'
                  ' display_order) values (?,?,?,?,?,?,?,?)' % name.replace('"', '""'),
                  r + (len(rows) - i,))
    if order is not None:
        f.execute('insert into folder_order values (?,?)', (name, order))

# id, name, author, type, tags, cover_path, time
full('JM', [('jm-1', '标题一', '作者甲', JM, 'a,b', 'https://a.example/1.jpg', '2026-01-01'),
            ('jm-2', '标题二', '作者乙', JM, '', 'https://a.example/2.jpg', '2026-01-02')], 0)
full('picacg', [('pic-1', 'picacg 一本', '', PICACG, 'x', 'https://a.example/p.jpg', '2026-01-03')], 2)
# the enum split lives here: these must come out as type 6, not 5
full('ehentai', [('eh-1', 'ehentai 一本', '', EHENTAI, '', 'https://a.example/e.jpg', '2026-01-04'),
                 ('nh-1', 'nhentai 一本', '', NHENTAI, 'y', '//t4.nhentai.example/n.jpg', '2026-01-05')], 1)
full('😋', [('cp-1', '拷贝漫画的一本', '', COPY, '', '//img.copy.example/c.jpg', '2026-01-06')], 5)
full('说"引号"的夹子', [('md-1', 'mangadex 一本', None, MANGADEX, None, None, None)], 9)
# no folder_order row at all -> must be given a fresh, non-colliding value
lean('没排序的夹子', [('wn-1', 'wnacg 一本', '', WNACG, '', 'https://a.example/w.jpg', '2026-01-07'),
                 ('ht-1', 'hitomi 一本', '', HITOMI, '', 'https://a.example/h.jpg', '2026-01-08')])
lean('另一个没排序的', [('jm-3', '标题三', '', JM, '', 'https://a.example/3.jpg', '2026-01-09')])
f.commit(); f.close()

appdata = {'settings': {'comicDisplayMode': 'detailed', 'favorites': ['jm', 'picacg']},
           'webdav': ['https://dav.example/', 'user', 'not-a-real-password']}
with open(os.path.join(work, 'appdata.json'), 'w', encoding='utf-8') as fh:
    json.dump(appdata, fh, ensure_ascii=False)
os.makedirs(os.path.join(work, 'comic_source'), exist_ok=True)
with open(os.path.join(work, 'comic_source', 'copy_manga.js'), 'w', encoding='utf-8') as fh:
    fh.write('// stub source script\n')
c = sqlite3.connect(os.path.join(work, 'cookie.db'))
c.execute('create table cookies (host text, name text, value text)')
c.execute("insert into cookies values ('example.com','sid','stub')")
c.commit(); c.close()

with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in ('history.db', 'local_favorite.db', 'appdata.json', 'cookie.db'):
        z.write(os.path.join(work, name), name)
    z.write(os.path.join(work, 'comic_source', 'copy_manga.js'), 'comic_source/copy_manga.js')
shutil.rmtree(work, ignore_errors=True)
print('wrote', out, os.path.getsize(out), 'bytes')
print('history rows', len(HIST))
