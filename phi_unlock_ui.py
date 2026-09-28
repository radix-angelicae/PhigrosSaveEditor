# -*- coding: utf-8 -*-
"""强制解锁 —— 按章节展开，自动补齐前置曲目。

规则：章节内第 N 首解锁的前提是第 1~N-1 首都在同一难度达到 880000(A)。
所以选中第 N 首时，会自动把前面的曲子一并纳入解锁计划。
"""

import tkinter as tk
from tkinter import messagebox, ttk

import phi_chapters as CH
import phi_paths as paths
import phi_unlock as U
from phi_theme import C, F_UI, F_UI_B, F_SMALL, F_MONO


def _patch_tail(tail: bytes, ver: str):
    """把参考尾部末尾的版本串换成用户自己的。

    参考尾部末尾形如 b'\x04True' —— 前一个字节是长度、后面是该长度的 UTF-8 串
    （那份存档里被写成了 "True"，是生成全解锁 xml 时的副作用）。
    这里剥掉这一段，再接上用户原本的 gameVersion，避免覆盖成 "True"。
    """
    if not tail:
        return tail
    out = bytearray(tail)
    k = out[-1] if False else None
    # 末尾最后一段：假定为 [L][L 字节]
    L = out[-1]
    # 从尾部往前取：结构必为 [L][L bytes]，故总长需 >= L+1
    # 参考是 L=4 -> b'\x04True'，共 5 字节
    idx = len(out) - 1
    # 读取真正的长度字节：位于末尾 L 字节之前
    try:
        L2 = out[len(out) - 2]
    except Exception:
        L2 = 0
    # 用参考实测结构直接判定：倒数第 5 字节是长度，其后 4 字节是内容
    if len(out) >= 5 and out[-5] == len(out[-4:]) and out[-5] > 0:
        del out[-5:]
    b = ver.encode("utf-8")
    out += bytes([len(b)]) + b
    return bytes(out)


CHK_ON = "☑"
CHK_OFF = "☐"


class UnlockDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("强制解锁 · 按章节")
        self.transient(app)
        self.configure(background=C["bg"])
        paths.apply_icon(self)
        self.geometry("980x700")

        self.data = CH.ChapterData()
        self.checked = set()          # "章节id|曲目id"
        self.rows = {}                # iid -> song dict
        self.q = tk.StringVar()
        self.show_played = tk.BooleanVar(value=False)
        # 实测：只置解锁位不写分数 → 解锁无效。故这两项固定开启，不提供选项。
        self.with_scores = tk.BooleanVar(value=True)
        self.with_progress = tk.BooleanVar(value=True)
        self.score = tk.StringVar(value="880000")
        self.acc = tk.StringVar(value="88.00")

        gr = app.views.get("gameRecord")
        self.played = self.data.played_keys(
            gr.obj.get("records", []) if gr else [])

        self._build()
        self._fill()
        self._fit()
        self._hint()

    def _hint(self):
        self.hint.set(
            "解锁 = 在 gameKey 里给该曲加「曲绘/曲目解锁」位（bit3）。"
            "已由全解锁存档对照确认：购买过的单曲、异象曲、第九章曲目，"
            "解锁后 gameKey 都会出现该曲名的 bit3 条目。全部曲目都可解锁。")

    def _fit(self):
        try:
            self.update_idletasks()
            rw, rh = self.winfo_reqwidth(), self.winfo_reqheight()
        except Exception:
            rw, rh = 980, 700
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        w = max(860, min(max(980, rw + 24), sw - 80))
        h = max(560, min(max(700, rh + 24), sh - 60))
        self.minsize(min(840, w), min(520, h))
        self.geometry(f"{w}x{h}")
        try:
            self.update_idletasks()
            px, py = self.app.winfo_rootx(), self.app.winfo_rooty()
            pw = self.app.winfo_width() or w
            ph = self.app.winfo_height() or h
            self.geometry(f"+{max(0, px + (pw - w) // 2)}+{max(0, py + (ph - h) // 2)}")
        except Exception:
            pass

    # ---------------------------------------------------------------- 界面
    def _build(self):
        head = ttk.Frame(self, padding=(14, 12, 14, 6))
        head.pack(fill="x")
        ttk.Label(head, text="点曲目即可选中；选中第 N 首会自动带上前面的前置曲目",
                  font=F_UI_B).pack(side="left")
        self.hint = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.hint, font=F_SMALL,
                  foreground=C["dim"], padding=(14, 0)).pack(fill="x", after=head)
        self.cnt = tk.StringVar(value="")
        ttk.Label(head, textvariable=self.cnt, font=F_UI,
                  foreground=C["accent"]).pack(side="right")

        bar = ttk.Frame(self, padding=(14, 0, 14, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="🔍", font=F_UI).pack(side="left")
        e = ttk.Entry(bar, textvariable=self.q, width=24, font=F_UI)
        e.pack(side="left", padx=(2, 12))
        self.q.trace_add("write", lambda *a: self._fill())
        ttk.Checkbutton(bar, text="显示已游玩",
                        variable=self.show_played).pack(side="left")
        self.show_played.trace_add("write", lambda *a: self._fill())
        ttk.Button(bar, text="展开全部", style="Tool.TButton",
                   command=lambda: self._expand(True)).pack(side="right")
        ttk.Button(bar, text="折叠全部", style="Tool.TButton",
                   command=lambda: self._expand(False)).pack(side="right", padx=(0, 8))

        # ---- 章节树 ----
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=14, pady=(4, 0))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tv = ttk.Treeview(wrap, columns=("lv", "st"), show="tree headings",
                               height=14)
        self.tv.heading("#0", text="章节 / 曲目")
        self.tv.heading("lv", text="将写入")
        self.tv.heading("st", text="状态")
        self.tv.column("#0", width=420, minwidth=260, anchor="w", stretch=True)
        self.tv.column("lv", width=90, minwidth=70, anchor="center", stretch=False)
        self.tv.column("st", width=150, minwidth=90, anchor="w", stretch=False)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=vs.set)
        self.tv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.tv.tag_configure("ch", foreground=C["accent"])
        self.tv.tag_configure("on", foreground=C["accent"])
        self.tv.tag_configure("dim", foreground=C["dim"])
        self.tv.bind("<Button-1>", self._on_click)
        self.tv.bind("<space>", lambda e: (self._toggle_key(), "break")[1])

        # ---- 解锁方案 ----
        info = ttk.LabelFrame(self, style="Card.TLabelframe",
                              text="解锁方案", padding=12)
        info.pack(fill="x", padx=14, pady=(8, 4))
        ttk.Label(info, font=F_SMALL, foreground=C["dim"], justify="left",
                  anchor="w", wraplength=900,
                  text="解锁三步，全部都是必需的，无法关闭：\n"
                       "① gameKey 给该曲加「曲绘/曲目解锁」位（bit3）；\n"
                       "② 向最高难度写入分数（实测：只置位不写分数解锁无效）；\n"
                       "③ 写入全解锁的章节进度字节。\n"
                       "不依赖前置曲目，勾哪首就解哪首。"
                  ).pack(fill="x")

        # 固定方案（不可关）：实测只置位不写分数解锁无效，所以分数与章节进度必做
        opt = ttk.Frame(info)
        opt.pack(fill="x", pady=(8, 0))
        ttk.Label(opt, text="写入分数（最高难度）",
                  font=F_UI).pack(side="left")
        ttk.Entry(opt, textvariable=self.score, width=9,
                  font=F_UI).pack(side="left", padx=(6, 2))
        ttk.Label(opt, text="分 /", font=F_SMALL).pack(side="left")
        ttk.Entry(opt, textvariable=self.acc, width=6,
                  font=F_UI).pack(side="left", padx=(4, 2))
        ttk.Label(opt, text="% ACC", font=F_SMALL).pack(side="left")
        for v in (self.score, self.acc):
            v.trace_add("write", lambda *a: self._sync())

        # ---- 计划预览 ----
        box = ttk.LabelFrame(self, style="Card.TLabelframe",
                             text="本次将写入", padding=10)
        box.pack(fill="x", padx=14, pady=(4, 0))
        self.plan_txt = tk.StringVar(value="（未选择）")
        self.plab = ttk.Label(box, textvariable=self.plan_txt, font=F_SMALL,
                              foreground=C["dim"], justify="left", anchor="w")
        self.plab.pack(fill="x")
        self.bind("<Configure>", self._on_resize)

        # ---- 底部 ----
        bot = ttk.Frame(self, padding=(14, 6, 14, 12))
        bot.pack(fill="x", side="bottom")
        ttk.Separator(bot).pack(fill="x", pady=(0, 8))
        self.summary = tk.StringVar(value="未选择")
        ttk.Label(bot, textvariable=self.summary, font=F_UI_B,
                  foreground=C["accent"]).pack(side="left")
        ttk.Button(bot, text="关闭", style="Tool.TButton",
                   command=self._close).pack(side="right")
        self.ok_btn = ttk.Button(bot, text="✔ 确定（执行解锁）",
                                 style="Accent.TButton", command=self.do_ok)
        self.ok_btn.pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda e: self.do_ok())
        self.bind("<Escape>", lambda e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _on_resize(self, ev=None):
        try:
            w = self.plab.winfo_width()
            if w > 40:
                self.plab.configure(wraplength=max(200, w - 4))
        except Exception:
            pass

    def _expand(self, on):
        for iid in self.tv.get_children():
            self.tv.item(iid, open=on)

    # ---------------------------------------------------------------- 填充
    def _fill(self):
        self.tv.delete(*self.tv.get_children())
        self.rows.clear()
        q = self.q.get().strip().lower()
        show_p = self.show_played.get()

        for ch in self.data.chapters:
            shown_songs = []
            for s in ch["songs"]:
                played = self._norm(s["id"]) in self.played
                if played and not show_p:
                    continue
                if q and q not in s["title"].lower() \
                        and q not in s.get("composer", "").lower() \
                        and q not in ch["title"].lower():
                    continue
                shown_songs.append((s, played))
            if not shown_songs:
                continue
            cid = ch["id"]
            n_sel = sum(1 for s, _ in shown_songs
                        if f"{cid}|{s['id']}" in self.checked)
            label = ch["title"]
            if n_sel:
                label += f"　（已选 {n_sel}）"
            allin = n_sel and n_sel == len(shown_songs)
            ciid = self.tv.insert("", "end", text=label,
                                  tags=["ch"],
                                  values=(CHK_ON if allin else CHK_OFF, "", ""))
            self.rows[ciid] = {"kind": "chapter", "chapter": ch}
            for s, played in shown_songs:
                key = f"{cid}|{s['id']}"
                on = key in self.checked
                un = self.data.is_unconfirmed(s)
                st = "已游玩" if played else (
                    "异象/购买曲" if s.get("unlock") == "special" else "未解锁")
                top = CH.highest_level(s.get("levels") or [])
                siid = self.tv.insert(
                    ciid, "end",
                    text=f"{s['index']:>2}. {s['title']}",
                    tags=(["on"] if on else []) + (["dim"] if (played or un) else []),
                    values=(CHK_ON if on else CHK_OFF,
                            f"{top} {int(float(self.score.get() or 0)) // 1000}k",
                            st))
                self.rows[siid] = {"kind": "song", "chapter": ch, "song": s,
                                   "key": key, "played": played}
            if q:
                self.tv.item(ciid, open=True)
        self._sync()

    def _norm(self, s):
        return CH._norm(s)

    def _short(self, title):
        """章节标题取简称：去掉括号补充说明"""
        t = str(title).split("（")[0].split("(")[0].strip()
        return t[:18]

    # ---------------------------------------------------------------- 勾选
    def _on_click(self, ev=None):
        """只有点「选择」列才切换勾选；点其它位置保持默认行为（展开/折叠）"""
        if ev is None:
            return
        col = self.tv.identify_column(ev.x)
        if col != "#1":          # #0 是树列，#1 才是「选择」
            return
        iid = self.tv.identify_row(ev.y)
        if not iid or iid not in self.rows:
            return
        row = self.rows[iid]
        if row["kind"] == "chapter":
            self._toggle_chapter(row["chapter"])
        else:
            self._toggle_song(row)
        self._fill()
        return "break"

    def _toggle_key(self):
        """空格键：对当前选中行切换"""
        sel = self.tv.selection()
        if not sel or sel[0] not in self.rows:
            return
        row = self.rows[sel[0]]
        if row["kind"] == "chapter":
            self._toggle_chapter(row["chapter"])
        else:
            self._toggle_song(row)
        self._fill()

    def _toggle_chapter(self, ch):
        keys = [f"{ch['id']}|{s['id']}" for s in ch["songs"]]
        if all(k in self.checked for k in keys):
            for k in keys:
                self.checked.discard(k)
        else:
            self.checked.update(keys)

    def _toggle_song(self, row):
        """只切换这一首 —— 解锁靠 gameKey 的 bit3，不依赖前置曲目"""
        key = row["key"]
        if key in self.checked:
            self.checked.discard(key)
        else:
            self.checked.add(key)

    # ---------------------------------------------------------------- 计划
    def _plan(self):
        """汇总勾选的曲目（按章节顺序）。不再推导前置链。"""
        items = []
        for ch in self.data.chapters:
            for s in ch["songs"]:
                if f"{ch['id']}|{s['id']}" not in self.checked:
                    continue
                it = {"id": s["id"], "title": s["title"], "index": s["index"],
                      "levels": list(s.get("levels") or []),
                      "level": CH.highest_level(s.get("levels") or []),
                      "chapter": ch["title"]}
                items.append(it)
        return items, []

    def _nums(self):
        try:
            score = max(0, min(1000000, int(float(self.score.get().strip() or 0))))
        except Exception:
            messagebox.showerror("参数错误", "分数必须是数字")
            return None
        try:
            acc = max(0.0, min(100.0, float(self.acc.get().strip() or 0)))
        except Exception:
            messagebox.showerror("参数错误", "ACC 必须是数字")
            return None
        return score, acc

    def _sync(self):
        items, warn = self._plan()
        n = len(items)
        self.cnt.set(f"将写入 {n} 首" if n else "")
        if not n:
            self.summary.set("未选择任何曲目")
            self.plan_txt.set("（未选择）")
        else:
            self.summary.set(
                f"将解锁 {n} 首曲目　·　置解锁位 + "
                f"{int(float(self.score.get() or 0)) // 1000}k 分 + 全章节进度")
            lines = [f"{i + 1}. [{self._short(it['chapter'])}] "
                     f"{it['index']}. {it['title']}　→ "
                     f"{CH.highest_level(it['levels'])} "
                     f"{int(float(self.score.get() or 0)) // 1000}k"
                     for i, it in enumerate(items[:8])]
            if n > 8:
                lines.append(f"… 共 {n} 首")
            for w in warn[:3]:
                lines.append("⚠ " + w)
            if len(warn) > 3:
                lines.append(f"⚠ …共 {len(warn)} 条提示")
            self.plan_txt.set("\n".join(lines))
        try:
            self.ok_btn.configure(state=("normal" if n else "disabled"))
        except Exception:
            pass

    # ---------------------------------------------------------------- 执行
    def do_ok(self):
        """确定：解锁选中（gameKey bit3），可选写成绩与章节进度"""
        items, warn = self._plan()
        if not items:
            messagebox.showinfo("提示", "请先在上方勾选要解锁的曲目")
            return
        v = self._nums()          # 写分数是解锁必需，参数有问题就直接中止
        if v is None:
            return

        gk = self.app.views.get("gameKey")
        gr = self.app.views.get("gameRecord")
        if gk is None:
            return

        self.app.push_undo("强制解锁")
        msgs = []

        # ① gameKey 解锁位（主操作）
        names = {}
        for it in items:
            names[it["id"]] = U.unlock_name(it["id"], it["title"])
        added, changed = U.set_song_unlock(
            gk.obj["items"], [it["id"] for it in items], names, on=True)
        msgs.append(f"解锁位：新增 {added}、更新 {changed}")

        # ② 成绩
        if self.with_scores.get() and gr is not None:
            score, acc = v
            ns, nl = CH.apply_plan(gr.obj["records"], items,
                                   score=score, acc=acc)
            msgs.append(f"成绩：{ns} 首 / {nl} 条")

        # ③ 章节进度
        if self.with_progress.get():
            gp = self.app.views.get("gameProgress")
            tail = U.load_progress_unlocked()
            if gp is not None and tail:
                obj = gp.obj
                ver = str(obj.get("gameVersion", ""))
                obj["_tail"] = list(_patch_tail(bytes(tail), ver))
                msgs.append("章节进度：已写入全解锁参考字节")

        try:
            gk.pull(); gk.refresh()
        except Exception:
            pass
        if gr is not None:
            try:
                gr.pull(); gr.refresh()
            except Exception:
                pass
        gp = self.app.views.get("gameProgress")
        if gp is not None and self.with_progress.get():
            try:
                gp.pull(); gp.refresh()
            except Exception:
                pass
        self.app.touch()
        msg = "；".join(msgs)
        self.app._status("强制解锁完成：" + msg)
        messagebox.showinfo("完成", msg + "\n\n可用主窗口 Ctrl+Z 撤销，"
                                         "记得保存并上传到云端。")
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
