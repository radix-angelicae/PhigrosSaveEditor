# -*- coding: utf-8 -*-
"""Phigros 云存档格式：加解密、解析、序列化、zip 读写、自检与数据校验。

不依赖 tkinter，可被命令行自检单独导入。
"""

import base64
import json
import struct
import zipfile

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ---------------------------------------------------------------- 常量
AES_KEY = base64.b64decode("6Jaa0qVAJZuXkZCLiOa/Ax5tIZVu+taKUN1V1nqwkks=")  # AES-256
AES_IV = base64.b64decode("Kk/wisgNYwcAV8WVGMgyUw==")

LEVELS = ["EZ", "HD", "IN", "AT"]
ENTRY_ORDER = ["gameRecord", "gameKey", "gameProgress", "settings", "user"]

ENTRY_LABEL = {
    "gameRecord": "曲目成绩",
    "gameKey": "解锁数据",
    "gameProgress": "游戏进度",
    "settings": "游戏设置",
    "user": "用户资料",
}

HINTS = {
    "gameRecord": "双击单元格即可修改；分数 0~1000000，ACC 为百分比。删除某难度 = 视为未通关。",
    "gameKey": "解锁数据。flags 为位打包原始字节，改前建议先记下原值；可整行复制同类项的 flags。",
    "gameProgress": "challengeRank = 课题分；gameVersion 为存档版本串。",
    "settings": "设备名可改；下方数值多为音量/延迟/缩放（1.0 量级通常是音量），不确定请勿改。",
    "user": "个人简介与头像 id，可直接编辑。",
}


# ================================================================ 加解密
def aes_decrypt(blob: bytes):
    version = blob[0]
    plain = unpad(AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(blob[1:]), 16)
    return version, plain


def aes_encrypt(version: int, plain: bytes) -> bytes:
    return bytes([version]) + AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(plain, 16))


# ================================================================ Phi 二进制流
class Reader:
    def __init__(self, b: bytes):
        self.b, self.i = b, 0

    def varint(self):
        v = sh = 0
        while True:
            c = self.b[self.i]
            self.i += 1
            v |= (c & 0x7F) << sh
            if not c & 0x80:
                return v
            sh += 7

    def string(self):
        n = self.varint()
        s = self.b[self.i:self.i + n].decode("utf-8", "replace")
        self.i += n
        return s

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.i)[0]
        self.i += 4
        return v

    def f32(self):
        v = struct.unpack_from("<f", self.b, self.i)[0]
        self.i += 4
        return v

    def rest(self):
        return list(self.b[self.i:])


class Writer(bytearray):
    def varint(self, v):
        while v >= 0x80:
            self.append((v & 0x7F) | 0x80)
            v >>= 7
        self.append(v)

    def string(self, s: str):
        raw = s.encode("utf-8")
        self.varint(len(raw))
        self.extend(raw)


# ================================================================ 解析
def parse_game_record(d: bytes) -> dict:
    r = Reader(d)
    records = []
    for _ in range(r.varint()):
        sid = r.string()
        exists, fc = r.b[r.i + 1], r.b[r.i + 2]
        r.i += 3                                   # 跳过 [长度][exists][fc]
        scores = {}
        for k, lv in enumerate(LEVELS):
            if exists & (1 << k):
                scores[lv] = {"score": r.i32(), "acc": r.f32(), "fc": bool(fc & (1 << k))}
        records.append({"id": sid, "scores": scores})
    return {"_tail": r.rest(), "records": records}


def parse_game_key(d: bytes) -> dict:
    r = Reader(d)
    items = []
    for _ in range(r.varint()):
        sid = r.string()
        m = r.b[r.i]
        flags = list(r.b[r.i:r.i + 1 + m])
        r.i += 1 + m
        items.append({"id": sid, "flags": flags})
    return {"_tail": r.rest(), "items": items}


def parse_settings(d: bytes) -> dict:
    r = Reader(d)
    head = r.b[r.i]; r.i += 1
    name = r.string()
    tail = r.rest()
    obj = {"_tail": tail, "headerByte": head, "deviceName": name}
    if tail and len(tail) % 4 == 0:                # 尾部可解读为浮点序列
        obj["_tailFloats"] = [struct.unpack_from("<f", bytes(tail), i)[0]
                              for i in range(0, len(tail), 4)]
    return obj


def parse_user(d: bytes) -> dict:
    r = Reader(d)
    b0 = r.b[r.i]; r.i += 1
    intro = r.string()
    b1 = r.b[r.i]; r.i += 1
    avatar = r.string()
    return {"_tail": r.rest(), "byte0": b0, "byte1": b1,
            "introduction": intro, "avatar": avatar}


def parse_game_progress(d: bytes) -> dict:
    r = Reader(d)
    challenge = r.varint()
    version = r.string()
    return {"_tail": r.rest(), "challengeRank": challenge, "gameVersion": version}


PARSERS = {
    "gameRecord": parse_game_record,
    "gameKey": parse_game_key,
    "gameProgress": parse_game_progress,
    "settings": parse_settings,
    "user": parse_user,
}


# ================================================================ 重建
def build_game_record(o: dict) -> bytes:
    w = Writer()
    recs = o["records"]
    w.varint(len(recs))
    for rec in recs:
        w.string(rec["id"])
        sc = rec.get("scores", {})
        exists = fc = 0
        for k, lv in enumerate(LEVELS):
            if lv in sc and sc[lv] is not None:
                exists |= 1 << k
                if sc[lv].get("fc"):
                    fc |= 1 << k
        w.append(2 + 8 * bin(exists).count("1"))
        w.append(exists)
        w.append(fc)
        for k, lv in enumerate(LEVELS):
            if exists & (1 << k):
                s = sc[lv]
                w.extend(struct.pack("<i", int(s.get("score", 0))))
                w.extend(struct.pack("<f", float(s.get("acc", 0.0))))
    w.extend(bytes(o.get("_tail", [])))
    return bytes(w)


def build_game_key(o: dict) -> bytes:
    w = Writer()
    w.varint(len(o["items"]))
    for it in o["items"]:
        w.string(it["id"])
        w.extend(bytes(it["flags"]))
    w.extend(bytes(o.get("_tail", [])))
    return bytes(w)


def build_settings(o: dict) -> bytes:
    w = Writer()
    w.append(int(o["headerByte"]) & 0xFF)
    w.string(o["deviceName"])
    tail = o.get("_tail", [])
    fs = o.get("_tailFloats")
    if fs is not None and len(fs) * 4 == len(tail):
        tail = [b for f in fs for b in struct.pack("<f", float(f))]
    w.extend(bytes(tail))
    return bytes(w)


def build_user(o: dict) -> bytes:
    w = Writer()
    w.append(int(o["byte0"]) & 0xFF)
    w.string(o["introduction"])
    w.append(int(o["byte1"]) & 0xFF)
    w.string(o["avatar"])
    w.extend(bytes(o.get("_tail", [])))
    return bytes(w)


def build_game_progress(o: dict) -> bytes:
    w = Writer()
    w.varint(int(o["challengeRank"]))
    w.string(o["gameVersion"])
    w.extend(bytes(o.get("_tail", [])))
    return bytes(w)


BUILDERS = {
    "gameRecord": build_game_record,
    "gameKey": build_game_key,
    "gameProgress": build_game_progress,
    "settings": build_settings,
    "user": build_user,
}


def parse_entry(name: str, plain: bytes):
    try:
        obj = PARSERS[name](plain)
        obj["_verified"] = (BUILDERS[name](obj) == plain)
        if not obj["_verified"]:
            obj["_rawBase64"] = base64.b64encode(plain).decode()
    except Exception as e:
        obj = {"_verified": False, "_parseError": str(e),
               "_rawBase64": base64.b64encode(plain).decode()}
    return obj


def build_entry(name: str, obj: dict) -> bytes:
    if isinstance(obj, dict) and obj.get("_rawBase64"):
        return base64.b64decode(obj["_rawBase64"])
    return BUILDERS[name](obj)


# ================================================================ 存档读写
def load_archive(path: str):
    zf = zipfile.ZipFile(path)
    names = list(zf.namelist())
    for n in ENTRY_ORDER:
        if n in names:
            names.remove(n)
            names.insert(ENTRY_ORDER.index(n), n)
    out = {}
    for n in names:
        ver, plain = aes_decrypt(zf.read(n))
        out[n] = (ver, plain, zf.getinfo(n))
    return names, out


def save_archive(path: str, names, originals, plain_map):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            ver, _old, info = originals[n]
            zi = zipfile.ZipInfo(n, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zf.writestr(zi, aes_encrypt(ver, plain_map[n]))


def build_zip_bytes(names, originals, plain_map) -> bytes:
    """按给定条目顺序生成与原版结构一致的 zip 字节"""
    import io as _io
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            ver, _old, info = originals[n]
            zi = zipfile.ZipInfo(n, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zf.writestr(zi, aes_encrypt(ver, plain_map[n]))
    return buf.getvalue()


def selftest(path: str):
    names, entries = load_archive(path)
    print(f"Self-test: {path}")
    ok = True
    for n in names:
        ver, plain, _ = entries[n]
        obj = parse_entry(n, plain)
        try:
            same = build_entry(n, obj) == plain
        except Exception as e:
            same = False
            print(f"  {n}: rebuild error {e}")
        ok &= same
        print(f"  {n:14s} v{ver}  {len(plain):5d} B  roundtrip {'OK' if same else 'MISMATCH'}")
    print("Result:", "all entries safe to edit" if ok else "some entries mismatch (raw fallback used)")
    return ok


# ================================================================ 小工具
def grade_of(score: int, acc: float) -> str:
    """评级（按社区常用阈值推算，仅供参考）"""
    if score >= 1000000:
        return "φ"
    if score >= 960000:
        return "V"
    if score >= 920000:
        return "S"
    if score >= 880000:
        return "A"
    if score >= 820000:
        return "B"
    if score >= 700000:
        return "C"
    return "F"


def clamp_score(v) -> int:
    try:
        return max(0, min(1000000, int(round(float(v)))))
    except Exception:
        return 0


def clamp_acc(v) -> float:
    try:
        return max(0.0, min(100.0, float(v)))
    except Exception:
        return 0.0


def hexs(flags) -> str:
    return " ".join(f"{b:02X}" for b in flags)


HINTS = {
    "gameRecord": "双击单元格即可修改；分数 0~1000000，ACC 为百分比。删除某难度 = 视为未通关。",
    "gameKey": "解锁数据。flags 为位打包原始字节，改前建议先记下原值；可整行复制同类项的 flags。",
    "gameProgress": "challengeRank = 课题分；gameVersion 为存档版本串。",
    "settings": "设备名可改；下方数值多为音量/延迟/缩放（1.0 量级通常是音量），不确定请勿改。",
    "user": "个人简介与头像 id，可直接编辑。",
}



# ================================================================ 数据矛盾校验
def validate_records(records, max_report=20):
    """检查成绩数据的常见矛盾，返回问题列表 [(曲目, 难度, 说明)]"""
    issues = []
    for r in records or []:
        sid = str(r.get("id", ""))
        for lv, s in (r.get("scores") or {}).items():
            if not isinstance(s, dict):
                issues.append((sid, lv, "成绩项不是合法对象"))
                continue
            sc = s.get("score", 0)
            ac = s.get("acc", 0.0)
            try:
                sc = int(sc)
            except Exception:
                issues.append((sid, lv, f"分数不是整数：{sc!r}"))
                continue
            try:
                ac = float(ac)
            except Exception:
                issues.append((sid, lv, f"ACC 不是数字：{ac!r}"))
                continue
            if not 0 <= sc <= 1000000:
                issues.append((sid, lv, f"分数超出 0~1000000：{sc}"))
            if not 0.0 <= ac <= 100.0:
                issues.append((sid, lv, f"ACC 超出 0~100：{ac}"))
            if ac >= 100.0 and sc < 1000000:
                issues.append((sid, lv, f"ACC=100% 但分数未满（{sc}）"))
            if sc >= 1000000 and ac < 100.0:
                issues.append((sid, lv, f"满分但 ACC 不足 100%（{ac:.4f}）"))
            if s.get("fc") and ac < 60.0:
                issues.append((sid, lv, f"标记 FC 但 ACC 偏低（{ac:.2f}%）"))
            if sc <= 0 and ac > 0:
                issues.append((sid, lv, f"分数为 0 但 ACC 非 0（{ac:.2f}%）"))
            if len(issues) >= max_report:
                return issues
    return issues


def validate_entry(name, obj):
    """对单个条目做校验，返回问题字符串列表"""
    out = []
    if not isinstance(obj, dict):
        return [f"{name} 不是合法对象"]
    if name == "gameRecord":
        for sid, lv, msg in validate_records(obj.get("records")):
            out.append(msg)
    if name == "user":
        if not isinstance(obj.get("introduction", ""), str):
            out.append("个人简介不是文本")
    if name == "settings":
        if not isinstance(obj.get("deviceName", ""), str):
            out.append("设备名不是文本")
    if name == "gameProgress":
        try:
            int(obj.get("challengeRank", 0))
        except Exception:
            out.append("课题分不是整数")
    return out


