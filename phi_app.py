# -*- coding: utf-8 -*-
"""主窗口 App：布局、存档载入/保存、撤销重做、主题切换、各子窗口入口。"""

import copy
import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import phi_paths as paths
from phi_theme import (C, F_UI, F_UI_B, F_SMALL, F_TITLE,
                       apply_theme, system_prefers_dark)
from phi_undo import UndoStack
from phi_format import (ENTRY_LABEL, HINTS,
                        load_archive, save_archive, parse_entry, build_entry,
                        validate_entry)
from phi_views import RecordView, KeyView, FormView
from phi_cloud_ui import CloudDialog
from phi_unlock_ui import UnlockDialog

RECENT_MAX = 6


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phigros 云存档编辑器")
        self.configure(background=C["bg"])
        paths.apply_icon(self)

        self.cfg = paths.load_config()
        self.names, self.originals = [], {}
        self.views = {}
        self.bad_entries = []
        self.dirty = False
        self.current_file = None
        self.cloud_ctx = None
        # 云端连接会话：保存在主窗口上，云存档窗口关闭也不清空，
        # 只有整个程序退出时才断开（见 on_close / close_cloud）
        self.cloud_user = None
        self.cloud_token = ""
        self.cloud_server = ""
        self.cloud_saves = []
        self.cloud_meta = None
        self.cloud_dlg = None
        self.raw_order = []
        self.undo = UndoStack()

        self.file_label = tk.StringVar(value="未打开文件")
        self.status_var = tk.StringVar(value="")
        self.dirty_var = tk.StringVar(value="")
        self.undo_var = tk.StringVar(value="")

        self.style = ttk.Style(self)
        self._init_theme()
        self._fit_screen()
        self._build_menu()
        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._refresh_cloud_btn()
        self._status("就绪 —— 请打开一个存档，或从云端下载")

    # ------------------------------------------------------------ 主题
    def _init_theme(self):
        mode = self.cfg.get("theme", "system")
        dark = system_prefers_dark() if mode == "system" else (mode == "dark")
        C.set(dark)
        apply_theme(self, self.style)
        self.theme_mode = mode

    def set_theme(self, mode):
        """mode: light / dark / system"""
        self.cfg["theme"] = mode
        paths.save_config(self.cfg)
        self.theme_mode = mode
        dark = system_prefers_dark() if mode == "system" else (mode == "dark")
        C.set(dark)
        apply_theme(self, self.style)
        self._rebuild_views()          # 重建视图以应用新的行颜色等
        # 云存档窗口也重建以套用新主题；只销毁窗口，连接状态保留，
        # 下次打开会自动恢复（见 CloudDialog._restore_session）
        dlg = self.cloud_dlg
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.destroy()
            except Exception:
                pass
            self.cloud_dlg = None
        self._status(f"已切换为{'深色' if C.dark else '浅色'}主题")

    def toggle_theme(self):
        self.set_theme("light" if C.dark else "dark")

    def _rebuild_views(self):
        if not self.views:
            return
        objs = {n: v.obj for n, v in self.views.items()}
        self._build_tabs(objs)

    # ------------------------------------------------------------ 窗口尺寸
    def _fit_screen(self):
        w, h = 1280, 840
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w = max(1040, min(w, sw - 120))
            h = max(640, min(h, sh - 120))
        except Exception:
            pass
        self.minsize(1000, 620)
        self.geometry(f"{w}x{h}")

    # ------------------------------------------------------------ 菜单
    def _build_menu(self):
        m = tk.Menu(self, tearoff=0, background=C["card"], foreground=C["text"])
        self.configure(menu=m)

        tmenu = tk.Menu(m, tearoff=0, background=C["card"], foreground=C["text"])
        m.add_cascade(label="工具", menu=tmenu)
        tmenu.add_command(label="强制解锁…", command=self.open_unlock)
        tmenu.add_command(label="云存档…", command=self.open_cloud)

        fmenu = tk.Menu(m, tearoff=0, background=C["card"], foreground=C["text"])
        m.add_cascade(label="文件", menu=fmenu)
        fmenu.add_command(label="打开存档…", command=self.open_file, accelerator="Ctrl+O")
        fmenu.add_command(label="保存为存档…", command=self.save_zip, accelerator="Ctrl+S")
        fmenu.add_separator()
        fmenu.add_command(label="导出 JSON…", command=self.export_all)
        fmenu.add_command(label="导入 JSON…", command=self.import_json)
        fmenu.add_separator()
        fmenu.add_command(label="退出", command=self.on_close)

        emenu = tk.Menu(m, tearoff=0, background=C["card"], foreground=C["text"])
        m.add_cascade(label="编辑", menu=emenu)
        emenu.add_command(label="撤销", command=self.do_undo, accelerator="Ctrl+Z")
        emenu.add_command(label="重做", command=self.do_redo, accelerator="Ctrl+Y")
        emenu.add_separator()
        emenu.add_command(label="搜索曲目", command=self.focus_search, accelerator="Ctrl+F")

        vmenu = tk.Menu(m, tearoff=0, background=C["card"], foreground=C["text"])
        m.add_cascade(label="视图", menu=vmenu)
        vmenu.add_command(label="浅色主题", command=lambda: self.set_theme("light"))
        vmenu.add_command(label="深色主题", command=lambda: self.set_theme("dark"))
        vmenu.add_command(label="跟随系统", command=lambda: self.set_theme("system"))

        hmenu = tk.Menu(m, tearoff=0, background=C["card"], foreground=C["text"])
        m.add_cascade(label="帮助", menu=hmenu)
        hmenu.add_command(label="打开数据目录", command=self.open_data_dir)
        hmenu.add_command(label="使用说明", command=self.show_help)

    # ------------------------------------------------------------ 界面
    def _build_ui(self):
        # 标题栏
        top = ttk.Frame(self, padding=(16, 12, 16, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Phigros 云存档编辑器",
                  font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.file_label, font=F_SMALL,
                  foreground=C["dim"]).pack(side="left", padx=(12, 0))

        # 工具栏
        bar = ttk.Frame(self, padding=(16, 0, 16, 10))
        bar.pack(fill="x")
        self.path_var = tk.StringVar()
        ttk.Button(bar, text="打开存档", style="Accent.TButton",
                   command=self.open_file).pack(side="left")
        ttk.Button(bar, text="保存到本地", style="Accent.TButton",
                   command=self.save_zip).pack(side="left", padx=(8, 0))
        self.cloud_btn = ttk.Button(bar, text="☁ 云存档", command=self.open_cloud)
        self.cloud_btn.pack(side="left", padx=(8, 0))
        ttk.Frame(bar, width=1).pack(side="left", padx=8, fill="y")
        ttk.Button(bar, text="↶", style="Tool.TButton", width=3,
                   command=self.do_undo).pack(side="left")
        ttk.Button(bar, text="↷", style="Tool.TButton", width=3,
                   command=self.do_redo).pack(side="left", padx=(4, 0))
        ttk.Label(bar, textvariable=self.undo_var, font=F_SMALL,
                  foreground=C["dim"]).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="◐ 主题", style="Tool.TButton",
                   command=self.toggle_theme).pack(side="right")
        ttk.Button(bar, text="数据目录", style="Tool.TButton",
                   command=self.open_data_dir).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="说明", style="Tool.TButton",
                   command=self.show_help).pack(side="right", padx=(0, 6))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=(0, 4))

        # 内容区：空状态引导 / 标签页
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        self.nb = ttk.Notebook(self.body)
        self._build_welcome()
        self.welcome.pack(fill="both", expand=True)

        # 状态栏
        foot = ttk.Frame(self, padding=(16, 6, 16, 8))
        foot.pack(fill="x", side="bottom")
        ttk.Separator(foot, orient="horizontal").pack(fill="x", pady=(0, 6))
        ttk.Label(foot, textvariable=self.status_var, font=F_SMALL,
                  foreground=C["dim"]).pack(side="left")
        ttk.Label(foot, textvariable=self.dirty_var, font=F_SMALL,
                  foreground=C["danger"]).pack(side="right")

    def _build_welcome(self):
        self.welcome = ttk.Frame(self.body)
        inner = ttk.Frame(self.welcome)
        inner.pack(expand=True)
        ttk.Label(inner, text="开始使用", font=F_TITLE).pack(pady=(0, 4))
        ttk.Label(inner, text="打开一份 Phigros 云存档压缩包，或从云端下载你的存档",
                  font=F_UI, foreground=C["dim"]).pack(pady=(0, 20))

        btns = ttk.Frame(inner)
        btns.pack()
        ttk.Button(btns, text="打开本地存档…", style="Accent.TButton",
                   command=self.open_file).pack(side="left", padx=6)
        ttk.Button(btns, text="☁ 从云端下载", style="Accent.TButton",
                   command=self.open_cloud).pack(side="left", padx=6)
        ttk.Button(btns, text="查看说明", style="Tool.TButton",
                   command=self.show_help).pack(side="left", padx=6)

        recent = self.cfg.get("recent") or []
        if recent:
            ttk.Label(inner, text="最近打开", font=F_UI_B,
                      foreground=C["dim"]).pack(pady=(28, 6))
            rf = ttk.Frame(inner)
            rf.pack()
            for p in recent[:RECENT_MAX]:
                if not os.path.exists(p):
                    continue
                ttk.Button(rf, text=os.path.basename(p), style="Tool.TButton",
                           command=lambda x=p: self.open_path(x)).pack(pady=2)

    def _bind_keys(self):
        self.bind_all("<Control-o>", lambda e: self.open_file())
        self.bind_all("<Control-s>", lambda e: self.save_zip())
        self.bind_all("<Control-f>", lambda e: self.focus_search())
        self.bind_all("<Control-z>", lambda e: self.do_undo())
        self.bind_all("<Control-y>", lambda e: self.do_redo())
        self.bind_all("<Control-Shift-Z>", lambda e: self.do_redo())

    # ------------------------------------------------------------ 状态
    def _status(self, msg):
        self.status_var.set(msg)

    def touch(self):
        self.dirty = True
        self.dirty_var.set("● 有未保存的修改")
        if not self.title().startswith("*"):
            self.title("*" + self.title())
        self._sync_undo_label()

    def untouch(self):
        self.dirty = False
        self.dirty_var.set("")
        if self.title().startswith("*"):
            self.title(self.title()[1:])
        self._sync_undo_label()

    def _sync_undo_label(self):
        if self.undo.can_undo():
            self.undo_var.set(f"可撤销：{self.undo.next_undo_label()}")
        else:
            self.undo_var.set("")

    # ------------------------------------------------------------ 撤销 / 重做
    def _snapshot(self):
        return {n: copy.deepcopy(v.obj) for n, v in self.views.items()}

    def _restore(self, snap):
        for n, obj in (snap or {}).items():
            v = self.views.get(n)
            if v is not None:
                v.obj = obj
                v.refresh()

    def push_undo(self, label):
        if not self.views:
            return
        self.undo.push(label, self._snapshot())
        self._sync_undo_label()

    def do_undo(self):
        snap = self.undo.undo(self._snapshot())
        if snap is None:
            self._status("没有可撤销的操作")
            return
        self._restore(snap)
        self.touch()
        self._status(f"已撤销：{self.undo.next_redo_label() or '上一步'}")

    def do_redo(self):
        snap = self.undo.redo(self._snapshot())
        if snap is None:
            self._status("没有可重做的操作")
            return
        self._restore(snap)
        self.touch()
        self._status(f"已重做：{self.undo.next_undo_label() or '下一步'}")

    # ------------------------------------------------------------ 打开
    def open_file(self):
        p = filedialog.askopenfilename(
            title="选择 Phigros 存档压缩包",
            filetypes=[("存档压缩包", "*.zip *.save *.txt *.bin"),
                       ("ZIP 文件", "*.zip"), ("所有文件", "*.*")])
        if p:
            self.open_path(p)

    def open_path(self, p):
        self.current_file = p
        self.path_var.set(p)
        self.file_label.set(os.path.basename(p))
        self._add_recent(p)
        self.load()

    def _add_recent(self, p):
        r = [x for x in (self.cfg.get("recent") or []) if x != p]
        r.insert(0, p)
        self.cfg["recent"] = r[:RECENT_MAX]
        paths.save_config(self.cfg)

    def reload(self):
        if self.current_file:
            self.load()
        else:
            self.open_file()

    def load(self):
        path = self.path_var.get().strip()
        if not path:
            return
        try:
            names, entries = load_archive(path)
        except Exception as e:
            messagebox.showerror("打开失败",
                                 f"无法解析：\n{e}\n\n"
                                 "请确认这是 Phigros 云存档 zip"
                                 "（内含 gameRecord 等 5 个无扩展名条目）。")
            return
        try:
            with __import__("zipfile").ZipFile(path) as z:
                self.raw_order = list(z.namelist())
        except Exception:
            self.raw_order = list(names)

        self.names, self.originals = names, entries
        self.undo.clear()
        self.cloud_ctx = None

        objs, bad = {}, []
        for n in names:
            ver, plain, _ = entries[n]
            obj = parse_entry(n, plain)
            if not obj.get("_verified"):
                bad.append(n)
            objs[n] = obj

        self.bad_entries = bad
        self._build_tabs(objs)
        self.untouch()

        msg = f"已载入 {len(names)} 个条目，{len(names) - len(bad)} 个通过逐字节自检"
        if bad:
            msg += f"｜{'、'.join(bad)} 未通过校验"
            self._status(msg)
            messagebox.showwarning(
                "版本兼容提示",
                "以下条目的结构与本工具内置的解析规则不完全匹配，"
                "可能因为游戏版本更新导致格式变化：\n\n  "
                + "、".join(ENTRY_LABEL.get(n, n) for n in bad)
                + "\n\n已启用「原始字节兜底」：保存时这些条目会原样写回，"
                  "因此不会损坏存档，但你在界面上对它们的结构化修改不会生效。")
        else:
            self._status(msg)

    def _build_tabs(self, objs):
        for w in self.nb.winfo_children():
            w.destroy()
        self.views.clear()
        for n in self.names:
            obj = objs.get(n)
            if obj is None:
                continue
            page = ttk.Frame(self.nb)
            self.nb.add(page, text=f"  {ENTRY_LABEL.get(n, n)}  ")
            view = self._make_view(page, n, obj)
            view.pack(fill="both", expand=True)
            self.views[n] = view
            tip = HINTS.get(n, "")
            if n in self.bad_entries:
                tip = "⚠ 该条目未通过结构校验，已启用原始字节兜底（修改不会生效）。 " + tip
            ttk.Label(page, text=tip, font=F_SMALL, foreground=C["dim"],
                      padding=(8, 2)).pack(fill="x", side="bottom")
        self.welcome.pack_forget()
        self.nb.pack(fill="both", expand=True)
        self._sync_undo_label()

    def _make_view(self, page, name, obj):
        if name == "gameRecord":
            return RecordView(page, name, obj, self)
        if name == "gameKey":
            return KeyView(page, name, obj, self)
        if name == "settings":
            return FormView(page, name, obj, self, [("deviceName", "设备名", "str")])
        if name == "user":
            return FormView(page, name, obj, self,
                            [("introduction", "个人简介", "text"),
                             ("avatar", "头像 ID", "str")])
        if name == "gameProgress":
            return FormView(page, name, obj, self,
                            [("challengeRank", "课题分", "int"),
                             ("gameVersion", "游戏版本串", "str")])
        return FormView(page, name, obj, self, [])

    # ------------------------------------------------------------ 保存
    def _collect(self):
        """收集当前各条目的二进制；返回 (plain_map, objs) 或抛 ValueError/异常"""
        plain_map, objs = {}, {}
        for n, v in self.views.items():
            try:
                v.pull()
            except ValueError as e:
                raise ValueError(str(e))
            objs[n] = v.obj
            plain_map[n] = build_entry(n, v.obj)
        return plain_map, objs

    def save_zip(self):
        if not self.views:
            messagebox.showinfo("提示", "请先打开一个存档压缩包")
            return
        try:
            plain_map, objs = self._collect()
        except ValueError as e:
            messagebox.showerror("JSON 错误", str(e))
            return
        except Exception as e:
            messagebox.showerror("结构错误", str(e))
            return

        # 数据矛盾校验
        issues = []
        for n, obj in objs.items():
            for msg in validate_entry(n, obj):
                issues.append(f"{ENTRY_LABEL.get(n, n)}：{msg}")
        if issues:
            show = "\n".join("  · " + x for x in issues[:15])
            more = f"\n  …… 另有 {len(issues) - 15} 条" if len(issues) > 15 else ""
            if not messagebox.askyesno(
                    "数据可能存在矛盾",
                    f"检测到 {len(issues)} 处可疑数据：\n\n{show}{more}\n\n"
                    "仍要保存吗？"):
                self._status("已取消保存")
                return

        # 尾部字节保护
        warn = [n for n in self.names
                if self._orig_tail(n) and (objs[n].get("_tail") is None
                                           or len(objs[n]["_tail"]) != len(self._orig_tail(n)))]
        if warn and not messagebox.askyesno(
                "尾部字节被改动",
                "以下条目的 _tail（未能确定语义的原始字节）被删除或长度改变：\n  "
                + "、".join(ENTRY_LABEL.get(n, n) for n in warn)
                + "\n\n这通常会导致存档异常，确定仍要保存吗？"):
            self._status("已取消保存")
            return

        changed = [n for n in self.names if plain_map[n] != self.originals[n][1]]
        base = os.path.splitext(os.path.basename(self.current_file or "save"))[0]
        out = filedialog.asksaveasfilename(
            defaultextension=".zip", initialfile=f"{base}_edited.zip",
            filetypes=[("ZIP 压缩包", "*.zip")])
        if not out:
            return
        order = self.raw_order or self.names
        try:
            save_archive(out, order, self.originals, plain_map)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return
        self.untouch()
        what = "、".join(ENTRY_LABEL.get(n, n) for n in changed) or "（无内容变化）"
        self._status(f"已保存：{out}　本次改动：{what}")
        messagebox.showinfo("保存成功",
                            f"已导出：\n{out}\n\n改动条目：{what}\n\n"
                            "文件与原版结构一致（同条目名、同版本号字节、AES-256-CBC 加密）。")

    def _orig_tail(self, name):
        return parse_entry(name, self.originals[name][1]).get("_tail")

    # ------------------------------------------------------------ 导入导出
    def export_all(self):
        if not self.views:
            messagebox.showinfo("提示", "请先打开一个存档压缩包")
            return
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                         initialfile="phigros_save.json",
                                         filetypes=[("JSON", "*.json")])
        if not p:
            return
        data = {}
        for n, v in self.views.items():
            try:
                v.pull()
            except ValueError as e:
                messagebox.showerror("JSON 错误", str(e))
                return
            data[n] = v.obj
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._status(f"已导出全部 JSON：{p}")

    def import_json(self):
        if not self.views:
            messagebox.showinfo("提示", "请先打开一个存档压缩包")
            return
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        self.push_undo("导入 JSON")
        n_imp = 0
        for n, obj in data.items():
            v = self.views.get(n)
            if v:
                v.obj = obj
                v.refresh()
                n_imp += 1
        self.touch()
        self._status(f"已从 {os.path.basename(p)} 导入 {n_imp} 个条目")

    # ------------------------------------------------------------ 其它
    def focus_search(self):
        v = self.views.get("gameRecord")
        if not v:
            return
        self.nb.select(list(self.views).index("gameRecord"))
        if hasattr(v, "search_entry"):
            v.search_entry.focus_set()
            v.search_entry.select_range(0, "end")

    def open_data_dir(self):
        try:
            if sys.platform == "win32":
                os.startfile(paths.DATA_DIR)
            else:
                import subprocess
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open",
                                  paths.DATA_DIR])
        except Exception:
            pass
        self._status(f"数据目录：{paths.DATA_DIR}")

    def open_unlock(self):
        if not self.views:
            messagebox.showinfo("提示", "请先打开一个存档")
            return
        UnlockDialog(self).grab_set()

    def open_cloud(self):
        """云存档窗口复用同一实例：关闭只是隐藏，连接状态保留"""
        dlg = self.cloud_dlg
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.deiconify()
                    dlg.lift()
                    try:
                        dlg.focus_set()
                        dlg.grab_set()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
        self.cloud_dlg = CloudDialog(self)
        try:
            self.cloud_dlg.grab_set()
        except Exception:
            pass

    def _refresh_cloud_btn(self):
        """工具栏按钮上用 ● 表示云端仍处于连接状态"""
        b = getattr(self, "cloud_btn", None)
        if b is None:
            return
        try:
            b.configure(text="☁ 云存档 ●" if self.cloud_user else "☁ 云存档")
        except Exception:
            pass

    def close_cloud(self):
        """真正断开：销毁云存档窗口并清空会话（程序退出时调用）"""
        dlg = self.cloud_dlg
        if dlg is not None:
            try:
                dlg.destroy()
            except Exception:
                pass
        self.cloud_dlg = None
        self.cloud_user = None
        self.cloud_token = ""
        self.cloud_server = ""
        self.cloud_saves = []
        self.cloud_meta = None
        self.cloud_ctx = None
        self._refresh_cloud_btn()

    def on_close(self):
        if self.dirty and not messagebox.askyesno("未保存", "有未保存的修改，确定退出吗？"):
            return
        self.close_cloud()
        self.destroy()

    def show_help(self):
        messagebox.showinfo(
            "使用说明",
            "【流程】打开存档 → 在表格/表单里改 → 保存为存档压缩包\n\n"
            "【曲目成绩】双击单元格直接修改；右键有「设为 φ」「全部 FC」；\n"
            "顶部可搜索、按难度筛选、点列名排序（▲升序 / ▼降序）；\n"
            "「批量修改」可一次改完筛选出的所有成绩。\n\n"
            "【解锁数据】双击改 flags（十六进制），或选中多行「复制同类项 flags」。\n\n"
            "【设置 / 资料 / 进度】表单直接填，点「应用修改」。\n\n"
            "【撤销重做】Ctrl+Z 撤销、Ctrl+Y 重做，支持多步。\n\n"
            "【强制解锁】工具栏「🔓 强制解锁」可批量置解锁标记、补全曲目条目、\n"
            "为未打过的曲目补写成绩；改动可用 Ctrl+Z 一次撤销。\n\n"
            "【云存档】填 sessionToken（可从 .userdata 导入）即可拉取与上传；\n"
            "上传前会自动备份到数据目录。\n\n"
            "【主题】工具栏「◐ 主题」或菜单「视图」可切换浅色/深色/跟随系统。\n\n"
            f"数据目录（配置、备份）：\n{paths.DATA_DIR}\n\n"
            "⚠ 修改存档违反游戏用户协议，存在封号与损坏风险，请先备份原始文件。")
