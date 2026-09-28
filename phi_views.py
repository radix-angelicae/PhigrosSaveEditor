# -*- coding: utf-8 -*-
"""各条目的可视化视图：成绩表、解锁表、表单，以及通用的 JSON 抽屉。"""

import json
import re
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from phi_format import LEVELS, ENTRY_LABEL, grade_of, clamp_score, clamp_acc, hexs
from phi_theme import C, F_UI, F_MONO, F_TITLE, grade_color, register_text


class JsonPane(ttk.Frame):
    """底部可折叠的原始 JSON 编辑区"""

    def __init__(self, master, on_apply, on_regen=None):
        super().__init__(master)
        self.on_apply = on_apply
        self.on_regen = on_regen
        self.open = False
        self.bar = ttk.Frame(self)
        self.bar.pack(fill="x")
        self.btn = ttk.Button(self.bar, text="▸  原始 JSON（高级）", command=self.toggle)
        self.btn.pack(side="left", padx=2, pady=2)
        ttk.Label(self.bar, text="展开后可直接编辑 JSON，点「应用」同步回上方表格",
                  font=F_UI, foreground=C["dim"]).pack(side="left")
        self.body = ttk.Frame(self)
        self.txt = scrolledtext.ScrolledText(self.body, wrap="none", font=F_MONO, height=10)
        register_text(self.txt)
        self.txt.pack(fill="both", expand=True, padx=2, pady=2)
        btns = ttk.Frame(self.body)
        btns.pack(fill="x")
        ttk.Button(btns, text="应用 JSON 到上方", command=self.apply).pack(side="left", padx=2)
        ttk.Button(btns, text="格式化", command=self.fmt).pack(side="left", padx=2)
        ttk.Button(btns, text="从上方重新生成", command=self.regenerate).pack(side="left", padx=2)

    def toggle(self):
        self.open = not self.open
        if self.open:
            self.body.pack(fill="both", expand=True)
            self.btn.configure(text="▾  原始 JSON（高级）")
        else:
            self.body.forget()
            self.btn.configure(text="▸  原始 JSON（高级）")

    def set_obj(self, obj):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", json.dumps(obj, ensure_ascii=False, indent=2))

    def get_text(self):
        return self.txt.get("1.0", "end-1c")

    def regenerate(self):
        if self.on_regen:
            self.on_regen()

    def fmt(self):
        try:
            obj = json.loads(self.get_text())
        except Exception as e:
            messagebox.showerror("JSON 错误", str(e))
            return
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", json.dumps(obj, ensure_ascii=False, indent=2))

    def apply(self):
        self.on_apply(self.get_text())


# ================================================================ 视图基类
class BaseView(ttk.Frame):
    def __init__(self, master, name, obj, app):
        super().__init__(master)
        self.name, self.obj, self.app = name, obj, app
        self.json_pane = None

    def attach_json(self):
        self.json_pane = JsonPane(self, self.apply_json, self.refresh_json)
        self.json_pane.pack(fill="x", side="bottom", padx=4, pady=3)
        self.json_pane.set_obj(self.obj)

    def refresh_json(self):
        if self.json_pane:
            self.json_pane.set_obj(self.obj)

    def apply_json(self, text):
        try:
            obj = json.loads(text)
        except Exception as e:
            messagebox.showerror("JSON 错误", f"{self.name}：\n{e}")
            return False
        self.obj = obj
        self.refresh()
        self.app.touch()
        return True

    def pull(self):
        """保存前：若 JSON 抽屉被改过，以 JSON 为准"""
        if self.json_pane and self.json_pane.open:
            t = self.json_pane.get_text()
            try:
                new = json.loads(t)
            except Exception as e:
                raise ValueError(f"{self.name} 的 JSON 无法解析：{e}")
            if new != self.obj:
                self.obj = new

    def refresh(self):
        raise NotImplementedError

    def commit(self, label):
        """修改前登记撤销点"""
        try:
            self.app.push_undo(label)
        except Exception:
            pass


# ================================================================ 成绩表
class RecordView(BaseView):
    COLS = ("song", "lv", "score", "acc", "fc", "grade")
    HEAD = {"song": "曲目 / ID", "lv": "难度", "score": "分数", "acc": "ACC (%)",
            "fc": "FC", "grade": "评级"}

    def __init__(self, master, name, obj, app):
        super().__init__(master, name, obj, app)
        self.sort_col, self.sort_desc = "song", False
        self.build()

    # ---------- 界面
    def build(self):
        top = ttk.Frame(self, padding=(6, 6, 6, 2))
        top.pack(fill="x")
        ttk.Label(top, text="🔍", font=F_UI).pack(side="left")
        self.q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q, width=26, font=F_UI)
        e.pack(side="left", padx=(2, 8))
        self.search_entry = e
        self.q.trace_add("write", lambda *a: self.refresh_tree())

        ttk.Label(top, text="难度", font=F_UI).pack(side="left")
        self.lv = tk.StringVar(value="全部")
        cb = ttk.Combobox(top, textvariable=self.lv, values=["全部"] + LEVELS,
                          state="readonly", width=6, font=F_UI)
        cb.pack(side="left", padx=(2, 8))
        cb.bind("<<ComboboxSelected>>", lambda ev: self.refresh_tree())

        self.only_fc = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="仅 FC", variable=self.only_fc,
                        command=self.refresh_tree).pack(side="left", padx=(0, 8))
        self.hide_low = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="隐藏无成绩", variable=self.hide_low,
                        command=self.refresh_tree).pack(side="left", padx=(0, 8))

        ttk.Button(top, text="批量修改…", command=self.batch).pack(side="right", padx=2)
        ttk.Button(top, text="＋ 新增成绩", command=self.add).pack(side="right", padx=2)
        ttk.Button(top, text="－ 删除", command=self.delete).pack(side="right", padx=2)

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=6)
        self.tree = ttk.Treeview(wrap, columns=self.COLS, show="headings",
                                 selectmode="extended", height=16)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self._sync_headings()
        # 曲目列自适应填充剩余宽度，其余列保持舒适固定宽度
        self.tree.column("song", width=380, minwidth=220, anchor="w", stretch=True)
        self.tree.column("lv", width=70, minwidth=60, anchor="center", stretch=False)
        self.tree.column("score", width=120, minwidth=100, anchor="e", stretch=False)
        self.tree.column("acc", width=110, minwidth=90, anchor="e", stretch=False)
        self.tree.column("fc", width=70, minwidth=60, anchor="center", stretch=False)
        self.tree.column("grade", width=80, minwidth=64, anchor="center", stretch=False)
        self.tree.tag_configure("alt", background=C["alt"])
        for g in ["φ","V","S","A","B","C","F"]:
            self.tree.tag_configure(f"g{g}", foreground=grade_color(g))

        self.tree.bind("<Double-1>", self.on_edit)
        self.tree.bind("<Return>", self.on_edit)
        self.tree.bind("<Delete>", lambda e: self.delete())
        self.tree.bind("<Button-3>", self.popup)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="修改此行…", command=self.edit_selected)
        self.menu.add_command(label="设为 φ (1000000 / 100%)", command=lambda: self.preset(1000000, 100.0, True))
        self.menu.add_command(label="全部 FC", command=lambda: self.preset(None, None, True))
        self.menu.add_separator()
        self.menu.add_command(label="删除此行", command=self.delete)

        self.stat = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.stat, font=F_UI,
                  foreground=C["dim"], padding=(8, 2)).pack(fill="x")
        self.attach_json()
        self.refresh_tree()

    def export_csv(self):
        import csv as _csv

        p = filedialog.asksaveasfilename(defaultextension=".csv",
                                         initialfile="gameRecord.csv",
                                         filetypes=[("CSV (Excel 可打开)", "*.csv")])
        if not p:
            return
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.writer(f)
            w.writerow(["曲目 ID", "难度", "分数", "ACC", "FC", "评级"])
            for ri, lv, s2 in self.rows():
                sc = int(s2.get("score", 0))
                ac = float(s2.get("acc", 0.0))
                w.writerow([self.obj["records"][ri].get("id", ""), lv, sc,
                            f"{ac:.4f}", "FC" if s2.get("fc") else "", grade_of(sc, ac)])
        self.app._status(f"已导出 CSV：{p}")

    def popup(self, ev):
        iid = self.tree.identify_row(ev.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.menu.post(ev.x_root, ev.y_root)

    # ---------- 数据
    def rows(self):
        q = self.q.get().strip().lower()
        lvf = self.lv.get()
        out = []
        for ri, rec in enumerate(self.obj.get("records", [])):
            for lv in LEVELS:
                s = rec.get("scores", {}).get(lv)
                if s is None:
                    continue
                if lvf != "全部" and lv != lvf:
                    continue
                if self.only_fc.get() and not s.get("fc"):
                    continue
                if self.hide_low.get() and int(s.get("score", 0)) <= 0:
                    continue
                if q and q not in str(rec.get("id", "")).lower():
                    continue
                out.append((ri, lv, s))
        key = {"song": lambda t: str(self.obj["records"][t[0]].get("id", "")).lower(),
               "lv": lambda t: LEVELS.index(t[1]),
               "score": lambda t: int(t[2].get("score", 0)),
               "acc": lambda t: float(t[2].get("acc", 0)),
               "fc": lambda t: bool(t[2].get("fc")),
               "grade": lambda t: int(t[2].get("score", 0))}[self.sort_col]
        out.sort(key=key, reverse=self.sort_desc)
        return out

    def _sync_headings(self):
        """表头显示当前排序列与方向"""
        for c in self.COLS:
            mark = ("  ▼" if self.sort_desc else "  ▲") if c == self.sort_col else ""
            self.tree.heading(c, text=self.HEAD[c] + mark,
                              command=lambda x=c: self.sort_by(x))

    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = col, False
        self._sync_headings()
        self.refresh_tree()

    def refresh_tree(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        data = self.rows()
        for i, (ri, lv, s) in enumerate(data):
            sid = self.obj["records"][ri].get("id", "")
            sc = int(s.get("score", 0))
            ac = float(s.get("acc", 0.0))
            g = grade_of(sc, ac)
            tags = ["g" + g] + (["alt"] if i % 2 else [])
            self.tree.insert("", "end", iid=f"{ri}|{lv}", tags=tags,
                             values=(sid, lv, f"{sc:,}", f"{ac:.4f}", "✔" if s.get("fc") else "", g))
        if sel:
            for s_ in sel:
                if s_ in self.tree.get_children():
                    self.tree.selection_add(s_)
        n_song = len(self.obj.get("records", []))
        dist = {}
        for r in self.obj.get("records", []):
            for s2 in r.get("scores", {}).values():
                g2 = grade_of(int(s2.get("score", 0)), float(s2.get("acc", 0.0)))
                dist[g2] = dist.get(g2, 0) + 1
        dtxt = "  ".join(f"{k}×{dist[k]}" for k in ["φ", "V", "S", "A", "B", "C", "F"]
                         if k in dist)
        self.stat.set(f"显示 {len(data)} 条 / 共 {len(self.all_rows())} 条成绩，"
                      f"{n_song} 首曲目　|　{dtxt}　|　"
                      f"双击单元格修改，右键更多操作")

    def all_rows(self):
        return [(ri, lv) for ri, r in enumerate(self.obj.get("records", []))
                for lv in r.get("scores", {})]

    def refresh(self):
        self.refresh_tree()
        self.refresh_json()

    # ---------- 编辑
    def on_edit(self, ev=None):
        col = "#3"
        if ev is not None and hasattr(ev, "x"):
            try:
                c = self.tree.identify_column(ev.x)
                if c:
                    col = c
            except Exception:
                pass
        self.edit_selected(col)

    def edit_selected(self, col="#3"):
        sel = self.tree.selection()
        if not sel:
            return
        ri, lv = sel[0].split("|")
        if col == "#1":
            self.rename(int(ri))
            return
        s = self.obj["records"][int(ri)]["scores"][lv]
        idx = {"#3": 1, "#4": 2, "#5": 3}.get(col, 1)
        self._dialog(ri, lv, s, idx)

    def rename(self, ri):
        rec = self.obj["records"][ri]
        d = tk.Toplevel(self)
        d.title("重命名曲目 ID")
        d.resizable(False, False)
        d.transient(self.winfo_toplevel())
        frm = ttk.Frame(d, padding=12)
        frm.pack()
        ttk.Label(frm, text="曲目 ID（格式：曲名.曲师.0）", font=F_UI).pack(anchor="w")
        v = tk.StringVar(value=str(rec.get("id", "")))
        ent = ttk.Entry(frm, textvariable=v, width=40, font=F_UI)
        ent.pack(fill="x", pady=6)
        ent.select_range(0, "end")

        def ok():
            nv = v.get().strip()
            if nv:
                rec["id"] = nv
                d.destroy()
                self.refresh()
                self.app.touch()

        ttk.Button(frm, text="确定", command=ok).pack(side="right", padx=3)
        ttk.Button(frm, text="取消", command=d.destroy).pack(side="right")
        ent.focus_set()
        d.grab_set()
        self.wait_window(d)

    def _dialog(self, ri, lv, s, focus=1):
        sid = self.obj["records"][int(ri)].get("id", "")
        d = tk.Toplevel(self)
        d.title("修改成绩")
        d.transient(self.winfo_toplevel())
        d.resizable(False, False)
        d.configure(bg=C["bg"])
        frm = ttk.Frame(d, padding=12)
        frm.pack()

        ttk.Label(frm, text=sid, font=F_TITLE).grid(row=0, column=0, columnspan=2,
                                                    sticky="w", pady=(0, 8))
        ttk.Label(frm, text="难度", font=F_UI).grid(row=1, column=0, sticky="e", padx=4, pady=3)
        lv_var = tk.StringVar(value=lv)
        ttk.Combobox(frm, textvariable=lv_var, values=LEVELS, state="readonly",
                     width=8, font=F_UI).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(frm, text="分数 (0~1000000)", font=F_UI).grid(row=2, column=0, sticky="e", padx=4, pady=3)
        sc_var = tk.StringVar(value=str(int(s.get("score", 0))))
        sc_e = ttk.Entry(frm, textvariable=sc_var, width=14, font=F_UI)
        sc_e.grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(frm, text="ACC (%)", font=F_UI).grid(row=3, column=0, sticky="e", padx=4, pady=3)
        ac_var = tk.StringVar(value=f"{float(s.get('acc', 0.0)):.4f}")
        ac_e = ttk.Entry(frm, textvariable=ac_var, width=14, font=F_UI)
        ac_e.grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(frm, text="FC (Full Combo)", font=F_UI).grid(row=4, column=0, sticky="e", padx=4, pady=3)
        fc_var = tk.BooleanVar(value=bool(s.get("fc")))
        ttk.Checkbutton(frm, variable=fc_var).grid(row=4, column=1, sticky="w", pady=3)

        prev = tk.StringVar(value="")
        ttk.Label(frm, textvariable=prev, font=F_UI, foreground=C["accent"]).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))

        def upd(*a):
            g = grade_of(clamp_score(sc_var.get()), clamp_acc(ac_var.get()))
            prev.set(f"预览评级：{g}")
        sc_var.trace_add("write", upd)
        ac_var.trace_add("write", upd)
        upd()

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btns, text="设为 φ", command=lambda: (
            sc_var.set("1000000"), ac_var.set("100.0000"), fc_var.set(True))).pack(side="left", padx=3)
        ttk.Button(btns, text="确定", command=lambda: self._ok(d, ri, lv, lv_var, sc_var,
                                                               ac_var, fc_var)).pack(side="left", padx=3)
        ttk.Button(btns, text="取消", command=d.destroy).pack(side="left", padx=3)

        [sc_e, ac_e][min(focus - 1, 1)].focus_set()
        [sc_e, ac_e][min(focus - 1, 1)].select_range(0, "end")
        d.grab_set()
        self.wait_window(d)

    def _ok(self, d, ri, lv, lv_var, sc_var, ac_var, fc_var):
        self.commit("修改成绩")
        rec = self.obj["records"][int(ri)]
        new_lv = lv_var.get()
        val = {"score": clamp_score(sc_var.get()),
               "acc": clamp_acc(ac_var.get()),
               "fc": bool(fc_var.get())}
        if new_lv != lv:
            rec["scores"].pop(lv, None)
        rec["scores"][new_lv] = val
        rec["scores"] = {k: rec["scores"][k] for k in LEVELS if k in rec["scores"]}
        d.destroy()
        self.refresh()
        self.app.touch()

    def preset(self, score, acc, fc):
        if not self.tree.selection():
            return
        self.commit("批量设为 φ / FC")
        for iid in self.tree.selection():
            ri, lv = iid.split("|")
            s = self.obj["records"][int(ri)]["scores"][lv]
            if score is not None:
                s["score"] = score
            if acc is not None:
                s["acc"] = acc
            if fc is not None:
                s["fc"] = fc
        self.refresh()
        self.app.touch()

    def batch(self):
        data = self.rows()
        if not data:
            messagebox.showinfo("提示", "当前筛选结果为空")
            return
        d = tk.Toplevel(self)
        d.title("批量修改")
        d.resizable(False, False)
        d.transient(self.winfo_toplevel())
        frm = ttk.Frame(d, padding=12)
        frm.pack()
        ttk.Label(frm, text=f"将作用于当前筛选出的 {len(data)} 条成绩",
                  font=F_TITLE).grid(row=0, column=0, columnspan=2, pady=(0, 8))

        use_sc = tk.BooleanVar(value=True)
        sc_var = tk.StringVar(value="1000000")
        use_ac = tk.BooleanVar(value=True)
        ac_var = tk.StringVar(value="100.0000")
        use_fc = tk.BooleanVar(value=True)
        fc_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(frm, variable=use_sc, text="分数 =").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm, textvariable=sc_var, width=12, font=F_UI).grid(row=1, column=1)
        ttk.Checkbutton(frm, variable=use_ac, text="ACC =").grid(row=2, column=0, sticky="e")
        ttk.Entry(frm, textvariable=ac_var, width=12, font=F_UI).grid(row=2, column=1)
        ttk.Checkbutton(frm, variable=use_fc, text="FC =").grid(row=3, column=0, sticky="e")
        ttk.Checkbutton(frm, variable=fc_var, text="设为 Full Combo").grid(row=3, column=1, sticky="w")

        def ok():
            self.commit("批量修改")
            for ri, lv, s in data:
                if use_sc.get():
                    s["score"] = clamp_score(sc_var.get())
                if use_ac.get():
                    s["acc"] = clamp_acc(ac_var.get())
                if use_fc.get():
                    s["fc"] = bool(fc_var.get())
            d.destroy()
            self.refresh()
            self.app.touch()
            messagebox.showinfo("完成", f"已更新 {len(data)} 条成绩")

        ttk.Button(frm, text="应用", command=ok).grid(row=4, column=0, pady=(10, 0))
        ttk.Button(frm, text="取消", command=d.destroy).grid(row=4, column=1, pady=(10, 0))
        d.grab_set()
        self.wait_window(d)

    def add(self):
        d = tk.Toplevel(self)
        d.title("新增成绩")
        d.resizable(False, False)
        d.transient(self.winfo_toplevel())
        frm = ttk.Frame(d, padding=12)
        frm.pack()
        ttk.Label(frm, text="曲目 ID（格式：曲名.曲师.0）", font=F_UI).grid(row=0, column=0, sticky="e", pady=3)
        sid = tk.StringVar()
        ttk.Entry(frm, textvariable=sid, width=32, font=F_UI).grid(row=0, column=1, pady=3)
        ttk.Label(frm, text="难度", font=F_UI).grid(row=1, column=0, sticky="e", pady=3)
        lv = tk.StringVar(value="IN")
        ttk.Combobox(frm, textvariable=lv, values=LEVELS, state="readonly",
                     width=8, font=F_UI).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(frm, text="分数", font=F_UI).grid(row=2, column=0, sticky="e", pady=3)
        sc = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=sc, width=12, font=F_UI).grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(frm, text="ACC", font=F_UI).grid(row=3, column=0, sticky="e", pady=3)
        ac = tk.StringVar(value="0.0")
        ttk.Entry(frm, textvariable=ac, width=12, font=F_UI).grid(row=3, column=1, sticky="w", pady=3)

        def ok():
            self.commit("新增成绩")
            name = sid.get().strip()
            if not name:
                messagebox.showwarning("提示", "请填写曲目 ID")
                return
            rec = next((r for r in self.obj["records"] if r.get("id") == name), None)
            if rec is None:
                rec = {"id": name, "scores": {}}
                self.obj["records"].append(rec)
            rec["scores"][lv.get()] = {"score": clamp_score(sc.get()),
                                       "acc": clamp_acc(ac.get()), "fc": False}
            rec["scores"] = {k: rec["scores"][k] for k in LEVELS if k in rec["scores"]}
            d.destroy()
            self.refresh()
            self.app.touch()

        ttk.Button(frm, text="添加", command=ok).grid(row=4, column=0, pady=(10, 0))
        ttk.Button(frm, text="取消", command=d.destroy).grid(row=4, column=1, pady=(10, 0))
        d.grab_set()
        self.wait_window(d)

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("确认删除", f"将删除选中的 {len(sel)} 条成绩记录，继续？"):
            return
        self.commit("删除成绩")
        drop = {}
        for iid in sel:
            ri, lv = iid.split("|")
            drop.setdefault(int(ri), []).append(lv)
        for ri in sorted(drop, reverse=True):
            rec = self.obj["records"][ri]
            for lv in drop[ri]:
                rec["scores"].pop(lv, None)
            if not rec["scores"]:
                self.obj["records"].pop(ri)
        self.refresh()
        self.app.touch()


# ================================================================ 解锁表
class KeyView(BaseView):
    def __init__(self, master, name, obj, app):
        super().__init__(master, name, obj, app)
        self.build()

    def build(self):
        top = ttk.Frame(self, padding=(6, 6, 6, 2))
        top.pack(fill="x")
        ttk.Label(top, text="🔍", font=F_UI).pack(side="left")
        self.q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q, width=26, font=F_UI)
        e.pack(side="left", padx=(2, 8))
        self.q.trace_add("write", lambda *a: self.refresh_tree())
        ttk.Button(top, text="编辑选中 flags…", command=self.edit).pack(side="right", padx=2)
        ttk.Button(top, text="复制同类项 flags", command=self.copy_flags).pack(side="right", padx=2)

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=6)
        self.tree = ttk.Treeview(wrap, columns=("id", "n", "flags"), show="headings", height=16)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.heading("id", text="条目 ID")
        self.tree.heading("n", text="字节数")
        self.tree.heading("flags", text="flags（十六进制）")
        self.tree.column("id", width=420, minwidth=240, anchor="w", stretch=True)
        self.tree.column("n", width=90, minwidth=70, anchor="center", stretch=False)
        self.tree.column("flags", width=300, minwidth=200, anchor="w", stretch=True)
        self.tree.tag_configure("alt", background=C["alt"])
        self.tree.bind("<Double-1>", lambda e: self.edit())

        self.stat = tk.StringVar()
        ttk.Label(self, textvariable=self.stat, font=F_UI,
                  foreground=C["dim"], padding=(8, 2)).pack(fill="x")
        self.attach_json()
        self.refresh_tree()

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        q = self.q.get().strip().lower()
        items = self.obj.get("items", [])
        shown = 0
        for i, it in enumerate(items):
            if q and q not in str(it.get("id", "")).lower():
                continue
            shown += 1
            fl = it.get("flags", [])
            self.tree.insert("", "end", iid=str(i), tags=["alt"] if i % 2 else [],
                             values=(it.get("id", ""), len(fl), hexs(fl)))
        self.stat.set(f"显示 {shown} / 共 {len(items)} 个解锁条目　·　"
                      f"flags 为位打包原始字节，修改前请记录原值")
        self.refresh_json()

    def refresh(self):
        self.refresh_tree()

    def edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        it = self.obj["items"][i]
        d = tk.Toplevel(self)
        d.title("编辑 flags")
        d.resizable(False, False)
        d.transient(self.winfo_toplevel())
        frm = ttk.Frame(d, padding=12)
        frm.pack()
        ttk.Label(frm, text=str(it.get("id", "")), font=F_TITLE).grid(row=0, column=0, columnspan=2, pady=(0, 6))
        ttk.Label(frm, text="flags（十六进制，空格分隔）", font=F_UI).grid(row=1, column=0, sticky="e", pady=3)
        v = tk.StringVar(value=hexs(it.get("flags", [])))
        ent = ttk.Entry(frm, textvariable=v, width=28, font=F_MONO)
        ent.grid(row=1, column=1, pady=3)
        ttk.Label(frm, text="十进制：", font=F_UI).grid(row=2, column=0, sticky="e", pady=3)
        dv = tk.StringVar(value=str(list(it.get("flags", []))))
        ttk.Entry(frm, textvariable=dv, width=28, font=F_MONO).grid(row=2, column=1, pady=3)

        def ok():
            self.commit("修改 flags")
            raw = re.findall(r"[0-9a-fA-F]{1,2}", v.get())
            if not raw:
                messagebox.showwarning("提示", "请输入十六进制字节")
                return
            it["flags"] = [int(x, 16) for x in raw]
            d.destroy()
            self.refresh()
            self.app.touch()

        ttk.Button(frm, text="确定", command=ok).grid(row=3, column=0, pady=(10, 0))
        ttk.Button(frm, text="取消", command=d.destroy).grid(row=3, column=1, pady=(10, 0))
        ent.focus_set()
        d.grab_set()
        self.wait_window(d)

    def copy_flags(self):
        sel = self.tree.selection()
        if len(sel) < 2:
            messagebox.showinfo("提示", "请先选中 2 行以上：以第一行为模板，覆盖其余行")
            return
        self.commit("复制 flags")
        src = self.obj["items"][int(sel[0])]
        for iid in sel[1:]:
            self.obj["items"][int(iid)]["flags"] = list(src.get("flags", []))
        self.refresh()
        self.app.touch()
        messagebox.showinfo("完成", f"已将 {len(sel)-1} 行的 flags 设为与首行一致")


# ================================================================ 表单视图
class FormView(BaseView):
    """settings / user / gameProgress 通用表单"""

    def __init__(self, master, name, obj, app, fields, tail_label=None):
        super().__init__(master, name, obj, app)
        self.fields = fields
        self.tail_label = tail_label
        self.build()

    def build(self):
        box = ttk.LabelFrame(self, text="可编辑字段", padding=12)
        box.pack(fill="x", padx=8, pady=8)
        self.vars = {}
        r = 0
        for key, label, kind in self.fields:
            ttk.Label(box, text=label, font=F_UI).grid(row=r, column=0, sticky="ne", padx=6, pady=5)
            if kind == "text":
                w = scrolledtext.ScrolledText(box, width=60, height=8, font=F_MONO, wrap="word")
                register_text(w)
                w.insert("1.0", str(self.obj.get(key, "")))
                w.grid(row=r, column=1, sticky="w", pady=5)
                self.vars[key] = w
            else:
                v = tk.StringVar(value=str(self.obj.get(key, "")))
                ent = ttk.Entry(box, textvariable=v, width=44, font=F_UI)
                ent.grid(row=r, column=1, sticky="w", pady=5)
                self.vars[key] = v
            r += 1

        ttk.Button(box, text="✔ 应用修改", command=self.apply_form).grid(
            row=r, column=0, columnspan=2, pady=(10, 2))
        self.form_hint = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.form_hint, font=F_UI,
                  foreground=C["accent"]).grid(row=r + 1, column=0, columnspan=2, sticky="w")

        # settings 的浮点参数
        if "_tailFloats" in self.obj:
            fs = self.obj["_tailFloats"]
            fb = ttk.LabelFrame(self, style="Card.TLabelframe", text="数值参数（音量 / 延迟 / 缩放等，谨慎修改）", padding=12)
            fb.pack(fill="x", padx=8, pady=(0, 8))
            ttk.Label(fb, text="1.0 量级通常为音量或缩放，小于 1 的多为延迟类。不确定请保持原值。",
                      font=F_UI, foreground=C["dim"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
            self.fvars = []
            for i, f in enumerate(fs):
                row, col = divmod(i, 4)
                ttk.Label(fb, text=f"参数 {i+1}", font=F_UI).grid(row=row + 1, column=col * 2,
                                                                  sticky="e", padx=(6, 2), pady=3)
                v = tk.StringVar(value=f"{float(f):.6g}")
                ttk.Entry(fb, textvariable=v, width=10, font=F_UI).grid(row=row + 1, column=col * 2 + 1,
                                                                        sticky="w", padx=(0, 10), pady=3)
                self.fvars.append(v)
            ttk.Button(fb, text="✔ 应用数值", command=self.apply_floats).grid(
                row=(len(fs) + 3) // 4 + 1, column=0, columnspan=8, pady=(8, 0), sticky="w")

        # 尾部原始字节（只读）
        tail = self.obj.get("_tail", [])
        if tail:
            tb = ttk.LabelFrame(self, style="Card.TLabelframe", text=f"尾部原始字节（{len(tail)} 字节，未解析 · 只读）", padding=8)
            tb.pack(fill="x", padx=8, pady=(0, 8))
            txt = scrolledtext.ScrolledText(tb, height=3, font=F_MONO, wrap="word")
            register_text(txt)
            txt.insert("1.0", hexs(tail))
            txt.configure(state="disabled")
            txt.pack(fill="x")

        self.attach_json()

    def apply_form(self):
        try:
            for key, _label, kind in self.fields:
                w = self.vars[key]
                if kind == "text":
                    self.obj[key] = w.get("1.0", "end-1c")
                elif kind == "int":
                    self.obj[key] = int(str(w.get()).strip())
                elif kind == "float":
                    self.obj[key] = float(str(w.get()).strip())
                else:
                    self.obj[key] = str(w.get())
        except Exception as e:
            messagebox.showerror("输入错误", str(e))
            return
        self.commit("修改" + ENTRY_LABEL.get(self.name, self.name))
        self.form_hint.set("已应用，请记得保存存档")
        self.refresh_json()
        self.app.touch()

    def apply_floats(self):
        vals = []
        for v in self.fvars:
            try:
                vals.append(float(str(v.get()).strip()))
            except Exception:
                messagebox.showerror("输入错误", f"「{v.get()}」不是合法数字")
                return
        self.commit("修改数值参数")
        self.obj["_tailFloats"] = vals
        self.obj["_tail"] = [b for f in vals for b in struct.pack("<f", f)]
        self.form_hint.set("数值已应用（同时同步了底层字节）")
        self.refresh_json()
        self.app.touch()

    def refresh(self):
        for key, _label, kind in self.fields:
            w = self.vars.get(key)
            if w is None:
                continue
            if kind == "text":
                w.delete("1.0", "end")
                w.insert("1.0", str(self.obj.get(key, "")))
            else:
                w.set(str(self.obj.get(key, "")))
        if hasattr(self, "fvars") and "_tailFloats" in self.obj:
            for v, f in zip(self.fvars, self.obj["_tailFloats"]):
                v.set(f"{float(f):.6g}")
        self.refresh_json()
