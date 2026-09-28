# -*- coding: utf-8 -*-
"""
Phigros 云存档 —— LeanCloud / TapTap 接口封装（仅用标准库 urllib，无额外依赖）

接口流程（均照官方客户端实测行为实现）：
  拉取：GET /1.1/users/me → GET /1.1/classes/_GameSave?where=...&include=gameFile → 下载 gameFile.url
  上传：POST /1.1/fileTokens → 七牛分片初始化 → PUT 分片 → 合并 → POST /1.1/fileCallback
        → PUT /1.1/classes/_GameSave/{id} → DELETE /1.1/files/{旧文件id}

鉴权：X-LC-Sign = md5(毫秒时间戳 + AppKey), 毫秒时间戳
"""

import base64
import hashlib
import json
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

# ------------------------------------------------------------------ 服务端配置
SERVERS = {
    "国服": "https://rak3ffdi.cloud.tds1.tapapis.cn/1.1",
    "国际服": "https://kviehlel.cloud.ap-sg.tapapis.com/1.1",
}
APP_ID = "rAK3FfdieFob2Nn8Am"
APP_KEY = "Qr9AEqtuoSVS3zeD6iVbM4ZC0AtkJcQ89tywVyi0"
UA = "LeanCloud-CSharp-SDK/1.0.3"


class CloudError(Exception):
    pass


# ------------------------------------------------------------------ 基础请求
def _sign():
    ts = str(int(time.time() * 1000))
    return f"{hashlib.md5((ts + APP_KEY).encode()).hexdigest()},{ts}"


def _req(url, method="GET", data=None, headers=None, timeout=30):
    """data: bytes/str 或 None；返回 (status, body_bytes)"""
    req = urllib.request.Request(url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    body = None
    if data is not None:
        body = data.encode("utf-8") if isinstance(data, str) else data
        req.add_header("Content-Length", str(len(body)))
    try:
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        raise CloudError(f"网络请求失败：{e}")


def _lc(method, path, session_token, server, body=None, timeout=30):
    """LeanCloud API 请求，返回 dict"""
    h = {
        "X-LC-Id": APP_ID,
        "X-LC-Session": session_token,
        "X-LC-Sign": _sign(),
        "User-Agent": UA,
        "Accept": "application/json",
    }
    if body is not None:
        h["Content-Type"] = "application/json"
    st, raw = _req(server + path, method,
                   json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else None,
                   h, timeout)
    try:
        j = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        raise CloudError(f"服务端返回异常 (HTTP {st})：{raw[:200]!r}")
    if st >= 400:
        raise CloudError(f"HTTP {st}：{j.get('error', j)}")
    return j


# ------------------------------------------------------------------ 账号 / 查询
def get_user(session_token: str, server: str):
    """返回 dict：objectId / nickname / username"""
    u = _lc("GET", "/users/me", session_token, server)
    if "objectId" not in u:
        raise CloudError(f"sessionToken 无效或已过期：{u}")
    return u


def list_saves(session_token: str, server: str, user_id: str):
    """返回存档列表（按更新时间倒序）"""
    where = {"user": {"__type": "Pointer", "className": "_User", "objectId": user_id}}
    q = urllib.parse.urlencode({
        "skip": 0, "limit": 100,
        "where": json.dumps(where, separators=(",", ":")),
        "include": "cover,gameFile",
    })
    r = _lc("GET", "/classes/_GameSave?" + q, session_token, server)
    saves = r.get("results", [])
    saves.sort(key=lambda s: s.get("updatedAt", ""), reverse=True)
    return saves


def save_meta(s: dict) -> dict:
    """把一条 _GameSave 记录整理成展示用的字典"""
    gf = s.get("gameFile") or {}
    return {
        "saveObjectId": s.get("objectId"),
        "url": gf.get("url"),
        "fileObjectId": gf.get("objectId"),
        "size": (gf.get("metaData") or {}).get("size"),
        "checksum": (gf.get("metaData") or {}).get("_checksum"),
        "updatedAt": s.get("updatedAt"),
        "modifiedAt": (s.get("modifiedAt") or {}).get("iso"),
        "summary": s.get("summary"),
        "name": s.get("name"),
    }


def download(url: str, timeout=60) -> bytes:
    st, raw = _req(url, "GET", None, {"User-Agent": UA}, timeout)
    if st != 200 or len(raw) < 4:
        raise CloudError(f"下载失败 (HTTP {st}, {len(raw)} 字节)")
    return raw


# ------------------------------------------------------------------ summary 编解码
def decode_summary(b64: str) -> dict:
    """summary = u8版本 + u16课题等级 + f32 RKS + varint游戏版本 + PhiString头像 + 12×u16"""
    try:
        s = base64.b64decode(b64)
    except Exception:
        return {}
    if len(s) < 7:
        return {}
    ver = s[0]
    rank = struct.unpack_from("<H", s, 1)[0]
    rks = struct.unpack_from("<f", s, 3)[0]
    i, v, sh = 7, 0, 0
    while i < len(s):
        c = s[i]
        i += 1
        v |= (c & 0x7F) << sh
        if not c & 0x80:
            break
        sh += 7
    n = s[i]
    i += 1
    avatar = s[i:i + n].decode("utf-8", "replace")
    i += n
    lv = list(struct.unpack_from("<12H", s, i)) if i + 24 <= len(s) else []
    names = ["EZ通关", "EZ的FC", "EZ的φ", "HD通关", "HD的FC", "HD的φ",
             "IN通关", "IN的FC", "IN的φ", "AT通关", "AT的FC", "AT的φ"]
    return {"saveVersion": ver, "challengeRank": rank, "rks": rks,   # rks 保留原精度以保证可回写
            "gameVersion": v, "avatar": avatar,
            "levelRecords": dict(zip(names, lv)) if lv else {},
            "_raw": b64}


def encode_summary(d: dict) -> str:
    """与 decode_summary 互逆；缺字段时用原值兜底"""
    if not d:
        return ""
    if d.get("_raw") and not any(d.get(k) is not None for k in ("rks", "challengeRank", "levelRecords")):
        return d["_raw"]
    b = bytearray()
    b.append(int(d.get("saveVersion", 6)) & 0xFF)
    b.extend(struct.pack("<H", int(d.get("challengeRank", 0)) & 0xFFFF))
    b.extend(struct.pack("<f", float(d.get("rks", 0.0))))
    v = int(d.get("gameVersion", 0))
    while v >= 0x80:
        b.append((v & 0x7F) | 0x80)
        v >>= 7
    b.append(v)
    av = str(d.get("avatar", "")).encode("utf-8")
    b.append(len(av))
    b.extend(av)
    lr = d.get("levelRecords") or {}
    names = ["EZ通关", "EZ的FC", "EZ的φ", "HD通关", "HD的FC", "HD的φ",
             "IN通关", "IN的FC", "IN的φ", "AT通关", "AT的FC", "AT的φ"]
    b.extend(struct.pack("<12H", *[int(lr.get(n, 0)) & 0xFFFF for n in names]))
    return base64.b64encode(bytes(b)).decode()


def recalc_level_records(records) -> dict:
    """按 gameRecord 统计各难度 通关/FC/φ 数量（用于重算 summary）"""
    cnt = {n: 0 for n in ["EZ通关", "EZ的FC", "EZ的φ", "HD通关", "HD的FC", "HD的φ",
                          "IN通关", "IN的FC", "IN的φ", "AT通关", "AT的FC", "AT的φ"]}
    idx = {"EZ": 0, "HD": 3, "IN": 6, "AT": 9}
    for r in records or []:
        for lv, s in (r.get("scores") or {}).items():
            if lv not in idx:
                continue
            base = idx[lv]
            if int(s.get("score", 0)) > 0:
                cnt[["EZ通关", "EZ的FC", "EZ的φ", "HD通关", "HD的FC", "HD的φ",
                     "IN通关", "IN的FC", "IN的φ", "AT通关", "AT的FC", "AT的φ"][base]] += 1
                if s.get("fc"):
                    cnt[["EZ通关", "EZ的FC", "EZ的φ", "HD通关", "HD的FC", "HD的φ",
                         "IN通关", "IN的FC", "IN的φ", "AT通关", "AT的FC", "AT的φ"][base + 1]] += 1
                if int(s.get("score", 0)) >= 1000000:
                    cnt[["EZ通关", "EZ的FC", "EZ的φ", "HD通关", "HD的FC", "HD的φ",
                         "IN通关", "IN的FC", "IN的φ", "AT通关", "AT的FC", "AT的φ"][base + 2]] += 1
    return cnt


# ------------------------------------------------------------------ 上传
class Uploader:
    """按官方客户端流程上传存档 zip"""

    def __init__(self, session_token, server, user_id, progress=None):
        self.tk, self.srv, self.uid = session_token, server, user_id
        self.progress = progress or (lambda m: None)

    # 1) 申请上传令牌
    def _file_token(self, size, checksum):
        body = {
            "name": ".save",
            "__type": "File",
            "ACL": {self.uid: {"read": True, "write": True}},
            "prefix": "gamesaves",
            "metaData": {"size": size, "_checksum": checksum, "prefix": "gamesaves"},
        }
        return _lc("POST", "/fileTokens", self.tk, self.srv, body)

    # 2~4) 七牛分片上传（单分片）
    def _qiniu_put(self, upload_url, bucket, key, token, data, checksum_md5):
        b64key = base64.b64encode(key.encode()).decode()
        base = f"{upload_url}/buckets/{bucket}/objects/{b64key}/uploads"
        auth = {"Authorization": f"UpToken {token}"}

        self.progress("初始化分片上传…")
        st, raw = _req(base, "POST", b"", dict(auth, **{"Content-Length": "0"}))
        if st != 200:
            raise CloudError(f"初始化上传失败 (HTTP {st})：{raw[:200]!r}")
        upload_id = json.loads(raw).get("uploadId")
        if not upload_id:
            raise CloudError(f"未取得 uploadId：{raw[:200]!r}")

        self.progress(f"上传存档（{len(data)} 字节）…")
        h = dict(auth, **{"Content-Type": "application/octet-stream",
                          "Content-MD5": base64.b64encode(bytes.fromhex(checksum_md5)).decode()})
        st, raw = _req(f"{base}/{upload_id}/1", "PUT", data, h, timeout=120)
        if st != 200:
            raise CloudError(f"上传分片失败 (HTTP {st})：{raw[:200]!r}")
        etag = json.loads(raw).get("etag")

        self.progress("合并分片…")
        h = dict(auth, **{"Content-Type": "application/json"})
        st, raw = _req(f"{base}/{upload_id}", "POST",
                       json.dumps({"parts": [{"partNumber": 1, "etag": etag}]},
                                  separators=(",", ":")).encode(), h)
        if st != 200:
            raise CloudError(f"合并分片失败 (HTTP {st})：{raw[:200]!r}")
        return etag

    # 主流程
    def upload(self, data: bytes, summary_b64: str, save_object_id: str,
               old_file_object_id=None, delete_old=True):
        checksum = hashlib.md5(data).hexdigest()

        self.progress("申请上传令牌…")
        tok = self._file_token(len(data), checksum)
        bucket, key = tok.get("bucket"), tok.get("key")
        token, upload_url = tok.get("token"), tok.get("upload_url")
        file_obj_id = tok.get("objectId")
        if not all([bucket, key, token, upload_url]):
            raise CloudError(f"获取上传令牌失败：{tok}")

        self._qiniu_put(upload_url, bucket, key, token, data, checksum)

        self.progress("通知服务端…")
        _lc("POST", "/fileCallback", self.tk, self.srv, {"result": True, "token": token})

        self.progress("更新存档记录…")
        now = time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime())
        now += f"{int(time.time() * 1000) % 1000:03d}Z"
        body = {
            "summary": summary_b64,
            "modifiedAt": {"__type": "Date", "iso": now},
            "gameFile": {"__type": "Pointer", "className": "_File", "objectId": file_obj_id},
            "ACL": {self.uid: {"read": True, "write": True}},
            "user": {"__type": "Pointer", "className": "_User", "objectId": self.uid},
        }
        _lc("PUT", f"/classes/_GameSave/{save_object_id}?", self.tk, self.srv, body)

        if delete_old and old_file_object_id and old_file_object_id != file_obj_id:
            try:
                self.progress("清理旧文件…")
                _lc("DELETE", f"/files/{old_file_object_id}", self.tk, self.srv)
            except Exception:
                pass  # 清理失败不影响上传结果

        self.progress("完成")
        return {"fileObjectId": file_obj_id, "size": len(data), "checksum": checksum}
