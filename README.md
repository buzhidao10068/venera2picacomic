# venera2picacomic 网页版 · 单文件

把 [Venera](https://github.com/venera-app/venera) 导出的 `.venera` 转成
[PicaComic](https://github.com/ccbkv/PicaComic) 能导入的 `.picadata`，迁移
**收藏夹**和**阅读历史**。

这个分支只有一个 [`index.html`](index.html)（983 KB），SQLite 的 wasm 也在里面。
下载下来双击就能用，不需要装 Python、不需要起服务器、不需要联网。

> **本项目由 AI 生成。** 代码、文档，以及两个 App 数据格式差异的逆推分析，均由
> Claude（Claude Code）完成。它没有经过人工逐行审阅，使用前请自行 review，
> 导入前请先在 PicaComic 里导出一份备份。

## 用法

**下载这一个文件，用浏览器打开，把 `.venera` 丢进去。**

```
# 或者用命令行拿
curl -LO https://raw.githubusercontent.com/buzhidao10068/venera2picacomic/web-single/index.html
```

页面会当场转换、自检、给出下载按钮。然后在 PicaComic 里走
「设置 → 备份与恢复 → 导入数据」选生成的文件。导入是**增量合并**：已有的收藏和
历史不会被清掉，同一本重复的会跳过。

## 为什么是一个文件

`.venera` 是你整个书库的记录。Venera 导出的 `appdata.json` 里**明文**保存着
WebDAV 的账号和密码，`cookie.db` 里是各站点的登录态。这种文件不该上传给任何人，
包括我。

所以：没有后端、没有 Worker、没有上传接口。而这一份连依赖也没有外链——
fflate、sql.js 和那个 643 KB 的 SQLite wasm 全部内联在 HTML 里，
**页面自身不发起任何网络请求**。可以：

- 直接 `file://` 双击打开，不必起 HTTP 服务器
- 拔网线用
- 存进 U 盘 / 备份盘。哪天这个仓库没了、Cloudflare 页面下线了，你手上这一个
  文件还是完整可用的

代价就是 983 KB：wasm 用 base64 内联会胀三分之一（643 KB → 857 KB），躲不掉。

## 部署到 Cloudflare Pages

一个文件而已，随便挑一种：

**直接拖**：Cloudflare dashboard → Workers & Pages → Create → Pages →
Upload assets → 把 `index.html` 拖进去 → Deploy。完事。

**连 GitHub 仓库**（之后 push 自动更新）：Connect to Git → 选中这个仓库 →
Production branch 选 `web-single` → Framework preset 选 None →
**Build command 留空，Build output directory 填 `/`**。

不需要任何 `_headers`、`_redirects` 或 MIME 配置——wasm 不是单独的文件，
没有 `Content-Type` 可配错。

## 三个分支怎么选

| 分支 | 形态 | 体积 | 取舍 |
|---|---|---|---|
| `web-single`（本分支） | 单个 `index.html`，wasm 以 base64 内联 | 983 KB | 一个文件，`file://` 直接可用，真正零请求 |
| [`web-vendored`](../../tree/web-vendored) | `web/` 四个文件 | 47 KB + 721 KB | 依赖能被浏览器分别缓存；改页面时不用重新生成 |
| [`web-cdn`](../../tree/web-cdn) | 单个 `index.html`，sql.js 从 cdnjs 取 | 80 KB | 仓库最小；但必须联网，且 cdnjs 在部分网络下不通 |

三份 `index.html` 的页面结构、样式和转换逻辑逐字节相同，只有
`<!-- VENDOR ... -->` 那一段不一样。本分支这一份是
[`web-vendored`](../../tree/web-vendored) 分支的 `web/build.py` 生成的，
想自己复现：

```bash
git switch web-vendored
python web/build.py --single -o /tmp/index.html
```

`build.py` 会先核对三个依赖文件的 sha256，对不上直接退出。生成的文件与本分支
这一份逐字节相同，可以 `sha256sum` 对一下。

## 页面做了什么

选文件之后依次跑三件事，结果都摊在页面上：

1. **转换** —— 重建两个 SQLite 库。两个 App 同源，但列名、来源编号、压缩包内
   文件名全都不一致，直接改扩展名无效。来源编号那张对照表，以及 `HistoryType`
   与 `FavoriteType` 在 nhentai 上的错位（5 对 6，写错了列表能显示、点开就崩），
   见 [`main` 分支的 README](../../blob/main/README.md#来源编号映射)。
2. **24 项自检** —— 每一项对应 PicaComic 导入器里一处真实行为，不是格式洁癖。
   点开每项能看到「为什么这条会出问题」。最要紧的几条：多余的顶层目录会让导入器
   **清空你的下载目录**；一行 `readEpisode` 解析失败会中断**整个**历史合并；
   `image_favorites` 表缺失会在合并历史之后无 try/catch 地抛异常。
3. **重放导入** —— 用与 PicaComic 相同的 SQL 把导入流程在浏览器里跑一遍，
   并按 `FavoriteType.comicSource` / `HistoryType.name` 的解析路径把每一行的
   来源解一遍。任何在 App 里会抛异常的行，会在这里先失败。

自检没全过也允许下载，但按钮会改成「自检未通过 · 仍然下载」。

「已经在用 PicaComic」那一栏可以再传一份你自己从 PicaComic 导出的 `.picadata`：
生成的包会沿用其中的 `appdata` / `cookies.db` / `comic_source`，只替换两个数据库，
这样设置和登录态不会退回默认值。不传则写一个最小副作用的 `appdata`。

## 里面内联了什么

| 组件 | 版本 | sha256 |
|---|---|---|
| [sql.js](https://github.com/sql-js/sql.js) `sql-wasm.js` | 1.14.2 | `f1c84000dbc856c9d87f4f3aabc4d3654bd436165db4be3da13751db3a9c20d7` |
| 同上 `sql-wasm.wasm`（base64） | 1.14.2 | `38c14f6e379210bc942bdc4ebca44e7bfdb4318ecc1c72ca666a28fdce96670a` |
| [fflate](https://github.com/101arrowz/fflate) `fflate.min.js` | 0.8.3 | `462ef8041fc970e3615a20a9dd2b2e3047a073b2da729ef4f02b634bba8b7b83` |

两个都是 MIT，许可原文见 [VENDOR-LICENSES.md](VENDOR-LICENSES.md)。
原始文件在 [`web-vendored`](../../tree/web-vendored) 分支的 `web/` 下，可以自己
比对。浏览器里要**写出** SQLite 文件，只有把 SQLite 编译成 wasm 这一条路，
所以这 643 KB 躲不掉。除此之外没有任何依赖：没有框架、没有 webfont、
没有统计脚本。

## 迁移范围

**会迁移**：收藏夹（含夹子顺序与夹内顺序）、阅读历史（含已读章节与页码）。

**不会迁移**：登录 cookie（库结构不同，需重新登录）、Venera 的 JS 漫画源
（API 不兼容）、单页图片收藏（两边数据模型不同）、设置与搜索历史。

非内置源（拷贝漫画、漫画柜、mangadex 等）的条目会保留，但需要你在 PicaComic
里装上 **key 完全相同**的源才能打开——两边都用 `sourceKey.hashCode` 编码，
所以 key 一致时数值天然相同。

## 命令行版

同一个转换器也有 Python 版，就在这个分支里（`venera2picacomic.py`，只依赖标准库），
另有 `verify.py` / `simulate_import.py`（页面上那两步的原始实现）和
`make_fixture.py`（生成一份不含真实数据的测试样本）。两个 App 的格式差异、
来源编号映射、导入器的六个坑，都写在 [`main` 分支的 README](../../blob/main/README.md) 里。

## 声明

本项目是非官方的第三方工具，与 [Venera](https://github.com/venera-app/venera)、
[PicaComic](https://github.com/ccbkv/PicaComic) 均无关联，也未获得任何一方背书。
它不提供、不托管、不分发任何漫画内容，也不访问任何漫画站点——全部工作是在本机
读取你自己导出的文件、写出另一个格式的文件。文档中出现的来源名称仅用于说明
两个 App 的内部编号如何对应。

导入会写入 PicaComic 的收藏库与历史库。**操作前请先在 PicaComic 里导出一份备份。**
格式是照 PicaComic 源码逆推的，上游改动可能使转换失效。

**注意保护自己的数据。** 提交 issue 时不要附带 `.venera` / `.picadata`，需要复现
问题请用 `make_fixture.py` 生成的样本，或自行删减成最小样本。本仓库的
`.gitignore` 已排除这两类文件。

## 许可证

[MIT](LICENSE)（本项目）。第三方组件见 [VENDOR-LICENSES.md](VENDOR-LICENSES.md)。
