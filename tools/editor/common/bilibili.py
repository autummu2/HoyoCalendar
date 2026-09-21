"""B站动态抓取 — 从米哈游官方账号动态获取公告栏拿不到的信息。

用途（见 tools/editor/genshin/RULES.md）：
- 前瞻直播时间、版本名（米游社公告栏没有前瞻公告）
- 卡池日期（米游社卡池公告是图片，读不到文字）

接口为 B站新版动态流 API（x/polymer/web-dynamic/v1/feed/space）。
过风控三要素（缺一不可，参考 BilibiliCrawler）：
1. trust_env=False —— 绕过系统代理（Clash 等会把 B站流量送去国外节点，触发 -352/-412）；
2. buvid3/buvid4 匿名标识（首页 Set-Cookie + finger/spi）；
3. web_location/features 参数。
即使齐全，连续请求仍会触发软风控：不报错但返回 code=0 + 空列表，故带重试。
"""

from __future__ import annotations

import os
import random
import re
import time
import datetime

import requests

# 原神官方 B站账号 uid
GENSHIN_UID = 401742377

# 登录 cookie（可选）。未登录的匿名请求会被 B站风控拦截（-352 / 空列表），
# 建议在浏览器登录 B站后，从开发者工具复制 SESSDATA 值，设为环境变量：
#   BILI_SESSDATA=xxxx
SESSDATA = os.environ.get("BILI_SESSDATA", "")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"


def _session(uid: int) -> requests.Session:
    """建立带匿名标识（buvid）的会话，B站风控要求。"""
    s = requests.Session()
    # 关键：绕过系统代理（Clash 等）。requests 默认 trust_env=True 会走系统代理，
    # 把 B站流量送去国外出口节点，触发 -352/-412 风控。参考 BilibiliCrawler。
    s.trust_env = False
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://space.bilibili.com",
        "Referer": f"https://space.bilibili.com/{uid}/dynamic",
    })
    # 首页引导：让 B站通过 Set-Cookie 自然下发 buvid3/b_nut 等匿名标识，
    # 比单独调 finger/spi 更接近真实浏览器，风控更友好（参考 biliwatch）。
    try:
        s.get("https://www.bilibili.com/", timeout=15)
    except Exception:
        pass
    try:
        b = s.get(SPI_URL, timeout=15).json().get("data", {})
    except Exception:
        b = {}
    if b.get("b_3"):
        s.cookies.set("buvid3", b["b_3"], domain=".bilibili.com")
    if b.get("b_4"):
        s.cookies.set("buvid4", b["b_4"], domain=".bilibili.com")
    if SESSDATA:
        s.cookies.set("SESSDATA", SESSDATA, domain=".bilibili.com")
    return s


def _feed(s: requests.Session, uid: int, offset: str = "") -> dict:
    params = {
        "host_mid": uid,
        "timezone_offset": -480,
        "features": "itemOpusStyle,listOnlyfans",
        "web_location": "333.1296",
    }
    if offset:
        params["offset"] = offset
    r = s.get(FEED_URL, params=params, timeout=20)
    return r.json()


def _extract_text(md: dict) -> str:
    """从 module_dynamic 提取正文。不同动态类型正文位置不同：
    - 转发 / 视频：desc.text
    - 图文动态（OPUS）：major.opus.summary.text（此时 desc.text 为空）
    - 旧版图文：major.draw.items 里的 text 节点
    """
    desc = md.get("desc") or {}
    text = desc.get("text") or ""
    if not text:
        opus = (md.get("major") or {}).get("opus") or {}
        text = (opus.get("summary") or {}).get("text") or ""
    if not text:
        draw = (md.get("major") or {}).get("draw") or {}
        parts = [it.get("text") for it in (draw.get("items") or []) if it.get("text")]
        text = "\n".join(parts)
    return text


def fetch_dynamics(uid: int = GENSHIN_UID, limit: int = 20, retries: int = 3) -> list[dict]:
    """抓取账号最近的动态，返回 [{id, type, text, pub_ts}]（按时间倒序）。"""
    s = _session(uid)
    items: list[dict] = []
    offset = ""
    while len(items) < limit:
        data = {}
        for attempt in range(retries):
            try:
                d = _feed(s, uid, offset)
            except Exception:
                d = {}
            # code==0 且返回了条目才算成功。软风控时 B站不报错、
            # 直接返回 code=0 + 空列表，需一并当作需重试的情况。
            if d.get("code") == 0 and (d.get("data") or {}).get("items"):
                data = d["data"]
                break
            # 命中风控（-352 / -412 或软风控空列表）时指数退避重试
            time.sleep((attempt + 1) * 10 + random.uniform(2, 6))
        if not data:
            break
        for it in data.get("items") or []:
            mods = it.get("modules", {})
            author = mods.get("module_author", {})
            md = mods.get("module_dynamic") or {}  # module_dynamic 可能为 null
            items.append({
                "id": it.get("id_str", ""),
                "type": it.get("type", ""),
                "text": _extract_text(md),
                # pub_ts 为秒级时间戳，缺失时退回字符串 pub_time
                "pub_ts": author.get("pub_ts") or author.get("pub_time"),
            })
        if not data.get("has_more") or not data.get("offset"):
            break
        offset = data["offset"]
        time.sleep(random.uniform(1, 3))  # 分页间隔，降低触发软风控的概率
    return items[:limit]


def _resolve_year(month: int, day: int, pub_ts) -> str | None:
    """把「X月X日」补全年份。前瞻预告发布在前瞻当天之前，故日期晚于发布日时用同年，
    早于发布日（跨年）时用次年。

    pub_ts 本应是秒级时间戳，但 fetch_dynamics 在它缺失时会退回**字符串** pub_time，
    两者都可能不可解析。此时退回今年、不做跨年判断（略差一点，但不会再抛异常）。

    pub_date 必须先绑定成 None：下面的比较要读它，而「变量未绑定」抛的是 NameError，
    不是 ValueError——原来那个 except 捕不住，会一路冒到 pipeline，被 maintain.py 的
    每游戏 try 接住后**该游戏当轮整个作废**（一条都不落盘）。

    月日与年份凑不出合法日期时返回 None，由调用方当「这条没日期」处理：正则误匹配出的
    「13月45日」、或两个候选年份都不是闰年的「2月29日」。拼非法串出去更糟——前端 Zod
    会把**整份**数据文件拒收。
    """
    pub_date = None
    try:
        pub_date = datetime.datetime.fromtimestamp(int(pub_ts)).date()
    except (TypeError, ValueError, OSError):
        pass
    year = pub_date.year if pub_date else datetime.date.today().year
    # 同年解析出的日子若早于发布日，只能是跨年，顺延一年；两年都凑不出合法日期就放弃
    for y in (year, year + 1):
        try:
            d = datetime.date(y, month, day)
        except ValueError:
            continue
        if not pub_date or d >= pub_date:
            return f"{y:04d}-{month:02d}-{day:02d}"
    return None


def parse_livestream(text: str, pub_ts=None) -> dict | None:
    """从前瞻预告动态文本提取 {version, name, date}。

    匹配示例：
      #原神7.1版本前瞻特别节目# 《原神》7.1版本「往冥府的安魂歌」前瞻特别节目
      将于9月12日（本周六）晚20:00正式开启。
    仅识别「预告公告」（含「开启」）；前瞻结束后的回顾长图、录播视频等
    虽也含「前瞻特别节目」，但不算预告公告，返回 None。
    """
    if "前瞻特别节目" not in text or "开启" not in text:
        return None
    result: dict = {}
    # 版本号：7.1版本
    m = re.search(r"(\d+\.\d+)\s*版本", text)
    if m:
        result["version"] = m[1]
    # 版本名：书名号内
    m = re.search(r"[「『]([^」』]{2,40})[」』]", text)
    if m:
        result["name"] = m[1]
    # 前瞻日期：X月X日（月日非法时不落 date 键，当「这条没日期」处理）
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        d = _resolve_year(int(m[1]), int(m[2]), pub_ts)
        if d:
            result["date"] = d
    return result


def parse_summary(text: str, pub_ts=None) -> dict | None:
    """解析「总览」公告（本期活动祈愿时间为…），返回 {start_date, end_date, characters, weapons}。

    总览一次性给出整个祈愿阶段的起止时间与全部 5 星物品，是卡池日期最权威的来源。
    卡池结束于 17:59/14:59（非 03:59），结束日直接抄、不减一天。
    """
    if "本期活动祈愿时间" not in text:
        return None
    result: dict = {}
    dates = re.findall(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if dates:
        y, mo, d = dates[0]
        result["start_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        y, mo, d = dates[-1]
        result["end_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"限定5星角色([^，。]+)", text)
    if m:
        result["characters"] = re.findall(r"[「『]([^」』]+)[」』]", m.group(1))
    m = re.search(r"限定5星武器([^，。]+)", text)
    if m:
        result["weapons"] = re.findall(r"[「『]([^」』]+)[」』]", m.group(1))
    return result


def find_summaries(items: list[dict]) -> list[dict]:
    """从动态里筛出总览公告，返回 parse_summary 结果（含 id）。"""
    out = []
    for d in items:
        r = parse_summary(d["text"], d["pub_ts"])
        if r:
            r["id"] = d["id"]
            out.append(r)
    return out


def merge_banners(entries: list[dict], summaries: list[dict]) -> list[dict]:
    """用 B站总览校验/覆盖推断的卡池日期。

    entries：inference.infer_banner_dates 的输出（含 title/start_date/end_date/phase）
    summaries：find_summaries 的输出（含 start_date/end_date/characters/weapons）
    按 5 星名精确匹配（两边都带属性）。命中总览 → 日期改为总览值（权威）、phase 置「已确认」；
    未命中 → 保留推断日期。
    """
    out = []
    for entry in entries:
        title = entry.get("title", "")
        # 5 星名 = 带「·」的书名号（卡池名「孤灯夜访」等不含「·」）
        stars = [it for it in re.findall(r"[「『]([^」』]+)[」』]", title) if "·" in it]
        sm = None
        for s in summaries:
            pool = s.get("characters", []) + s.get("weapons", [])
            if stars and all(st in pool for st in stars):
                sm = s
                break
        new = dict(entry)
        if sm:
            new["start_date"] = sm["start_date"]
            new["end_date"] = sm["end_date"]
            new["phase"] = "已确认"
            new["source"] = "B站总览"   # 权威来源标记，供 calibrate 打 calibrated
        out.append(new)
    return out


def parse_special_banner_time(text: str) -> dict | None:
    """解析特殊祈愿（溯光/集录）B站动态的「〓祈愿时间〓」段，返回 {name, start_date?, end_date, version_update}。

    特殊祈愿 B站动态不含「本期活动祈愿时间」（那是普通祈愿总览），而是「〓祈愿时间〓」：
    - 上半（实测）：「月之八」版本更新后 ~ 2026/07/21 17:59
        → 无显式 start（version_update=True，start 由版本更新日补）；end 17:59 直接抄、不减一天。
    - 下半（若出现）：X HH:MM ~ Y HH:MM → 显式起止，同样直接抄。
    """
    if "溯光祈愿" not in text and "集录祈愿" not in text:
        return None
    if "〓祈愿时间〓" not in text:
        return None
    m = re.search(r"[「『]([^」』]{2,40})[」』]", text)
    if not m:
        return None
    name = m.group(1).rstrip("！!。：:")
    m = re.search(r"〓祈愿时间〓(.*?)(?=〓|$)", text, re.S)
    if not m:
        return None
    body = m.group(1)
    dates = re.findall(r"(\d{4})/(\d{1,2})/(\d{1,2})", body)
    if not dates:
        return None
    y, mo, d = dates[-1]
    result = {"name": name, "end_date": f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"}
    if "版本更新后" in body:
        result["version_update"] = True
    else:
        y, mo, d = dates[0]
        result["start_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return result


def find_special_banner_dynamics(items: list[dict]) -> list[dict]:
    """从动态里筛出特殊祈愿（溯光/集录）公告，返回 parse_special_banner_time 结果（含 id/pub_ts）。"""
    out = []
    for d in items:
        r = parse_special_banner_time(d["text"])
        if r:
            r["id"] = d["id"]
            r["pub_ts"] = d["pub_ts"]
            out.append(r)
    return out


def merge_special_banners(entries: list[dict], dynamics: list[dict],
                          version_dates: list[str | datetime.date]) -> list[dict]:
    """用 B站特殊祈愿动态覆盖推断的特殊祈愿日期。

    entries：infer_banner_dates 输出的特殊祈愿（title 含溯光/集录）
    dynamics：find_special_banner_dynamics 输出
    按「」内祈愿名匹配。命中后 end 取动态权威值；「版本更新后」的 start 取距动态发布日
    最近的版本更新日（上半锚点），否则取动态显式 start。未命中保留推断日期。
    """
    by_name: dict[str, dict] = {}
    for d in dynamics:
        by_name.setdefault(d["name"], d)
    updates = sorted(datetime.date.fromisoformat(str(v)) for v in version_dates)
    out = []
    for e in entries:
        new = dict(e)
        m = re.search(r"[「『]([^」』]{2,40})[」』]", e.get("title", ""))
        name = m.group(1) if m else ""
        d = by_name.get(name)
        if not d:
            out.append(new)
            continue
        if d.get("end_date"):
            new["end_date"] = d["end_date"]
        if d.get("start_date"):
            new["start_date"] = d["start_date"]
        elif d.get("version_update"):
            pub = None
            try:
                pub = datetime.datetime.fromtimestamp(int(d.get("pub_ts", 0))).date()
            except (TypeError, ValueError, OSError):
                pub = None
            if pub and updates:
                vd = min(updates, key=lambda u: abs((pub - u).days))
                new["start_date"] = vd.isoformat()
        new["phase"] = "已确认"
        new["source"] = "B站祈愿时间"   # 权威来源标记，供 calibrate 打 calibrated
        out.append(new)
    return out


def parse_activity_time(text: str) -> dict | None:
    """解析 B站活动动态的「〓活动时间〓」段，返回 {start_date, end_date, multi_stage}。

    常规活动（单段）: 2026/09/14 04:00 ~ 2026/09/21 03:59
    版本大活动（多阶段）: 第一阶段：… / 第二阶段：… / 结束时间：2026/09/14 03:59
    start = 第一个日期（白天整点，直接抄）；end = 最后一个日期（活动均 03:59 结束，减一天）。
    multi_stage = 段内出现「阶段/结束时间」→ 版本大活动信号（竞锋大赛即分多个阶段）。
    """
    m = re.search(r"〓活动时间〓(.*?)(?=〓|$)", text, re.S)
    if not m:
        return None
    seg = m.group(1)
    dates = re.findall(r"(\d{4})/(\d{1,2})/(\d{1,2})", seg)
    if not dates:
        return None
    y, mo, d = dates[0]
    start = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    y, mo, d = dates[-1]
    end_date = datetime.date(int(y), int(mo), int(d))
    end = (end_date - datetime.timedelta(days=1)).isoformat()
    multi_stage = bool(re.search(r"阶段|结束时间", seg))
    return {"start_date": start, "end_date": end, "multi_stage": multi_stage}


def find_activity_dynamics(items: list[dict]) -> list[dict]:
    """从动态里筛出活动公告，返回 [{name, start_date, end_date, multi_stage, id}]。

    name 为括号内活动名（「七圣召唤」例外用「七圣召唤」作匹配键），
    与 extractor.find_activity_announcements 的 name 对齐。
    """
    out = []
    for d in items:
        r = parse_activity_time(d["text"])
        if not r:
            continue
        text = d["text"]
        if "七圣召唤" in text:
            # 七圣召唤是系统名、多个活动（热斗/铸境研炼）共用，且日期都在米游社正文里，
            # 不靠 B站匹配，否则同名会把别的活动的日期串过来。
            continue
        m = re.search(r"[「『]([^」』]{2,40})[」』]", text)
        if not m:
            continue
        name = m.group(1).rstrip("！!。：:")
        r["name"] = name
        r["id"] = d["id"]
        out.append(r)
    return out


def merge_activities(entries: list[dict], dynamics: list[dict]) -> list[dict]:
    """合并米游社活动与 B站动态：定类型、填日期。

    entries：extractor.find_activity_announcements + parse_activity_body 的输出
             （含 title/name/created_at/post_id/start_date?/end_date?/description?）
    dynamics：find_activity_dynamics 输出（含 name/start_date/end_date/multi_stage）
    类型：默认「常规活动」；B站动态多阶段（阶段/结束时间）→「版本大活动」+「待确认」标签。
    日期：B站动态优先（权威，全阶段起止）；无动态时保留米游社正文推断值。
    """
    by_name: dict[str, dict] = {}
    for d in dynamics:
        if d.get("name"):
            by_name.setdefault(d["name"], d)  # 同名取第一个（最新）
    out = []
    for e in entries:
        d = by_name.get(e.get("name"))
        new = dict(e)
        if d and d.get("multi_stage"):
            new["type"] = "版本大活动"
            tags = new.get("tags") or []
            if "待确认" not in tags:
                tags.append("待确认")
            new["tags"] = tags
        else:
            new["type"] = "常规活动"
        if d and d.get("start_date") and d.get("end_date"):
            new["start_date"] = d["start_date"]
            new["end_date"] = d["end_date"]
            new["source"] = "B站活动动态"   # 权威来源标记，供 calibrate 打 calibrated
        out.append(new)
    return out


def find_livestreams(items: list[dict]) -> list[dict]:
    """从 fetch_dynamics 返回的动态里筛出前瞻预告公告，返回 [{version, name, date, id}]。"""
    out = []
    for d in items:
        r = parse_livestream(d["text"], d["pub_ts"])
        if r:
            r["id"] = d["id"]
            out.append(r)
    return out


if __name__ == "__main__":
    for d in fetch_dynamics(limit=20):
        print(d["pub_ts"], d["type"], "|", d["text"][:80].replace("\n", " "))
