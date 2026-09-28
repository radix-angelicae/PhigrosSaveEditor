# -*- coding: utf-8 -*-
"""用户数据目录管理。

所有运行时数据统一放在系统标准用户数据目录，绝不写入程序安装目录：
    Windows : %APPDATA%\PhigrosSaveEditor
    macOS   : ~/Library/Application Support/PhigrosSaveEditor
    Linux   : $XDG_DATA_HOME/PhigrosSaveEditor (默认 ~/.local/share/...)
"""

import os
import sys
import time

APP_NAME = "PhigrosSaveEditor"


def resource_path(rel):
    """打包后资源位于临时解压目录 sys._MEIPASS，源码运行时在项目目录。
    用于定位 resources/ 下的图标等随程序分发的静态文件。"""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def _user_data_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_NAME)


def _ensure(d):
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR = _ensure(_user_data_dir())
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
BACKUP_DIR = _ensure(os.path.join(DATA_DIR, "backups"))
DOWNLOAD_DIR = _ensure(os.path.join(DATA_DIR, "downloads"))
# 备份保留策略
BACKUP_KEEP = 30
BACKUP_KEEP_DAYS = 60


def prune_backups(keep=BACKUP_KEEP, keep_days=BACKUP_KEEP_DAYS):
    """清理旧备份：最多保留 keep 份，且删除超过 keep_days 天的"""
    removed = []
    try:
        files = []
        for f in os.listdir(BACKUP_DIR):
            p = os.path.join(BACKUP_DIR, f)
            if os.path.isfile(p):
                files.append((os.path.getmtime(p), p))
        files.sort(reverse=True)
        now = time.time()
        for mtime, p in files[keep:]:
            try:
                os.remove(p)
                removed.append(os.path.basename(p))
            except Exception:
                pass
        for mtime, p in files[:keep]:
            if now - mtime > keep_days * 86400:
                try:
                    os.remove(p)
                    removed.append(os.path.basename(p))
                except Exception:
                    pass
    except Exception:
        pass
    return removed


# ---------------------------------------------------------------- 配置读写
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            import json
            return json.load(open(CONFIG_FILE, encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_config(cfg):
    try:
        import json
        json.dump(cfg, open(CONFIG_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------- 图标
def apply_icon(win):
    """给窗口设置图标：Windows 用 .ico（标题栏 + 任务栏），其他平台用 PNG。
    找不到图标文件时静默跳过，不影响启动。"""
    try:
        if sys.platform == "win32":
            p = resource_path("resources/app.ico")
            if os.path.exists(p):
                win.iconbitmap(default=p)
                # 让任务栏也用同一图标（Windows 需显式指定 AppUserModelID）
                try:
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                        "PigeonGames.PhigrosSaveEditor")
                except Exception:
                    pass
                return True
        else:
            p = resource_path("resources/app.png")
            if os.path.exists(p):
                img = __import__("tkinter").PhotoImage(file=p)
                win.iconphoto(True, img)
                win._icon_img = img      # 防被回收
                return True
    except Exception:
        pass
    return False
