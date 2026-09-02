# venera2picacomic 网页版 · CDN 版

把 [Venera](https://github.com/venera-app/venera) 导出的 `.venera` 转成
[PicaComic](https://github.com/ccbkv/PicaComic) 能导入的 `.picadata`，迁移
**收藏夹**和**阅读历史**。

这个分支是一个 80 KB 的 [`index.html`](index.html)：fflate 内联在里面，
SQLite 的 wasm 从 cdnjs 取。

> **先说清楚：多数人应该用 [`web-single`](../../tree/web-single) 分支，不是这个。**
> 这一份唯一的优势是仓库和 HTML 都小，代价是必须联网，而 cdnjs 在国内网络下
> 时常不通——真打不开时页面会卡在「正在加载 SQLite……」。

> **本项目由 AI 生成。** 代码、文档，以及两个 App 数据格式差异的逆推分析，均由
> Claude（Claude Code）完成。它没有经过人工逐行审阅，使用前请自行 review，
> 导入前请先在 PicaComic 里导出一份备份。

## 什么时候选这一份

适合：你要部署到静态托管，希望仓库和首屏尽量小，且确认目标用户能访问 cdnjs
（例如部署在 Cloudflare Pages，访问者主要在墙外）。

不适合：想离线用、想 `file://` 双击打开、访问者在国内网络。那些情况用
[`web-single`](../../tree/web-single)。

## 你的文件仍然不会离开设备

`.venera` 是你整个书库的记录。Venera 导出的 `appdata.json` 里**明文**保存着
WebDAV 的账号和密码，`cookie.db` 里是各站点的登录态。所以这里没有后端、
没有 Worker、没有上传接口——**转换全在浏览器里跑，你的文件一个字节都不会发出去**。

但这一份和另两个不同：它会向 cdnjs 发两个请求（`sql-wasm.js` 和
`sql-wasm.wasm`）。cdnjs 因此能看到你的 IP 和你加载了这个页面——不是文件内容，
但也不是零。如果页面本身部署在 Cloudflare Pages，那么 cdnjs 并没有引入新的
第三方（两者都是 Cloudflare）；部署在别处就是多了一个。

`sql-wasm.js` 的 `<script>` 标签上钉了 subresource integrity，被篡改浏览器会拒绝执行。
**它旁边那个 643 KB 的 `sql-wasm.wasm` 钉不了**——那是 Emscripten 自己 fetch 的，
没有 `integrity` 属性可加。介意这一点就用内联版：那边这两样都在 HTML 里，
sha256 写在 README 上。

## 部署到 Cloudflare Pages

**直接拖**：Cloudflare dashboard → Workers & Pages → Create → Pages →
Upload assets → 把 `index.html` 拖进去 → Deploy。

**连 GitHub 仓库**（之后 push 自动更新）：Connect to Git → 选中这个仓库 →
Production branch 选 `web-cdn` → Framework preset 选 None →
**Build command 留空，Build output directory 填 `/`**。

如果你给站点加了 CSP，`script-src` 需要放行 `https://cdnjs.cloudflare.com`，
`connect-src` 同样（wasm 是 fetch 来的）。

## 三个分支怎么选

| 分支 | 形态 | 体积 | 取舍 |
|---|---|---|---|
| [`web-single`](../../tree/web-single) | 单个 `index.html`，wasm 以 base64 内联 | 983 KB | **推荐**。一个文件，`file://` 直接可用，真正零请求 |
| [`web-vendored`](../../tree/web-vendored) | `web/` 四个文件 | 47 KB + 721 KB | 依赖能被浏览器分别缓存；改页面时不用重新生成 |
| `web-cdn`（本分支） | 单个 `index.html`，sql.js 从 cdnjs 取 | 80 KB | 仓库最小；但必须联网，且 cdnjs 未必能访问 |

三份 `index.html` 的页面结构、样式和转换逻辑逐字节相同，只有
`<!-- VENDOR ... -->` 那一段不一样。本分支这一份是
[`web-vendored`](../../tree/web-vendored) 分支的 `web/build.py` 生成的，
想自己复现：

```bash
git switch web-vendored
python web/build.py --cdn -o /tmp/index.html
```

生成的文件与本分支这一份逐字节相同，可以 `sha256sum` 对一下。

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

生成后在 PicaComic 里走「设置 → 备份与恢复 → 导入数据」选该文件。导入是
**增量合并**：已有的收藏和历史不会被清掉，同一本重复的会跳过。

## 依赖

| 组件 | 版本 | 来源 | 校验 |
|---|---|---|---|
| [fflate](https://github.com/101arrowz/fflate) | 0.8.3 | 内联（32 KB） | sha256 `462ef804…8b7b83` |
| [sql.js](https://github.com/sql-js/sql.js) `sql-wasm.js` | 1.14.2 | cdnjs | SRI `sha512-G5E7whKQ…` |
| 同上 `sql-wasm.wasm` | 1.14.2 | cdnjs（643 KB） | **无法校验**，见上文 |

两个都是 MIT，许可原文见 [VENDOR-LICENSES.md](VENDOR-LICENSES.md)。cdnjs 上这两个
文件与 [`web-vendored`](../../tree/web-vendored) 分支 `web/` 下随仓库存放的副本
逐字节相同（sha256 都记在那边的 README 里），可以自己比对。

浏览器里要**写出** SQLite 文件，只有把 SQLite 编译成 wasm 这一条路，所以这
688 KB 躲不掉——三个分支的区别只是它从哪儿来。除此之外没有任何依赖：
没有框架、没有 webfont、没有统计脚本。

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
