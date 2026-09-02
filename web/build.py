# -*- coding: utf-8 -*-
"""Generate the two derived packagings of index.html from this directory.

    python build.py --single -o ../index.html   # everything inlined, one file
    python build.py --cdn    -o ../index.html   # sql.js from cdnjs, fflate inlined

Both variants differ from the source only inside the VENDOR block; the page
markup, the CSS and the converter are byte-identical across all three. The
vendor files are checked against the hashes below first, so a swapped or
truncated download fails here rather than in someone's browser.
"""
import argparse, base64, hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# sha256 of the pinned vendor files. sql-wasm.* are byte-identical to what
# cdnjs serves for sql.js 1.14.2, which is why --cdn can claim the same bits.
SHA256 = {
    'fflate.min.js':  '462ef8041fc970e3615a20a9dd2b2e3047a073b2da729ef4f02b634bba8b7b83',
    'sql-wasm.js':    'f1c84000dbc856c9d87f4f3aabc4d3654bd436165db4be3da13751db3a9c20d7',
    'sql-wasm.wasm':  '38c14f6e379210bc942bdc4ebca44e7bfdb4318ecc1c72ca666a28fdce96670a',
}
# subresource integrity for the one file --cdn actually fetches with a tag
SQLJS_SRI = ('sha512-G5E7whKQSPtDMO2K5CnlFdy518Z28CydpBURC+gT5JtOa+hMFMG0Jh'
             'ZUHgs+b7N4sbEOz2j0NfFQWmHVos5nUQ==')
CDN = 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.14.2/'

BEGIN, END = '<!-- VENDOR:BEGIN -->', '<!-- VENDOR:END -->'


def read(name, binary=False):
    with open(os.path.join(HERE, name), 'rb') as fh:
        raw = fh.read()
    got = hashlib.sha256(raw).hexdigest()
    if name in SHA256 and got != SHA256[name]:
        sys.exit('%s: sha256 mismatch\n  want %s\n  got  %s'
                 % (name, SHA256[name], got))
    return raw if binary else raw.decode('utf-8')


def inline(src):
    """Neither vendor file contains "</script", but assert it rather than
    trust it -- one occurrence would end the block early and break the page."""
    assert '</script' not in src.lower(), 'vendor file would close its own tag'
    return '<script>\n' + src.rstrip('\n') + '\n</script>'


def single():
    wasm = base64.b64encode(read('sql-wasm.wasm', binary=True)).decode('ascii')
    return '\n'.join([
        '<!-- vendored inline: fflate 0.8.3, sql.js 1.14.2 (MIT / MIT).',
        '     sha256 fflate.min.js %s' % SHA256['fflate.min.js'],
        '     sha256 sql-wasm.js   %s' % SHA256['sql-wasm.js'],
        '     sha256 sql-wasm.wasm %s -->' % SHA256['sql-wasm.wasm'],
        inline(read('fflate.min.js')),
        inline(read('sql-wasm.js')),
        '<script>',
        '/* the SQLite wasm module, base64 of the %d-byte sql-wasm.wasm.'
        % len(read('sql-wasm.wasm', binary=True)),
        '   Handing it over as wasmBinary is what keeps this a single file:',
        '   Emscripten then never calls locateFile and never fetches anything. */',
        'window.SQL_CONFIG = {wasmBinary: Uint8Array.from(atob("' + wasm
        + '"), c => c.charCodeAt(0))};',
        "window.SQL_SOURCE_NOTE = '这一份把 wasm 内联在 HTML 里，正常不该失败——"
        "如果真的失败了，多半是文件下载得不完整，请重新取一份完整的 index.html。';",
        '</script>',
    ])


def cdn():
    return '\n'.join([
        '<!-- fflate 0.8.3 inlined (32 KB, MIT); sql.js 1.14.2 from cdnjs.',
        '     The script tag is pinned by version and verified by SRI. The',
        '     643 KB sql-wasm.wasm beside it cannot be: Emscripten fetches it',
        '     itself, and there is no integrity attribute for that. -->',
        inline(read('fflate.min.js')),
        '<script src="%ssql-wasm.js" integrity="%s"' % (CDN, SQLJS_SRI),
        '        crossorigin="anonymous" referrerpolicy="no-referrer"></script>',
        '<script>',
        'window.SQL_CONFIG = {locateFile: f => %r + f};' % CDN,
        "window.SQL_SOURCE_NOTE = '这一份从 cdnjs 取 sql.js，看起来没取到——"
        "多半是网络不通或者被拦截了。web-single 分支的单文件版本可以完全离线使用。';",
        '</script>',
    ])


ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument('--single', action='store_const', const=single, dest='make')
g.add_argument('--cdn', action='store_const', const=cdn, dest='make')
ap.add_argument('-o', '--out', help='write here instead of stdout')
args = ap.parse_args()

# git hands index.html over with CRLF on Windows and LF everywhere else, so
# take the newlines back out: the derived files have to come out byte-identical
# whoever runs the build. The vendored sources keep the exact bytes their
# sha256 above covers -- they are checked in with -text for that reason.
page = read('index.html').replace('\r\n', '\n')
i, j = page.index(BEGIN), page.index(END) + len(END)
page = page[:i] + args.make() + page[j:]

if args.out:
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(page)
    print('wrote %s  %d bytes' % (args.out, len(page.encode('utf-8'))),
          file=sys.stderr)
else:
    sys.stdout.write(page)
