# -*- coding: utf-8 -*-
"""强制解锁。

提供三类可独立开关的操作，全部只改数据、不改存档结构，
且每一步都可通过主窗口的撤销栈回滚。

  1. gameKey 标志位   —— 把每个条目的解锁标记置为「已解锁」
  2. gameKey 补条目   —— 用内置曲目名单为尚未出现的曲目补写解锁条目
  3. gameRecord 补成绩 —— 为没打过的曲目写入一条成绩记录

关于 gameKey 的字节结构（已由「解析→重建」逐字节自检验证）：

    每条 = [曲目/收藏品 ID] [长度 m] [Type] [payload...]

  Type 是一个位掩码，payload 只存放 Type 中为 1 的那些位对应的字节，
  且按位序从小到大排列，因此 m = 1 + popcount(Type)。

  社区库（PhigrosLibraryCSharp）给出的位含义：

    bit0 已读收藏品数   bit1 单曲解锁   bit2 已解锁收藏品数
    bit3 曲绘解锁       bit4 头像解锁

  但实测存档里「曲名」条目用的是 bit3(8) 而非 bit1(2)，与文档不完全一致。
  因此这里采取保守且稳妥的做法：**把出现的位一律置为非零**，
  不猜测某一位到底代表什么，也不引入原本不存在的位语义。
"""

import json
import csv
import os

import phi_paths as paths

# gameKey 位含义（仅用于界面展示与说明，不用于判定）
FLAG_BITS = [
    (0x01, "已读收藏品"),
    (0x02, "单曲解锁"),
    (0x04, "已解锁收藏品"),
    (0x08, "曲绘/曲目解锁"),
    (0x10, "头像解锁"),
]

SONGLIST_FILE = "resources/songlist.csv"


# ---------------------------------------------------------------- 曲名名单
def load_songlist():
    """[(id, 显示名, 曲师, 难度元组)]，读不到返回空列表"""
    p = paths.resource_path(SONGLIST_FILE)
    if not os.path.exists(p):
        return []
    out = []
    try:
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if not r.get("id"):
                    continue
                lv = tuple(k for k in ("EZ", "HD", "IN", "AT") if r.get(k))
                out.append((r["id"], r.get("song") or r["id"],
                            r.get("composer") or "", lv))
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- gameKey
def decode_flags(flags):
    """[m, Type, payload...] -> (Type, {bit: value})；非法返回 (None, {})"""
    try:
        f = [int(x) & 0xFF for x in flags]
        if len(f) < 2:
            return (None, {})
        m = f[0]
        if m < 1 or len(f) < 1 + m:
            return (None, {})
        t = f[1]
        payload = f[2:2 + m - 1]
        bits = [i for i in range(8) if t & (1 << i)]
        if len(bits) != len(payload):
            return (None, {})
        return (t, dict(zip(bits, payload)))
    except Exception:
        return (None, {})


def encode_flags(t, kv):
    """(Type, {bit: value}) -> [m, Type, payload...]，按位序升序重建"""
    bits = sorted(kv)
    t = 0
    for b in bits:
        t |= (1 << b)
    payload = [int(kv[b]) & 0xFF for b in bits]
    return [1 + len(payload), t] + payload


def reencode_flags(flags):
    """原样解码再编码。用于验证「不改内容则字节不变」"""
    t, kv = decode_flags(flags)
    if t is None:
        return list(flags)
    return encode_flags(t, kv)


def describe_flags(flags):
    """给界面用的可读描述，如「单曲解锁=1　曲绘/曲目解锁=1」"""
    t, kv = decode_flags(flags)
    if t is None:
        return "（无法解析）"
    name = dict(FLAG_BITS)
    parts = []
    for b in sorted(kv):
        parts.append(f"{name.get(1 << b, f'bit{b}')}={kv[b]}")
    return "　".join(parts) if parts else "（空）"


def unlock_flag_bytes(items, fill_counts=False):
    """把所有条目的 payload 字节置为非零。

    fill_counts=False 时：0 → 1，其余保持原值（布尔位因此变为 1）
    fill_counts=True  时：所有位一律置 255（收藏品计数拉满）
    返回被修改的条目数
    """
    n = 0
    for it in items:
        t, kv = decode_flags(it.get("flags") or [])
        if t is None:
            continue
        new = {}
        changed = False
        for b, v in kv.items():
            nv = 255 if fill_counts else (v if v else 1)
            if nv != v:
                changed = True
            new[b] = nv
        if changed:
            it["flags"] = encode_flags(t, new)
            n += 1
    return n


# 曲目 id -> gameKey 解锁条目显示名
def _load_unlock_map():
    p = paths.resource_path("resources/unlock_map.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("map") or {}
    except Exception:
        return {}


def unlock_name(song_id, song_title=""):
    """该曲目在 gameKey 里的解锁条目名"""
    return _load_unlock_map().get(song_id) or song_title or song_id


def set_song_unlock(items, song_ids, names=None, on=True):
    """把指定曲目在 gameKey 里的「曲绘/曲目解锁」位（bit3）置 1 / 清 0。

    这是云端真正的解锁开关 —— 已由全解锁存档对照确认：
    购买过的单曲在 gameKey 里就是 {id: 曲名, Type=0x08, bit3=1}。
    返回 (新增条目数, 更新条目数)
    """
    names = names or {}
    # 精确匹配优先：避免改动同名的收藏品条目
    # （实测 'Clock Paradox' 曲目与 'clockparadox' 收藏品是两条独立条目）
    exact = {it.get("id", ""): it for it in items}
    by = {}
    for it in items:
        by.setdefault(_norm(it.get("id", "")), []).append(it)
    added = changed = 0
    for sid in song_ids:
        name = names.get(sid) or sid
        # 仅按精确名匹配；没有就新建一条，绝不去改名字只是「长得像」的条目
        hit = [exact[name]] if name in exact else None
        if hit:
            for it in hit:
                t, kv = decode_flags(it.get("flags") or [])
                if t is None:
                    continue
                new = dict(kv)
                if on:
                    new[3] = max(1, int(kv.get(3, 0) or 0))
                else:
                    new[3] = 0
                if new != kv:
                    it["flags"] = encode_flags(t | (8 if on and 3 not in kv else 0),
                                               new)
                    changed += 1
            continue
        if not on:
            continue
        items.append({"id": name, "flags": encode_flags(0x08, {3: 1})})
        added += 1
    return (added, changed)


def load_progress_unlocked():
    """全解锁参考尾部字节"""
    try:
        with open(paths.resource_path("resources/progress_unlocked.json"),
                  encoding="utf-8") as f:
            d = json.load(f)
        return bytes(d.get("tail") or [])
    except Exception:
        return None


def _norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def add_missing_songs(items, songlist, template_bit=0x08, template_val=1):
    """为名单里有、但 gameKey 中不存在的曲目补写条目。

    已存在的同名条目：确保 template_bit 这一位存在且非零。
    不存在的：照抄已解锁曲目的模式新建。
    返回 (新增数, 修改数)
    """
    if not songlist:
        return (0, 0)
    index = {_norm(it.get("id", "")): it for it in items}
    added = changed = 0
    for sid, name, _comp, _lv in songlist:
        key = _norm(name)
        it = index.get(key)
        if it is None:
            items.append({"id": name,
                          "flags": encode_flags(template_bit,
                                                {template_bit.bit_length() - 1:
                                                 template_val})})
            index[key] = items[-1]
            added += 1
            continue
        t, kv = decode_flags(it.get("flags") or [])
        if t is None:
            # 原条目无法解析，就别动它，避免破坏
            continue
        # 已存在的条目：只把为 0 的位都置 1，不动 Type
        # （每个条目的 Type 由游戏决定，跟着它的语义走比强行加位更安全）
        new = {b: (v if v else 1) for b, v in kv.items()}
        if new != kv:
            it["flags"] = encode_flags(t, new)
            changed += 1
    return (added, changed)


# ---------------------------------------------------------------- gameRecord
def fill_missing_records(records, songlist, score=880000, acc=88.0,
                         fc=False, levels=None):
    """为没打过的曲目写入成绩。

    levels=None 时按名单里该曲实际拥有的难度全部写入；
    也可传 ("EZ",) 只补最低难度。
    返回 (新增曲目数, 补写难度数)
    """
    if not songlist:
        return (0, 0)
    have = {_norm(r.get("id", "").rsplit(".", 1)[0])
            if r.get("id", "").endswith(".0") else _norm(r.get("id", ""))
            for r in records}
    # 存档里的 id 形如 'Glaciaxion.SunsetRay.0'，名单里是 'Glaciaxion.SunsetRay'
    have = set()
    for r in records:
        rid = r.get("id", "")
        if rid.endswith(".0"):
            rid = rid[:-2]
        have.add(_norm(rid))

    added_song = added_lv = 0
    for sid, name, _comp, lv in songlist:
        if _norm(sid) in have:
            continue
        want = tuple(levels) if levels else tuple(lv)
        if not want:
            continue
        scores = {k: {"score": int(score), "acc": float(acc), "fc": bool(fc)}
                  for k in want}
        records.append({"id": sid + ".0", "scores": scores})
        added_song += 1
        added_lv += len(want)
        have.add(_norm(sid))
    return (added_song, added_lv)


# ---------------------------------------------------------------- 统计
def unlock_stats(gk_items, records, songlist):
    """给解锁对话框用的统计信息"""
    played = set()
    for r in records or []:
        rid = r.get("id", "")
        if rid.endswith(".0"):
            rid = rid[:-2]
        played.add(_norm(rid))

    locked_bits = 0
    for it in gk_items or []:
        _t, kv = decode_flags(it.get("flags") or [])
        if _t is not None and any(v == 0 for v in kv.values()):
            locked_bits += 1

    total = len(songlist)
    unplayed = sum(1 for sid, *_ in songlist if _norm(sid) not in played)

    return {"key_items": len(gk_items or []),
            "key_zero": locked_bits,
            "songs_total": total,
            "songs_played": len(played),
            "songs_unplayed": unplayed,
            "has_songlist": bool(songlist)}


def clear_song_flags(items, songlist):
    """把指定曲目在 gameKey 里的标记字节全部清零。返回修改条目数"""
    names = {_norm(n) for _sid, n, _c, _lv in songlist}
    n = 0
    for it in items:
        if _norm(it.get("id", "")) not in names:
            continue
        t, kv = decode_flags(it.get("flags") or [])
        if t is None:
            continue
        new = {b: 0 for b in kv}
        if new != kv:
            it["flags"] = encode_flags(t, new)
            n += 1
    return n


def remove_records(records, songlist):
    """删除指定曲目的成绩记录。返回删除条数"""
    want = {_norm(sid) for sid, *_ in songlist}
    keep = []
    removed = 0
    for r in records:
        rid = r.get("id", "")
        key = _norm(rid[:-2] if rid.endswith(".0") else rid)
        if key in want:
            removed += 1
            continue
        keep.append(r)
    if removed:
        records[:] = keep
    return removed
