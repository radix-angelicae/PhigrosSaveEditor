# -*- coding: utf-8 -*-
"""主题：配色、字体、浅色/深色模式切换。

用法：视图统一用 `C["bg"]` 这样的键取值，切换主题时替换 Palette 内部字典即可，
无需重新导入常量。
"""

# ---------------------------------------------------------------- 字体
F_UI = ("Microsoft YaHei UI", 10)
F_UI_B = ("Microsoft YaHei UI", 10, "bold")
F_MONO = ("Cascadia Mono", 10)
F_TITLE = ("Microsoft YaHei UI", 12, "bold")
F_SMALL = ("Microsoft YaHei UI", 9)

# ---------------------------------------------------------------- 配色
LIGHT = {
    "bg": "#f6f7f9",        # 窗口底色
    "card": "#ffffff",      # 卡片/控件底色
    "border": "#e3e6ea",    # 分隔线
    "text": "#1f2328",      # 主文字
    "dim": "#6b7280",       # 次要文字
    "accent": "#2563eb",    # 强调色
    "accent_d": "#1d4ed8",  # 强调色·按下
    "head_bg": "#f0f2f5",   # 表头底色
    "head_active": "#e6e9ee",
    "sel": "#e0edff",       # 选中行
    "alt": "#fbfcfd",       # 斑马纹
    "danger": "#dc2626",
    "hover": "#f2f4f7",
    "pressed": "#e5e7eb",
    "disabled": "#f9fafb",
    "scroll": "#cbd2da",
    "text_bg": "#ffffff",   # Text 控件底色
}

DARK = {
    "bg": "#181a1f",
    "card": "#23262c",
    "border": "#33373f",
    "text": "#e6e8eb",
    "dim": "#9aa1ab",
    "accent": "#5b93ff",
    "accent_d": "#3f7ae8",
    "head_bg": "#2a2e35",
    "head_active": "#333842",
    "sel": "#2f4470",
    "alt": "#1e2126",
    "danger": "#f87171",
    "hover": "#2b2f36",
    "pressed": "#343941",
    "disabled": "#1f2227",
    "scroll": "#4a5058",
    "text_bg": "#1e2126",
}

GRADE_LIGHT = {"φ": "#b45309", "V": "#1d4ed8", "S": "#7c3aed",
               "A": "#dc2626", "B": "#ea580c", "C": "#6b7280", "F": "#9ca3af"}
GRADE_DARK = {"φ": "#fbbf24", "V": "#7aa9ff", "S": "#c084fc",
              "A": "#f87171", "B": "#fb923c", "C": "#9aa1ab", "F": "#6b7280"}


class Palette:
    """可热替换的配色表"""

    def __init__(self, dark=False):
        self.mode = "dark" if dark else "light"
        self._d = DARK if dark else LIGHT

    def set(self, dark: bool):
        self.mode = "dark" if dark else "light"
        self._d = DARK if dark else LIGHT

    @property
    def dark(self) -> bool:
        return self.mode == "dark"

    def __getitem__(self, k):
        return self._d[k]

    def get(self, k, default=""):
        return self._d.get(k, default)


C = Palette(False)


def grade_color(g: str) -> str:
    d = GRADE_DARK if C.dark else GRADE_LIGHT
    return d.get(g, C["text"])


# ---------------------------------------------------------------- Text 控件登记
# tkinter 的 Text / ScrolledText 不是 ttk 控件，切换主题时需手动刷新
_text_widgets = []


def register_text(w):
    try:
        if w not in _text_widgets:
            _text_widgets.append(w)
    except Exception:
        pass


def refresh_texts():
    for w in list(_text_widgets):
        try:
            if not w.winfo_exists():
                _text_widgets.remove(w)
                continue
            w.configure(background=C["text_bg"], foreground=C["text"],
                        insertbackground=C["text"],
                        selectbackground=C["sel"],
                        highlightbackground=C["border"])
        except Exception:
            pass



# ---------------------------------------------------------------- 勾选框图形
# ttk 的 clam 主题把「选中」画成了 ✕，这里换成自绘的对勾，跨平台一致。
def _png_bytes(rows, w, h):
    """rows: 每行为 [(r,g,b,a)...]，打包成 PNG"""
    import struct
    import zlib
    raw = bytearray()
    for r in rows:
        raw.append(0)
        for px in r:
            raw.extend(px)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _blank_rows(w, h):
    return [[(0, 0, 0, 0)] * w for _ in range(h)]


def _rect(rows, x0, y0, x1, y1, color):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if 0 <= y < len(rows) and 0 <= x < len(rows[0]):
                rows[y][x] = color


_CHECK_SIZE = 15
_ACCENT = (37, 99, 235, 255)      # #2563eb
_WHITE = (255, 255, 255, 255)
_BORDER = (150, 158, 170, 255)


def _tick_rows():
    rows = _blank_rows(_CHECK_SIZE, _CHECK_SIZE)
    # 蓝底 + 圆角（四角留透明）
    for y in range(_CHECK_SIZE):
        for x in range(_CHECK_SIZE):
            corner = ((x in (0, _CHECK_SIZE - 1)) and (y in (0, _CHECK_SIZE - 1)))
            if not corner:
                rows[y][x] = _ACCENT
    # 白色对勾：短边下行 + 长边上扬
    for x, y in ((3, 7), (4, 8), (5, 9), (6, 8), (7, 7), (8, 6), (9, 5), (10, 4)):
        rows[y][x] = _WHITE
        rows[y + 1][x] = _WHITE
        rows[y][x + 1] = _WHITE
    return rows


def _box_rows():
    rows = _blank_rows(_CHECK_SIZE, _CHECK_SIZE)
    _rect(rows, 1, 1, _CHECK_SIZE - 2, _CHECK_SIZE - 2, _WHITE)
    _rect(rows, 2, 2, _CHECK_SIZE - 3, _CHECK_SIZE - 3, (0, 0, 0, 0))
    for i in range(1, _CHECK_SIZE - 1):
        rows[1][i] = _BORDER
        rows[_CHECK_SIZE - 2][i] = _BORDER
        rows[i][1] = _BORDER
        rows[i][_CHECK_SIZE - 2] = _BORDER
    return rows


_CHECKBOX_IMAGES = []   # 防止被回收


def install_checkbutton(style):
    """用自绘图形替换 ttk 的勾选框（只需一次）"""
    try:
        if "Checkbutton.indicator" in style.element_names():
            return
    except Exception:
        return
    try:
        import base64
        import tkinter as tk
        off = tk.PhotoImage(data=base64.b64encode(
            _png_bytes(_box_rows(), _CHECK_SIZE, _CHECK_SIZE)).decode())
        on = tk.PhotoImage(data=base64.b64encode(
            _png_bytes(_tick_rows(), _CHECK_SIZE, _CHECK_SIZE)).decode())
        _CHECKBOX_IMAGES.extend([off, on])
        style.element_create("Checkbutton.indicator", "image", off,
                             ("selected", on))
    except Exception:
        pass


# ---------------------------------------------------------------- 样式应用
def apply_theme(root, style):
    """把当前配色应用到所有 ttk 样式"""
    try:
        style.theme_use("clam")
    except Exception:
        pass
    install_checkbutton(style)

    style.configure(".", background=C["bg"], foreground=C["text"],
                    fieldbackground=C["card"], font=F_UI, borderwidth=0)
    style.configure("TFrame", background=C["bg"])
    style.configure("Card.TFrame", background=C["card"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"], font=F_UI)

    # 卡片式分组框
    style.configure("Big.TLabel", background=C["card"], foreground=C["accent"],
                    font=("Microsoft YaHei UI", 22, "bold"))
    style.configure("Card.TLabelframe", background=C["card"], relief="solid", borderwidth=1)
    style.configure("Card.TLabelframe.Label", background=C["card"],
                    foreground=C["text"], font=F_UI_B)
    style.configure("TLabelframe", background=C["bg"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=C["bg"],
                    foreground=C["text"], font=F_UI_B)

    # 按钮
    style.configure("TButton", background=C["card"], foreground=C["text"],
                    font=F_UI, padding=(14, 7), relief="solid", borderwidth=1,
                    focuscolor=C["bg"])
    style.map("TButton",
              background=[("active", C["hover"]), ("pressed", C["pressed"]),
                          ("disabled", C["disabled"])],
              bordercolor=[("focus", C["accent"]), ("!focus", C["border"])],
              relief=[("pressed", "sunken"), ("!pressed", "solid")])
    style.configure("Accent.TButton", background=C["accent"], foreground="#ffffff",
                    borderwidth=0, padding=(16, 7))
    style.map("Accent.TButton",
              background=[("active", C["accent_d"]), ("pressed", C["accent_d"])])
    style.configure("Danger.TButton", foreground=C["danger"], padding=(12, 7))
    style.configure("Tool.TButton", padding=(10, 6))

    # 输入控件
    style.configure("TEntry", fieldbackground=C["card"], borderwidth=1,
                    relief="solid", padding=(8, 6), foreground=C["text"])
    style.map("TEntry", bordercolor=[("focus", C["accent"]), ("!focus", C["border"])],
              lightcolor=[("focus", C["accent"])])
    style.configure("TCombobox", fieldbackground=C["card"], borderwidth=1,
                    relief="solid", padding=(8, 6), foreground=C["text"])
    style.map("TCombobox", bordercolor=[("focus", C["accent"]), ("!focus", C["border"])])
    style.configure("TCheckbutton", background=C["bg"], foreground=C["text"],
                    font=F_UI, padding=(4, 4), indicatorrelief="flat")
    style.map("TCheckbutton", background=[("active", C["bg"])],
              indicatorcolor=[("selected", C["accent"]), ("!selected", C["card"])])

    # 标签页
    style.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(2, 6, 2, 0))
    style.configure("TNotebook.Tab", background=C["bg"], foreground=C["dim"],
                    font=F_UI, padding=(20, 10), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", C["card"]), ("active", C["hover"])],
              foreground=[("selected", C["accent"]), ("active", C["text"])],
              font=[("selected", F_UI_B)])

    # 表格
    style.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], font=F_UI, rowheight=34, borderwidth=0)
    style.configure("Treeview.Heading", background=C["head_bg"],
                    foreground=C["text"], font=F_UI_B,
                    relief="flat", borderwidth=0, padding=(10, 8))
    style.map("Treeview",
              background=[("selected", C["sel"])],
              foreground=[("selected", C["text"])])
    style.map("Treeview.Heading", background=[("active", C["head_active"])])

    # 滚动条 / 进度条 / 分隔线
    style.configure("TScrollbar", background=C["bg"], troughcolor=C["bg"],
                    borderwidth=0, arrowsize=12)
    style.map("TScrollbar", background=[("active", C["scroll"])])
    style.configure("Horizontal.TProgressbar", background=C["accent"])
    style.configure("TSeparator", background=C["border"])
    style.configure("Line.TSeparator", background=C["border"])

    try:
        root.configure(background=C["bg"])
    except Exception:
        pass
    refresh_texts()


# ---------------------------------------------------------------- 系统主题检测
def system_prefers_dark() -> bool:
    """Windows 读注册表；其他平台返回 False"""
    try:
        if __import__("sys").platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(val) == 0
    except Exception:
        pass
    return False
