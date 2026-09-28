# -*- coding: utf-8 -*-
"""章节结构与解锁链推导。

数据来自 resources/chapters.json（按游戏内解锁顺序排列的章节曲目），
以及 resources/songlist.csv（曲目 id 与各难度是否存在）。

核心规则（来自社区攻略，已核对多个来源）：

  * 同一首曲子：HD 达到 920000(S) 解锁 IN；IN 达到 920000(S) 解锁 AT
  * 章节内下一首曲子的对应难度：上一首曲子对应难度达到 880000(A) 才解锁
  * 因此「想打第 5 首」→ 第 1~4 首都必须在同一难度上达到 880000

本模块据此推导：选中第 N 首时，自动把第 1~N-1 首一并纳入解锁计划。
"""

import json

import phi_paths as paths

LEVEL_ORDER = ["EZ", "HD", "IN", "AT"]

# 写成绩能解开的解锁类型。special（异象/剧情触发）与 currency（Data 购买）
# 依赖 gameProgress / 购买标记，写成绩无效，故不列入解锁列表。
UNLOCKABLE = ("free", "sequential")

# 默认解锁方案：88 万分，写在最高难度上
DEFAULT_SCORE = 880000
DEFAULT_ACC = 88.0


def highest_level(levels):
    """取最高难度：AT > IN > HD > EZ；levels 为空时回退 IN"""
    for lv in reversed(LEVEL_ORDER):
        if lv in levels:
            return lv
    return "IN"


def _norm(s):
    out = []
    for ch in str(s).lower():
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff":
            out.append(ch)
    return "".join(out)


class ChapterData:
    def __init__(self):
        self.chapters = []
        self.special = {}
        self.rules = {}
        self.unlock_types = {}
        self.source_version = ""
        self._load()

    def _load(self):
        p = paths.resource_path("resources/chapters.json")
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        self.chapters = d.get("chapters") or []
        self.rules = d.get("difficulty_rules") or {}
        self.unlock_types = d.get("unlock_types") or {}
        self.source_version = d.get("source_version", "")
        for s in d.get("special_songs") or []:
            self.special[_norm(s.get("title", ""))] = s

    # ---------------------------------------------------------------- 查询
    def is_special(self, title):
        return _norm(title) in self.special

    @staticmethod
    def _kind(song):
        """解锁类型归类：ok / blocked_special / blocked_currency / unknown"""
        title = song.get("title", "")
        unlock = str(song.get("unlock", "")).split("（")[0].split("(")[0].strip()
        if unlock == "special":
            return "blocked_special"
        if unlock == "currency":
            return "blocked_currency"
        if unlock in UNLOCKABLE:
            return "ok"
        return "unknown"

    def is_unlockable(self, song):
        """是否列入解锁列表：确认解不开的（异象触发 / Data 购买）排除"""
        return self._kind(song) in ("ok", "unknown")

    def is_unconfirmed(self, song):
        """解锁方式未知（未收录到章节，无法推导前置链）"""
        return self._kind(song) == "unknown"

    def blocked_counts(self):
        """被排除的曲目数"""
        out = {"blocked_special": 0, "blocked_currency": 0, "unknown": 0}
        for c in self.chapters:
            for s in c["songs"]:
                out[self._kind(s)] = out.get(self._kind(s), 0) + 1
        return out

    def special_info(self, title):
        return self.special.get(_norm(title))

    def total_songs(self):
        return sum(len(c["songs"]) for c in self.chapters)

    def played_keys(self, records):
        """已有成绩记录的曲目 id 集合（严格按 '曲名.曲师' 全名匹配，
        避免同名不同曲师被误判为已游玩）"""
        out = set()
        for r in records or []:
            rid = r.get("id", "")
            if rid.endswith(".0"):
                rid = rid[:-2]
            out.add(_norm(rid))
        return out

    def plan(self, chapter_id, target_index, played, score=DEFAULT_SCORE,
             acc=DEFAULT_ACC, level_mode="highest"):
        """推导解锁计划。

        chapter_id  : 章节 id
        target_index: 想解锁第几首（1 起）
        played      : played_keys() 的结果
        level_mode  : "highest" 只写最高难度；"all" 写全部难度

        返回 dict：
          items  : [{index, title, id, level, levels, unlock, special, skip_reason}]
                   已游玩的会带 skip_reason="已游玩"
          warnings: [str]  特殊曲/章节门槛等提示
        """
        ch = self._find(chapter_id)
        if ch is None:
            return {"items": [], "warnings": ["未找到该章节"]}
        songs = ch["songs"]
        target = max(1, min(int(target_index), len(songs)))

        items = []
        warnings = []
        for s in songs[:target]:
            lv = s.get("levels") or ["EZ", "HD", "IN"]
            one = highest_level(lv) if level_mode == "highest" else None
            want = [one] if one else list(lv)
            special = self.is_special(s["title"])
            key = _norm(s.get("id", ""))
            skip = "已游玩" if key in played else ""
            items.append({"index": s["index"], "title": s["title"],
                          "id": s["id"], "levels": list(lv), "level": want[0],
                          "write_levels": want,
                          "unlock": s.get("unlock", ""),
                          "special": special, "skip_reason": skip,
                          "note": s.get("note", "")})
            if special and not skip:
                info = self.special_info(s["title"])
                trig = "；".join(info.get("trigger", [])) if info else ""
                warnings.append(
                    f"「{s['title']}」是特殊触发曲，写成绩大概率无法解锁。"
                    + (f"官方条件：{trig}" if trig else ""))
            if s.get("unlock") == "currency" and not skip:
                warnings.append(f"「{s['title']}」需用 Data 货币购买，写成绩不一定能解锁。")

        if ch.get("chapter_gate"):
            warnings.append(f"章节门槛：{ch['chapter_gate']}")
        return {"items": items, "warnings": warnings}

    def _find(self, cid):
        for c in self.chapters:
            if c["id"] == cid:
                return c
        return None


def apply_plan(records, items, score=DEFAULT_SCORE, acc=DEFAULT_ACC):
    """按计划写入成绩。返回 (新增曲目数, 新增难度记录数)"""
    added_song = added_lv = 0
    for it in items:
        if it.get("skip_reason"):
            continue
        sid = it["id"]
        rid = sid if sid.endswith(".0") else sid + ".0"
        want = it.get("write_levels") or [it["level"]]
        cur = None
        for r in records:
            if r.get("id") == rid:
                cur = r
                break
        if cur is None:
            cur = {"id": rid, "scores": {}}
            records.append(cur)
            added_song += 1
        for lv in want:
            old = cur["scores"].get(lv)
            if old is not None and isinstance(old, dict):
                # 已有成绩：绝不覆盖，更不会把高分改低
                continue
            cur["scores"][lv] = {"score": int(score), "acc": float(acc),
                                 "fc": False}
            added_lv += 1
    return (added_song, added_lv)
