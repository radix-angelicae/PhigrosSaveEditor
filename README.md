# PhigrosSaveEditor

Phigros（菲格罗斯）云存档编辑器 —— 带图形界面，可查看/修改成绩与解锁数据，
支持从云端下载、改完再传回云端。

> **免责声明**：本项目仅用于个人存档的备份、恢复与研究。
> 修改并上传云存档可能违反游戏的用户协议，存在封号或存档损坏的风险。
> 使用前请务必备份原始存档，后果由使用者自行承担。

---

## 功能

| 功能 | 说明 |
|---|---|
| 打开存档 | 支持 `.zip` / `.save` / 以及被改成 `.zip.txt` 的抓包文件 |
| 成绩编辑 | 表格双击即改：分数、ACC、FC；带评级着色、搜索、筛选、排序 |
| 解锁数据 | `gameKey` 条目表格化，改 flags 或整行复制 |
| 设置 / 资料 | 设备名、简介、头像、音量等表单化编辑 |
| **强制解锁** | 按章节勾选曲目，一键解锁（见下） |
| **云存档** | 填 sessionToken 直连，下载 / 上传云端存档 |
| 备份管理 | 上传前自动备份云端原档，可浏览、载入、回滚 |
| 撤销 / 重做 | 多级，Ctrl+Z / Ctrl+Y |
| 深色模式 | 浅色 / 深色 / 跟随系统 |
| 数据校验 | 保存前检查分数、ACC 等矛盾项 |

---

## 快速开始

### 方式一：直接用源码（Windows / macOS / Linux）

需要 Python 3.9 ~ 3.12（自带 tkinter）。

```bash
pip install -r requirements.txt
python phigros_editor.py
```

### 方式二：打包成 Windows exe

双击 **`build.bat`**，它会自动：

1. 创建虚拟环境 `.venv_build`
2. 安装 `pycryptodome` + `pyinstaller`
3. 清理旧产物并打包成单文件

产物在 `dist\PhigrosSaveEditor.exe`，可拷到任意电脑双击运行。

> 构建脚本默认使用清华镜像源，失败会自动回退官方源。
> 首次构建约 1~3 分钟。

---

## 使用说明

### 1. 准备一份存档

三种途径，任选其一：

- **从云端下载**：工具栏「☁ 云存档」→ 填 sessionToken → 连接 → 「下载并打开」
- **导入 sessionToken**：云面板里「从 .userdata 导入」，
  该文件在手机的 `Android/data/com.PigeonGames.Phigros/files/.userdata`
- **自己抓包**：抓到的文件常被改名成 `xxx.zip.txt`，直接选它即可，程序会自动识别

### 2. 编辑

主界面五个标签页，对应存档里的五个条目：

| 标签页 | 内容 |
|---|---|
| 曲目成绩 | 每首歌的难度、分数、ACC、FC、评级 |
| 解锁数据 | `gameKey` 的解锁条目与 flags |
| 游戏设置 | 设备名与各项数值 |
| 用户资料 | 昵称、简介、头像 |
| 游戏进度 | 课题分与版本 |

成绩页双击单元格即可修改，改完标题栏会出现 `*` 提示未保存。

### 3. 强制解锁

工具栏「🔓 强制解锁」。按章节展开，勾哪首就解哪首。

解锁固定执行三步，缺一不可（实测只置位不写分数无效）：

1. `gameKey` 里给该曲加「曲绘/曲目解锁」位（bit3）
2. 向该曲**最高难度**写入分数（默认 880000 / 88%）
3. 写入全解锁的章节进度字节（保留你自己的课题分与版本串）

已打过的曲目默认不显示；需要时可勾「显示已游玩」。
已有成绩只补不覆盖，不会把你的高分改低。

### 4. 上传到云端

改完后：

- 工具栏「保存」→ 存成 zip
- 「☁ 云存档」→ 「上传当前存档到云端」

上传前会自动把**云端原档**下载下来备份，同时备份本次上传的内容。
备份列表里双击即可载入回滚。

> 若载入的是备份或本地文件（不是刚从云端下载的），只要已连接账号，
> 同样可以直接上传 —— 云端只有一份存档，程序会自动取它的 ID。

---

## 数据存放位置

程序不会往自身目录写任何数据，全部落在系统标准位置：

| 平台 | 路径 |
|---|---|
| Windows | `%APPDATA%\PhigrosSaveEditor` |
| macOS | `~/Library/Application Support/PhigrosSaveEditor` |
| Linux | `~/.local/share/PhigrosSaveEditor` |

内含 `config.json`（凭据与偏好）、`downloads/`（云端下载的存档）、
`backups/`（备份，自动保留最近 30 份 / 60 天）。

---

## 快捷键

| 按键 | 作用 |
|---|---|
| `Ctrl+O` | 打开存档 |
| `Ctrl+S` | 保存 |
| `Ctrl+Z` / `Ctrl+Y` | 撤销 / 重做 |
| `Ctrl+F` | 搜索 |
| `Delete` | 删除选中行 |
| `Enter` / `Esc` | 解锁窗口：确定 / 关闭 |

---

## 项目结构

```
phigros_editor.py      入口
build.bat              一键打包 exe
push_github.bat        一键推送到 GitHub
phi_app.py             主窗口
phi_views.py           五个条目的表格 / 表单视图
phi_format.py          存档二进制解析、重建、校验
phi_unlock.py          gameKey 解锁位与曲目名单
phi_unlock_ui.py       强制解锁窗口
phigros_cloud.py       云存档接口（下载 / 上传）
phi_cloud_ui.py        云存档窗口与备份管理
phi_chapters.py        章节结构与解锁链
phi_theme.py           配色与主题（含自绘勾选框）
phi_undo.py            撤销栈
phi_paths.py           数据目录与资源定位
phi_files.py           本地存档 / 备份列举
resources/             图标、曲库名单、章节数据
```

---

## 技术说明

云存档是一个 zip，内含五个条目，每个条目**第 1 个字节是格式版本号**，
其后是 AES-256-CBC（PKCS7 填充）密文：

```
gameRecord     曲目成绩
gameKey        解锁数据（收藏品 / 单曲 / 曲绘）
gameProgress   章节进度、课题分
settings       设备名与音量等
user           昵称、简介、头像
```

程序对每条记录都做「解析 → 重建 → 逐字节比对」自检，
只有完全一致的条目才开放结构化编辑，否则退回原始字节兜底并在界面标注，
避免因为游戏版本更新而悄悄写坏存档。

可用 `python phigros_editor.py --selftest <存档.zip>` 单独跑这个自检。

---

## 注意事项

- 修改云存档有封号风险，**务必先备份**。
- 游戏在登录态启动时可能用云端覆盖本地，改完建议先确认云端已生效。
- 解锁功能依赖内置的曲库名单与章节数据（`resources/`），
  游戏大版本更新后可能需要同步更新。

---

## License

[MIT](LICENSE)
