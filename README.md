# venera2picadata

把 [Venera](https://github.com/venera-app/venera) 导出的 `.venera` 文件转成
[PicaComic](https://github.com/ccbkv/PicaComic) 能导入的 `.picadata`，迁移**收藏夹**和**阅读历史**。

两个 App 同源，所以数据库结构相近，但列名、来源编号、压缩包内文件名全都不一致，
直接改扩展名无效——必须重建数据库。

> **本项目由 AI 生成。** 代码、文档，以及两个 App 数据格式差异的逆推分析，均由
> Claude（Claude Code）完成。格式结论来自通读 PicaComic 源码，并由仓库内的
> `verify.py` 与 `simulate_import.py` 交叉验证；但它没有经过人工逐行审阅，
> 使用前请自行 review，涉及你自己数据的操作请务必先备份。

## 用法

```bash
python venera2picadata.py in.venera out.picadata [已有的PicaComic导出.picadata]
```

只需要 Python 3（标准库 `sqlite3` + `zipfile`），无第三方依赖。

第三个参数可选：传入一份你自己从 PicaComic 导出的 `.picadata`，会沿用其中的
`appdata` / `cookies.db` / `comic_source`，只替换两个数据库。不传则生成一个
最小副作用的 `appdata`（见下文）。

生成后在 PicaComic 里走「设置 → 备份与恢复 → 导入数据」选择该文件。导入是
**增量合并**：已有条目保留，重复的按 `(target, type)` / `target` 跳过。

### 校验

```bash
python verify.py out.picadata          # 逐项检查导入器的硬性要求
python simulate_import.py out.picadata # 用同样的 SQL 重放一遍导入流程
```

`simulate_import.py` 会按 `FavoriteType.comicSource` / `HistoryType.name` 的解析
路径把每一行的来源解一遍，任何在 App 里会抛异常的行会在这里先失败。

## 迁移范围

**会迁移**：收藏夹（含夹子顺序与夹内顺序）、阅读历史（含已读章节与页码）。

**不会迁移**：登录 cookie（库结构不同，需重新登录）、Venera 的 JS 漫画源
（API 不兼容）、单页图片收藏（两边数据模型不同）、设置与搜索历史。

非内置源（拷贝漫画、漫画柜、mangadex 等）的条目会保留，但需要你在 PicaComic
里装上 **key 完全相同**的源才能打开——两边都用 `sourceKey.hashCode` 编码，
所以 key 一致时数值天然相同。

## 格式差异

| | Venera | PicaComic |
|---|---|---|
| 压缩包内文件名 | `appdata.json` / `cookie.db` | `appdata` / `cookies.db` |
| 历史表主键列 | `id` | `target` |
| 历史表多余列 | `chapter_group` | — |
| 收藏夹表主键列 | `id` | `target` |
| 收藏夹表多余列 | `translated_tags` | — |
| 收藏夹表额外列 | — | `last_update_time` / `has_new_update` / `last_check_time` |
| `folder_sync` 列 | `folder_name, source_key, source_folder` | `folder_name, time, key, sync_data` |
| 来源编号 | 一律 `sourceKey.hashCode` | 内置源用固定小值，仅 JS 源用 hashCode |

### 来源编号映射

注意 PicaComic 的两个枚举**并不一致**，历史和收藏必须分开映射：

| 来源 | Venera（`sourceKey.hashCode`） | `HistoryType` | `FavoriteType` |
|---|---|---|---|
| picacg | 553570794 | 0 | 0 |
| ehentai | 385625716 | 1 | 1 |
| jm | 769844263 | 2 | 2 |
| hitomi | 258019538 | 3 | 3 |
| wnacg → htmanga | 823512256 | 4 | 4 |
| nhentai | 264196719 | **5** | **6** |

收藏那边跳过 5，是因为 `FavoriteType` 经 `ComicType.values[key]` 解析，而枚举
第 5 位是 `htFavorite`——没有任何内置源用这个 key。

Venera 的 hashCode 是 Dart VM 的 30 位字符串哈希（one-at-a-time，遍历 UTF-16
码元），可以在 Python 里复现，所以映射表是算出来的而不是猜的。

## 导入器的坑

以下都是 PicaComic 侧真实存在的行为，转换时必须规避：

- **`appdata` 是必需项**，缺失直接抛异常。但 `readDataFromJson` 的两个拷贝循环
  都取两边长度的最小值（`i < settings.length && i < newSettings.length`），
  版本探测又是 `settings.elementAtOrNull(46) ?? "1"`，所以
  `{"settings":[],"firstUse":[],"blockingKeywords":[],"favoriteTags":[]}`
  既能通过校验，又一项设置都不会覆盖。`settings` 和 `firstUse` 必须存在
  （都走 `List<String>.from`，为 null 会抛）。
- **`local_favorite.db` 是必需项**，拷贝时没有存在性判断。
- **不要放任何多余的顶层目录**：未知目录会被重命名成 `download`，
  而存在 `download` 时导入器会先**清空用户的整个下载目录**。
- **`readEpisode` 会被 `int.parse` 逐项解析**。Venera 对有章节分组的源写成
  `"1-1"` 这种形式，一行解析失败会中断**整个历史合并**。
- **`image_favorites` 表必须存在**：合并历史后紧跟一句
  `select * from image_favorites`，没有 try/catch。建一张空表即可，
  它的结构（每张图一行：`id/title/cover/ep/page/other`）和 Venera 的
  按漫画一行也不一样。
- 若干列在读取时会被强转 `String` / `int`，为 NULL 会抛异常，需要填默认值。

## 声明

本项目是非官方的第三方工具，与 [Venera](https://github.com/venera-app/venera)、
[PicaComic](https://github.com/ccbkv/PicaComic) 均无关联，也未获得任何一方背书。
它不提供、不托管、不分发任何漫画内容，也不访问任何漫画站点——全部工作是在本机
读取你自己导出的文件、写出另一个格式的文件。README 中出现的来源名称仅用于说明
两个 App 的内部编号如何对应。

导入会写入 PicaComic 的收藏库与历史库。**操作前请先在 PicaComic 里导出一份备份**。
格式是照下文所列源码逆推的，上游改动可能使转换失效。

**注意保护自己的数据。** `.venera` / `.picadata` 是你完整书库的记录——收藏、
阅读历史、封面地址。Venera 导出的 `appdata.json` 还**明文**保存着 WebDAV 的账号
与密码，`cookie.db` 里是各站点的登录态。提交 issue 时不要附带这些文件，需要复现
问题请自行删减成最小样本。本仓库的 `.gitignore` 已排除这两类文件。

## 兼容性

对照 [ccbkv/PicaComic](https://github.com/ccbkv/PicaComic) `master` 的
`lib/utils/io_tools.dart`、`lib/foundation/local_favorites.dart`、
`lib/foundation/history.dart`、`lib/foundation/image_favorites.dart`、
`lib/foundation/def.dart`、`lib/base.dart` 实现。上游
[wgh136/PicaComic](https://github.com/wgh136/PicaComic) 的导入流程基本相同，
多出的空表和多余列都会被按列名读取的合并逻辑忽略。

## 许可证

[MIT](LICENSE)
