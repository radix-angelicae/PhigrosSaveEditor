# -*- coding: utf-8 -*-
"""本地存档与备份的列举、打开、删除。

本地存档来源有两处：
  1) 数据目录 downloads/ —— 从云端下载下来的存档
  2) 配置里的「最近打开」列表 —— 用户自己打开过的任意路径文件

备份统一放在数据目录 backups/，由上传流程自动产生，也可手动创建。
"""

import os
import time

import phi_paths as paths

# 下载目录里可能被塞进来的非存档文件
_JUNK_EXT = {".json", ".csv", ".log", ".md", ".tmp", ".part", ".crdownload"}
# 上传备份的文件名前缀 → 中文说明
_BACKUP_KIND = (("cloud_before_", "上传前的云端原档"),
                ("before_upload_", "上传前的本地文件"),
                ("uploaded_", "本次上传的内容"),
                ("manual_", "手动备份"))


def _stat(p):
    st = os.stat(p)
    return st.st_size, st.st_mtime


def _fmt_time(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _fmt_size(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.2f} MB"


def _looks_like_save(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in _JUNK_EXT:
        return False
    # 抓包拿到的常被改成 .zip.txt，这里再剥一层
    base, ext2 = os.path.splitext(os.path.splitext(name)[0])
    if ext2.lower() == ".zip":
        return True
    return ext in ("", ".zip", ".save", ".bin", ".txt", ".dat")


def scan_local(cfg):
    """列出本地存档，按修改时间倒序。每项 dict：
    path / name / dir / size / mtime / source / shown_time / shown_size"""
    found = {}

    d = paths.DOWNLOAD_DIR
    if os.path.isdir(d):
        try:
            for f in os.listdir(d):
                p = os.path.abspath(os.path.join(d, f))
                if os.path.isfile(p) and _looks_like_save(f):
                    found[p] = "云端下载"
        except Exception:
            pass

    for p in (cfg.get("recent") or []):
        try:
            ap = os.path.abspath(p)
            if os.path.isfile(ap):
                found.setdefault(ap, "最近打开")
        except Exception:
            pass

    out = []
    for p, src in found.items():
        try:
            size, mt = _stat(p)
        except Exception:
            continue
        out.append({"path": p, "name": os.path.basename(p),
                    "dir": os.path.dirname(p), "size": size, "mtime": mt,
                    "source": src})
    out.sort(key=lambda x: -x["mtime"])
    for it in out:
        it["shown_time"] = _fmt_time(it["mtime"])
        it["shown_size"] = _fmt_size(it["size"])
    return out


def backup_kind(name):
    for prefix, label in _BACKUP_KIND:
        if name.startswith(prefix):
            return label
    return "备份"


def scan_backups():
    """列出备份目录，按修改时间倒序"""
    out = []
    d = paths.BACKUP_DIR
    if not os.path.isdir(d):
        return out
    try:
        for f in os.listdir(d):
            p = os.path.abspath(os.path.join(d, f))
            if not os.path.isfile(p):
                continue
            try:
                size, mt = _stat(p)
            except Exception:
                continue
            out.append({"path": p, "name": f, "size": size, "mtime": mt,
                        "kind": backup_kind(f),
                        "shown_time": _fmt_time(mt),
                        "shown_size": _fmt_size(size)})
    except Exception:
        pass
    out.sort(key=lambda x: -x["mtime"])
    return out


def make_backup(data, tag="manual"):
    """写一份备份，返回文件路径"""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    p = os.path.join(paths.BACKUP_DIR, f"{tag}_{stamp}.zip")
    with open(p, "wb") as f:
        f.write(data)
    return p


def open_in_folder(path):
    """在系统文件管理器里选中/打开该文件所在目录（跨平台）"""
    import subprocess
    import sys
    try:
        target = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
        if sys.platform == "win32":
            os.startfile(target)          # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception:
        return False
