# -*- coding: utf-8 -*-
"""云存档窗口：连接账号、拉取/上传云端存档，并管理本地存档与备份。"""

import hashlib
import os
import re
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import phigros_cloud as cloud
import phi_files as files
import phi_paths as paths
from phi_format import build_entry, build_zip_bytes
from phi_theme import C, F_UI, F_UI_B, F_SMALL, F_MONO, register_text


class CloudDialog(tk.Toplevel):
    """云存档：拉取 / 上传"""

    CFG = "cloud_config.json"

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("云存档 · 本地与备份")
        self.transient(app)
        paths.apply_icon(self)
        self.configure(background=C["bg"])
        self._fit()

        self.cfg = paths.load_config()
        self.user = None
        self.saves = []
        self.meta = None
        self.local_items = []
        self.backup_items = []
        self._restoring = False

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self.refresh_local()
        self.refresh_backups()
        # 凭证一旦被改动，旧连接立即失效
        self.tk_var.trace_add("write", lambda *a: self._on_cred_change())
        self.srv_var.trace_add("write", lambda *a: self._on_cred_change())
        if not self._restore_session() and self.cfg.get("token"):
            self._log("已载入上次的 sessionToken，点「连接」试试。")

    # ---------- 连接状态的保持 ----------
    def _on_close(self):
        """关闭窗口只是隐藏，连接状态保留到程序退出"""
        try:
            self.grab_release()
        except Exception:
            pass
        self.withdraw()
        if self.user:
            self._log("窗口已隐藏（连接保持）。点工具栏「☁ 云存档」可再次打开。")

    def _restore_session(self):
        """恢复主窗口上保存的连接状态，无需重新点「连接」"""
        app = self.app
        u = getattr(app, "cloud_user", None)
        if not u:
            return False
        self._restoring = True
        try:
            return self._do_restore(u)
        finally:
            self._restoring = False

    def _do_restore(self, u):
        app = self.app
        self.user = u
        self.saves = list(getattr(app, "cloud_saves", None) or [])
        self.meta = getattr(app, "cloud_meta", None)
        self.tk_var.set(getattr(app, "cloud_token", "") or self.cfg.get("token", ""))
        self.srv_var.set(getattr(app, "cloud_server", "") or self.cfg.get("server", "国服"))
        nick = u.get("nickname") or u.get("username")
        self.acct.set(f"已连接：{nick}　ID {u.get('objectId')}")
        self._log(f"已恢复上次连接：{nick}（程序退出前保持）")
        self._show_cloud()
        try:
            self.app._refresh_cloud_btn()
        except Exception:
            pass
        return True

    def _remember(self, token):
        """把当前连接记到主窗口上"""
        app = self.app
        app.cloud_user = self.user
        app.cloud_token = token
        app.cloud_server = self.srv_var.get()      # 存区服名，便于比对
        app.cloud_saves = self.saves
        app.cloud_meta = self.meta
        try:
            app._refresh_cloud_btn()
        except Exception:
            pass

    def _forget(self, why=""):
        app = self.app
        app.cloud_user = None
        app.cloud_token = ""
        app.cloud_server = ""
        app.cloud_saves = []
        app.cloud_meta = None
        app.cloud_ctx = None
        self.user = None
        self.saves = []
        self.meta = None
        self.acct.set("未连接")
        self.cloud_line1.set("未连接")
        self.cloud_line2.set("")
        self.cloud_line3.set("")
        try:
            app._refresh_cloud_btn()
        except Exception:
            pass
        if why:
            self._log(why)

    def _on_cred_change(self):
        """token/区服被改动 → 旧连接失效"""
        app = self.app
        if getattr(self, "_restoring", False):
            return
        if not getattr(app, "cloud_user", None):
            return
        if (self.tk_var.get().strip() != app.cloud_token
                or self.srv_var.get() != app.cloud_server):
            self._forget("凭证已修改，连接已断开，请重新点「连接」。")

    def _show_cloud(self):
        """把 self.meta 渲染到云端单条展示区"""
        m = self.meta
        if not m:
            self.cloud_line1.set("云端没有存档")
            self.cloud_line2.set("")
            self.cloud_line3.set("")
            return
        su = cloud.decode_summary(m.get("summary") or "")
        upd = (m.get("updatedAt") or "").replace("T", " ").replace("Z", "")
        self.cloud_line1.set(
            f"更新时间 {upd or '-'}　大小 {m.get('size')} B　"
            f"共 {len(self.saves)} 份记录")
        line2 = f"存档 ID：{m.get('saveObjectId')}　文件 ID：{m.get('fileObjectId')}"
        if m.get("modifiedAt"):
            line2 += ("　存档修改时间："
                      + m["modifiedAt"].replace("T", " ").replace("Z", ""))
        self.cloud_line2.set(line2)
        if su:
            lr = su.get("levelRecords", {})
            txt = (f"RKS：{su.get('rks', 0):.4f}　"
                   f"课题等级：{su.get('challengeRank')}　"
                   f"游戏版本：{su.get('gameVersion')}　"
                   f"头像：{su.get('avatar') or '（默认）'}")
            if lr:
                txt += "\n计数：" + "　".join(f"{k}×{v}" for k, v in lr.items() if v)
            self.cloud_line3.set(txt)
        else:
            self.cloud_line3.set("（summary 无法解析）")

    # ---------- 配置 ----------
    def _save_cfg(self):
        paths.save_config(self.cfg)

    # ---------- 界面 ----------
    def _fit(self):
        """按屏幕自适应尺寸并居中到父窗口，避免默认显示不全"""
        w, h = 900, 760
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w = max(760, min(w, sw - 80))
            h = max(600, min(h, sh - 60))
        except Exception:
            pass
        self.minsize(720, 620)
        self.geometry(f"{w}x{h}")
        try:
            self.update_idletasks()
            px = self.app.winfo_rootx()
            py = self.app.winfo_rooty()
            pw = self.app.winfo_width() or w
            ph = self.app.winfo_height() or h
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        except Exception:
            pass

    def _build(self):
        # ============ 账号（固定高度，输入区可伸缩）============
        top = ttk.LabelFrame(self, style="Card.TLabelframe", text="账号", padding=14)
        top.pack(fill="x", padx=14, pady=(14, 8))
        top.grid_columnconfigure(1, weight=1)      # token 输入框占据剩余宽度

        ttk.Label(top, text="sessionToken", font=F_UI).grid(
            row=0, column=0, sticky="e", padx=(0, 8))
        self.tk_var = tk.StringVar(value=self.cfg.get("token", ""))
        e = ttk.Entry(top, textvariable=self.tk_var, font=F_MONO, show="•")
        e.grid(row=0, column=1, sticky="ew")

        self.show_tk = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="显示", variable=self.show_tk,
                        command=lambda: e.configure(
                            show="" if self.show_tk.get() else "•")
                        ).grid(row=0, column=2, padx=(10, 0))

        ttk.Label(top, text="区服", font=F_UI).grid(row=0, column=3, sticky="e", padx=(16, 6))
        self.srv_var = tk.StringVar(value=self.cfg.get("server", "国服"))
        ttk.Combobox(top, textvariable=self.srv_var, values=list(cloud.SERVERS),
                     state="readonly", width=8, font=F_UI).grid(row=0, column=4)

        ttk.Button(top, text="连接", style="Accent.TButton",
                   command=self.connect).grid(row=0, column=5, padx=(16, 0))
        ttk.Button(top, text="从 .userdata 导入", style="Tool.TButton",
                   command=self.import_userdata).grid(row=0, column=6, padx=(8, 0))

        self.acct = tk.StringVar(value="未连接")
        ttk.Label(top, textvariable=self.acct, font=F_UI_B,
                  foreground=C["accent"]).grid(row=1, column=0, columnspan=7,
                                            sticky="w", pady=(10, 0))

        # ============ 云端存档（单条，云端本来就只有一份）============
        mid = ttk.LabelFrame(self, style="Card.TLabelframe", text="云端存档", padding=14)
        mid.pack(fill="x", padx=14, pady=6)

        self.cloud_line1 = tk.StringVar(value="未连接")
        ttk.Label(mid, textvariable=self.cloud_line1, font=F_UI_B,
                  anchor="w").pack(fill="x")
        self.cloud_line2 = tk.StringVar(value="")
        ttk.Label(mid, textvariable=self.cloud_line2, font=F_SMALL,
                  foreground=C["dim"], anchor="w", justify="left"
                  ).pack(fill="x", pady=(4, 0))
        self.cloud_line3 = tk.StringVar(value="")
        self.lab3 = ttk.Label(mid, textvariable=self.cloud_line3, font=F_SMALL,
                              foreground=C["dim"], anchor="w", justify="left")
        self.lab3.pack(fill="x")
        mid.bind("<Configure>", self._on_resize)

        btns = ttk.Frame(mid)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="⬇ 下载并打开", style="Accent.TButton",
                   command=self.download).pack(side="left")
        ttk.Button(btns, text="⬆ 上传到云端", style="Accent.TButton",
                   command=self.upload).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="刷新", style="Tool.TButton",
                   command=self.refresh).pack(side="left", padx=(8, 0))
        ttk.Label(btns, text="上传时按成绩重算 summary 计数",
                  font=F_SMALL, foreground=C["dim"]).pack(side="left", padx=(16, 0))

        # ============ 本地存档 / 备份（吸收剩余空间）============
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=14, pady=(10, 6))

        # ---- 本地存档 ----
        tab_local = ttk.Frame(nb, style="Card.TFrame")
        nb.add(tab_local, text="本地存档")
        self._build_list(tab_local, "local",
                         ("name", "src", "size", "time"),
                         [("name", "文件名", 300, "w", True),
                          ("src", "来源", 90, "center", False),
                          ("size", "大小", 84, "center", False),
                          ("time", "修改时间", 150, "center", False)],
                         [("⬆ 载入编辑器", self.load_local, True),
                          ("📂 打开所在文件夹", self.show_local, False),
                          ("刷新", self.refresh_local, False)],
                         "双击一行可直接载入")

        # ---- 备份 ----
        tab_bak = ttk.Frame(nb, style="Card.TFrame")
        nb.add(tab_bak, text="备份")
        self._build_list(tab_bak, "bak",
                         ("kind", "name", "size", "time"),
                         [("kind", "类型", 130, "w", False),
                          ("name", "文件名", 250, "w", True),
                          ("size", "大小", 84, "center", False),
                          ("time", "时间", 150, "center", False)],
                         [("⬆ 载入编辑器", self.load_backup, True),
                          ("💾 另存为…", self.save_backup_as, False),
                          ("✕ 删除", self.delete_backup, False),
                          ("＋ 备份当前存档", self.backup_current, False)],
                         "双击一行载入编辑器 → 上方「上传当前存档到云端」即可回传；"
                         "上传时会自动再备份一次")

        # ============ 日志（固定高度）============
        bot = ttk.LabelFrame(self, style="Card.TLabelframe", text="日志", padding=10)
        bot.pack(fill="x", padx=14, pady=(6, 14))
        self.log = scrolledtext.ScrolledText(bot, height=5, font=F_MONO,
                                             wrap="word", relief="flat",
                                             bg=C["card"], fg=C["text"])
        self.log.pack(fill="both", expand=True)
        bot = ttk.LabelFrame(self, style="Card.TLabelframe", text="日志", padding=10)
        bot.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.log = scrolledtext.ScrolledText(bot, height=6, font=F_MONO,
                                             wrap="word", relief="flat",
                                             bg=C["card"], fg=C["text"])
        self.log.pack(fill="both", expand=True)

    def _build_list(self, parent, key, cols, heads, buttons, hint=""):
        """通用列表：Treeview + 滚动条 + 一行按钮"""
        tip = ttk.Label(parent, text=hint, font=F_SMALL, foreground=C["dim"])
        tip.pack(anchor="w", padx=(2, 0), pady=(8, 6))

        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        tv = ttk.Treeview(wrap, columns=cols, show="headings", height=6)
        for c, t, w, anchor, stretch in heads:
            tv.heading(c, text=t)
            tv.column(c, width=w, minwidth=70, anchor=anchor, stretch=stretch)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        setattr(self, f"tv_{key}", tv)
        tv.bind("<Double-1>", lambda ev, k=key: self._load_selected(k))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(8, 0))
        for label, cmd, accent in buttons:
            style = "Accent.TButton" if accent else "Tool.TButton"
            if accent:
                ttk.Button(bar, text=label, style=style, command=cmd).pack(side="left")
            else:
                ttk.Button(bar, text=label, style=style, command=cmd).pack(side="left", padx=(8, 0))

    # 列表 key -> 数据列表属性名
    _LIST_DATA = {"local": "local_items", "bak": "backup_items"}

    def _sel(self, key):
        """返回当前选中项在数据列表里的 dict，没有则 None"""
        tv = getattr(self, f"tv_{key}", None)
        items = getattr(self, self._LIST_DATA.get(key, f"{key}_items"), None)
        if tv is None or not items:
            return None
        sel = tv.selection()
        if not sel:
            return None
        try:
            return items[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _load_selected(self, key):
        it = self._sel(key)
        if it:
            self._open_path(it["path"])

    def _open_path(self, path):
        if not os.path.exists(path):
            messagebox.showerror("打开失败", f"文件不存在：\n{path}")
            return
        self.app.path_var.set(path)
        self.app.load()
        self._log(f"已载入：{os.path.basename(path)}")

    # ---------- 本地存档 ----------
    def refresh_local(self):
        self.local_items = files.scan_local(self.cfg)
        tv = self.tv_local
        tv.delete(*tv.get_children())
        for i, it in enumerate(self.local_items):
            tv.insert("", "end", iid=str(i), values=(
                it["name"], it["source"], it["shown_size"], it["shown_time"]))
        if not self.local_items:
            tv.insert("", "end", iid="0", values=(
                "（暂无，下载或打开存档后会出现在这里）", "", "", ""))
        self._log(f"本地存档 {len(self.local_items)} 份")

    def load_local(self):
        it = self._sel("local")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        self._open_path(it["path"])

    def show_local(self):
        it = self._sel("local")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        if not files.open_in_folder(it["path"]):
            messagebox.showinfo("路径", it["dir"])

    # ---------- 备份 ----------
    def refresh_backups(self):
        self.backup_items = files.scan_backups()
        tv = self.tv_bak
        tv.delete(*tv.get_children())
        for i, it in enumerate(self.backup_items):
            tv.insert("", "end", iid=str(i), values=(
                it["kind"], it["name"], it["shown_size"], it["shown_time"]))
        if not self.backup_items:
            tv.insert("", "end", iid="0", values=("（暂无备份）", "", "", ""))

    def load_backup(self):
        it = self._sel("bak")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        self._open_path(it["path"])

    def save_backup_as(self):
        it = self._sel("bak")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        p = filedialog.asksaveasfilename(
            title="备份另存为", defaultextension=".zip",
            initialfile=it["name"],
            filetypes=[("ZIP 存档", "*.zip"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            import shutil
            shutil.copyfile(it["path"], p)
            self._log(f"已另存：{p}")
        except Exception as ex:
            messagebox.showerror("失败", str(ex))

    def delete_backup(self):
        it = self._sel("bak")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        if not messagebox.askyesno("确认删除",
                                   f"删除备份「{it['name']}」？\n此操作不可撤销。"):
            return
        try:
            os.remove(it["path"])
            self._log(f"已删除备份：{it['name']}")
            self.refresh_backups()
        except Exception as ex:
            messagebox.showerror("删除失败", str(ex))

    def backup_current(self):
        if not self.app.views:
            messagebox.showinfo("提示", "请先打开（或下载）一份存档")
            return
        try:
            data = self._current_bytes()
        except Exception:
            return
        try:
            p = files.make_backup(data)
            self._log(f"已备份当前存档：{os.path.basename(p)}")
            self.refresh_backups()
        except Exception as ex:
            messagebox.showerror("备份失败", str(ex))

    def _current_bytes(self):
        """把当前编辑内容打包成 zip 字节；JSON 有错会抛异常"""
        plain_map = {}
        for n, v in self.app.views.items():
            try:
                v.pull()
            except ValueError as ex:
                messagebox.showerror("JSON 错误", str(ex))
                raise
            try:
                plain_map[n] = build_entry(n, v.obj)
            except Exception as ex:
                messagebox.showerror("结构错误", f"{n} 无法重建：{ex}")
                raise
        order = getattr(self.app, "raw_order", None) or self.app.names
        return build_zip_bytes(order, self.app.originals, plain_map)

    def _on_resize(self, ev=None):
        """保持详情文字随窗口宽度换行，不出现横向截断"""
        try:
            w = self.lab3.winfo_width()
            if w > 40:
                self.lab3.configure(wraplength=w - 4)
        except Exception:
            pass

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.update_idletasks()

    def _server(self):
        return cloud.SERVERS[self.srv_var.get()]

    # ---------- 连接 ----------
    def connect(self):
        token = self.tk_var.get().strip()
        if len(token) != 25 or not token.isalnum():
            if not messagebox.askyesno("提示", "sessionToken 通常应为 25 位字母数字。\n仍要尝试连接吗？"):
                return
        self.cfg["token"] = token
        self.cfg["server"] = self.srv_var.get()
        self._save_cfg()
        try:
            self._log("连接中…")
            self.user = cloud.get_user(token, self._server())
            self._log(f"登录成功：{self.user.get('nickname') or self.user.get('username')}"
                      f"  (ID {self.user.get('objectId')})")
            self.acct.set(f"已连接：{self.user.get('nickname') or self.user.get('username')}"
                          f"　ID {self.user.get('objectId')}")
            self.refresh()
            self._remember(token)
            self.refresh_local()
            self.refresh_backups()
        except Exception as ex:
            self._log(f"连接失败：{ex}")
            messagebox.showerror("连接失败", str(ex))

    def import_userdata(self):
        p = filedialog.askopenfilename(title="选择 .userdata 文件",
                                       filetypes=[("userdata", "*.userdata"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
            m = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', txt)
            if not m:
                raise ValueError("未在文件中找到 sessionToken")
            self.tk_var.set(m.group(1))
            self._log("已从 .userdata 读取 sessionToken。")
        except Exception as ex:
            messagebox.showerror("导入失败", str(ex))

    def refresh(self):
        """云端只有一份存档，直接取第一条展示，不做列表"""
        if not self.user:
            messagebox.showinfo("提示", "请先点「连接」")
            return
        try:
            self.saves = cloud.list_saves(self.tk_var.get().strip(), self._server(),
                                          self.user["objectId"])
            self.meta = cloud.save_meta(self.saves[0]) if self.saves else None
            self.app.cloud_saves = self.saves
            self.app.cloud_meta = self.meta
            self._show_cloud()
            upd = (self.meta.get("updatedAt") or "") if self.meta else ""
            self._log(f"已读取云端存档：{upd}" if self.meta else "云端没有存档记录")
        except Exception as ex:
            self._log(f"查询失败：{ex}")
            messagebox.showerror("查询失败", str(ex))

    # ---------- 本地存档 ----------
    def refresh_local(self):
        self.local_items = files.scan_local(self.cfg)
        tv = self.tv_local
        tv.delete(*tv.get_children())
        for i, it in enumerate(self.local_items):
            tv.insert("", "end", iid=str(i), values=(
                it["name"], it["source"], it["shown_size"], it["shown_time"]))
        if not self.local_items:
            tv.insert("", "end", iid="0", values=(
                "（暂无，下载或打开存档后会出现在这里）", "", "", ""))
        self._log(f"本地存档 {len(self.local_items)} 份")

    def load_local(self):
        it = self._sel("local")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        self._open_path(it["path"])

    def show_local(self):
        it = self._sel("local")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        if not files.open_in_folder(it["path"]):
            messagebox.showinfo("路径", it["dir"])

    # ---------- 备份 ----------
    def refresh_backups(self):
        self.backup_items = files.scan_backups()
        tv = self.tv_bak
        tv.delete(*tv.get_children())
        for i, it in enumerate(self.backup_items):
            tv.insert("", "end", iid=str(i), values=(
                it["kind"], it["name"], it["shown_size"], it["shown_time"]))
        if not self.backup_items:
            tv.insert("", "end", iid="0", values=("（暂无备份）", "", "", ""))

    def load_backup(self):
        it = self._sel("bak")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        self._open_path(it["path"])

    def save_backup_as(self):
        it = self._sel("bak")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        p = filedialog.asksaveasfilename(
            title="备份另存为", defaultextension=".zip",
            initialfile=it["name"],
            filetypes=[("ZIP 存档", "*.zip"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            import shutil
            shutil.copyfile(it["path"], p)
            self._log(f"已另存：{p}")
        except Exception as ex:
            messagebox.showerror("失败", str(ex))

    def delete_backup(self):
        it = self._sel("bak")
        if not it:
            messagebox.showinfo("提示", "请先选择一行")
            return
        if not messagebox.askyesno("确认删除",
                                   f"删除备份「{it['name']}」？\n此操作不可撤销。"):
            return
        try:
            os.remove(it["path"])
            self._log(f"已删除备份：{it['name']}")
            self.refresh_backups()
        except Exception as ex:
            messagebox.showerror("删除失败", str(ex))

    def backup_current(self):
        if not self.app.views:
            messagebox.showinfo("提示", "请先打开（或下载）一份存档")
            return
        try:
            data = self._current_bytes()
        except Exception:
            return
        try:
            p = files.make_backup(data)
            self._log(f"已备份当前存档：{os.path.basename(p)}")
            self.refresh_backups()
        except Exception as ex:
            messagebox.showerror("备份失败", str(ex))

    def _current_bytes(self):
        """把当前编辑内容打包成 zip 字节；JSON 有错会抛异常"""
        plain_map = {}
        for n, v in self.app.views.items():
            try:
                v.pull()
            except ValueError as ex:
                messagebox.showerror("JSON 错误", str(ex))
                raise
            try:
                plain_map[n] = build_entry(n, v.obj)
            except Exception as ex:
                messagebox.showerror("结构错误", f"{n} 无法重建：{ex}")
                raise
        order = getattr(self.app, "raw_order", None) or self.app.names
        return build_zip_bytes(order, self.app.originals, plain_map)

    def _on_resize(self, ev=None):
        """保持详情文字随窗口宽度换行，不出现横向截断"""
        try:
            w = self.lab3.winfo_width()
            if w > 40:
                self.lab3.configure(wraplength=w - 4)
        except Exception:
            pass

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.update_idletasks()

    def _server(self):
        return cloud.SERVERS[self.srv_var.get()]

    # ---------- 连接 ----------
    def connect(self):
        token = self.tk_var.get().strip()
        if len(token) != 25 or not token.isalnum():
            if not messagebox.askyesno("提示", "sessionToken 通常应为 25 位字母数字。\n仍要尝试连接吗？"):
                return
        self.cfg["token"] = token
        self.cfg["server"] = self.srv_var.get()
        self._save_cfg()
        try:
            self._log("连接中…")
            self.user = cloud.get_user(token, self._server())
            self._log(f"登录成功：{self.user.get('nickname') or self.user.get('username')}"
                      f"  (ID {self.user.get('objectId')})")
            self.acct.set(f"已连接：{self.user.get('nickname') or self.user.get('username')}"
                          f"　ID {self.user.get('objectId')}")
            self.refresh()
            self._remember(token)
            self.refresh_local()
            self.refresh_backups()
        except Exception as ex:
            self._log(f"连接失败：{ex}")
            messagebox.showerror("连接失败", str(ex))

    def import_userdata(self):
        p = filedialog.askopenfilename(title="选择 .userdata 文件",
                                       filetypes=[("userdata", "*.userdata"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
            m = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', txt)
            if not m:
                raise ValueError("未在文件中找到 sessionToken")
            self.tk_var.set(m.group(1))
            self._log("已从 .userdata 读取 sessionToken。")
        except Exception as ex:
            messagebox.showerror("导入失败", str(ex))

    def refresh(self):
        """云端只有一份存档，直接取第一条展示，不做列表"""
        if not self.user:
            messagebox.showinfo("提示", "请先点「连接」")
            return
        try:
            self.saves = cloud.list_saves(self.tk_var.get().strip(), self._server(),
                                          self.user["objectId"])
            if not self.saves:
                self.meta = None
                self.cloud_line1.set("云端没有存档")
                self.cloud_line2.set("")
                self.cloud_line3.set("")
                self._log("云端没有存档记录")
                return
            self.meta = cloud.save_meta(self.saves[0])
            su = cloud.decode_summary(self.meta["summary"] or "")
            m = self.meta
            upd = (m["updatedAt"] or "").replace("T", " ").replace("Z", "")
            self.cloud_line1.set(
                f"更新时间 {upd or '-'}　"
                f"大小 {m['size']} B　"
                f"共 {len(self.saves)} 份记录")
            line2 = f"存档 ID：{m['saveObjectId']}　文件 ID：{m['fileObjectId']}"
            if m.get("modifiedAt"):
                line2 += f"　存档修改时间：{m['modifiedAt'].replace('T', ' ').replace('Z', '')}"
            self.cloud_line2.set(line2)
            if su:
                lr = su.get("levelRecords", {})
                txt = (f"RKS：{su.get('rks', 0):.4f}　"
                       f"课题等级：{su.get('challengeRank')}　"
                       f"游戏版本：{su.get('gameVersion')}　"
                       f"头像：{su.get('avatar') or '（默认）'}")
                if lr:
                    txt += "\n计数：" + "　".join(f"{k}×{v}" for k, v in lr.items() if v)
                self.cloud_line3.set(txt)
            else:
                self.cloud_line3.set("（summary 无法解析）")
            self._log(f"已读取云端存档：{upd}")
        except Exception as ex:
            self._log(f"查询失败：{ex}")
            messagebox.showerror("查询失败", str(ex))

    # ---------- 下载 ----------
    def download(self):
        if not self.meta or not self.meta.get("url"):
            messagebox.showinfo("提示", "请先选择一份云端存档")
            return
        try:
            self._log("下载中…")
            data = cloud.download(self.meta["url"])
            self._log(f"已下载 {len(data)} 字节，md5={hashlib.md5(data).hexdigest()}")
            if self.meta.get("checksum"):
                ok = hashlib.md5(data).hexdigest() == self.meta["checksum"]
                self._log("校验：" + ("一致 ✔" if ok else "不一致 ✘（仍会载入）"))
            tmp = os.path.join(paths.DOWNLOAD_DIR, "cloud_latest.save")
            open(tmp, "wb").write(data)
            self.app.path_var.set(tmp)
            self.app.load()
            self.app.cloud_ctx = {
                "token": self.tk_var.get().strip(),
                "server": self._server(),
                "user_id": self.user["objectId"],
                "save_object_id": self.meta["saveObjectId"],
                "file_object_id": self.meta["fileObjectId"],
                "summary": self.meta["summary"],
            }
            self.refresh_local()
            self.app.cloud_meta = self.meta
            self._log("已载入到编辑器，可直接修改后上传。")
            messagebox.showinfo("完成", "云端存档已载入编辑器。\n改完点「上传当前存档到云端」回传。")
        except Exception as ex:
            self._log(f"下载失败：{ex}")
            messagebox.showerror("下载失败", str(ex))

    def _backup_local(self, bd, stamp):
        """退而求其次：备份当前打开的文件"""
        p = self.app.path_var.get()
        if p and os.path.isfile(p):
            open(os.path.join(bd, f"before_upload_{stamp}.zip"), "wb").write(
                open(p, "rb").read())
            self._log("已备份本地当前文件")

    def _upload_target(self):
        """确定上传目标。

        云端只有一份存档，所以只要连着，就能拿到它的 ID ——
        不需要「必须先下载才能上传」。备份、抓包、本地改动过的存档
        都可以直接上传，覆盖云端那唯一一份。
        """
        token = self.tk_var.get().strip()
        cur = getattr(self.app, "cloud_ctx", None)
        if cur and cur.get("save_object_id"):
            cur["token"] = token
            cur["server"] = self._server()
            cur["user_id"] = self.user["objectId"]
            return cur
        # 没有下载上下文：用连接后查到的云端存档
        if not self.meta:
            try:
                self.refresh()
            except Exception:
                pass
        if not self.meta:
            messagebox.showwarning(
                "无法上传",
                "还没拿到云端存档信息。\n"
                "请先点「连接」，确认上方能显示出云端存档后再上传。")
            return None
        m = self.meta
        return {"token": token, "server": self._server(),
                "user_id": self.user["objectId"],
                "save_object_id": m["saveObjectId"],
                "file_object_id": m["fileObjectId"],
                "summary": m["summary"]}

    # ---------- 上传 ----------
    def upload(self):
        if not self.app.views:
            messagebox.showinfo("提示", "请先打开（或下载）一份存档")
            return
        if not self.user:
            messagebox.showinfo("提示", "请先点「连接」")
            return
        ctx = self._upload_target()
        if not ctx:
            return

        # 生成存档字节
        try:
            data = self._current_bytes()
        except Exception:
            return

        summary = ctx["summary"]
        su = cloud.decode_summary(summary or "")
        if su:
            su["levelRecords"] = cloud.recalc_level_records(
                self.app.views["gameRecord"].obj.get("records"))
            gp = self.app.views.get("gameProgress")
            if gp:
                su["challengeRank"] = int(
                    gp.obj.get("challengeRank", su.get("challengeRank", 0)))
            summary = cloud.encode_summary(su)
            self._log("已按当前成绩重算 summary 计数（RKS 保留原值，需游戏端刷新）。")

        # 强制本地备份：云端原档 + 本次上传内容
        bd = paths.BACKUP_DIR
        stamp = time.strftime("%Y%m%d_%H%M%S")
        try:
            # ① 云端原档：真的去下载，这样回滚才有意义
            url = (self.meta or {}).get("url")
            if url:
                try:
                    before = cloud.download(url)
                    open(os.path.join(bd, f"cloud_before_{stamp}.zip"), "wb").write(before)
                    self._log(f"已备份云端原档 {len(before)} 字节")
                except Exception as ex:
                    self._log(f"云端原档下载失败（{ex}），改为备份本地当前文件")
                    self._backup_local(bd, stamp)
            else:
                self._backup_local(bd, stamp)
            # ② 本次上传内容
            open(os.path.join(bd, f"uploaded_{stamp}.zip"), "wb").write(data)
            self._log(f"已备份本次内容到 {bd}（{stamp}）")
        except Exception as ex:
            self._log(f"备份失败（已中止上传）：{ex}")
            messagebox.showerror("备份失败", f"为安全起见已中止上传：\n{ex}")
            return

        src = os.path.basename(self.app.path_var.get() or "（未命名）")
        if not messagebox.askyesno(
                "确认上传",
                f"将把当前编辑的存档上传到云端，覆盖云端现有存档。\n\n"
                f"来源：{src}\n"
                f"大小：{len(data)} 字节\n"
                f"目标存档 ID：{ctx['save_object_id']}\n"
                f"上传前已备份到：{paths.BACKUP_DIR}\n\n"
                f"云端旧档与本次内容都会留备份，可随时回滚。确定继续吗？"):
            self._log("已取消上传")
            return

        try:
            up = cloud.Uploader(ctx["token"], ctx["server"], ctx["user_id"],
                                progress=lambda m: self._log("  " + m))
            res = up.upload(data, summary, ctx["save_object_id"], ctx["file_object_id"])
            self._log(f"上传成功：{res}")
            # 文件 ID 每次上传都会变，同步回各处，下次才能继续上传
            ctx["file_object_id"] = res["fileObjectId"]
            if self.meta:
                self.meta["fileObjectId"] = res["fileObjectId"]
            cur = getattr(self.app, "cloud_ctx", None)
            if cur:
                cur["file_object_id"] = res["fileObjectId"]
            self.app.cloud_meta = self.meta
            self.refresh_backups()
            messagebox.showinfo("上传成功",
                                f"已上传到云端（{res['size']} 字节）。\n"
                                "请在游戏中重新同步云存档查看效果。")
            self.refresh()
        except Exception as ex:
            self._log(f"上传失败：{ex}")
            messagebox.showerror("上传失败", str(ex))
