"""公告解析引擎 — 纯规则提取，不依赖 LLM。

支持:
- 从米游社 API 获取公告正文
- 从粘贴文本提取活动字段
- 输出结构化 dict 供编辑器表单填充
"""

import datetime
import re
import html as html_mod

import requests

# ─── 游戏 ID 映射 ──────────────────────────────────────

GIDS_MAP = {
    "genshin-impact": 2,
    "honkai-star-rail": 5,
    "zenless-zone-zero": 8,
    "honkai-impact-3rd": 1,
    "tears-of-themis": 4,
}

GAME_KEYWORDS = {
    "genshin-impact": {
        "names": ["原神", "Genshin", "提瓦特", "旅行者"],
        "versions": [r"(\d+\.\d+)"],
        "characters": ["林尼", "夜兰", "钟离", "达达利亚", "公子", "芙宁娜", "那维莱特",
                       "娜维娅", "莱欧斯利", "克洛琳德", "希格雯", "艾梅莉埃", "玛拉妮",
                       "基尼奇", "茜特菈莉", "恰斯卡", "阿蕾奇诺"],
        "regions": ["枫丹", "纳塔", "蒙德", "璃月", "稻妻", "须弥", "至冬"],
    },
    "honkai-star-rail": {
        "names": ["星穹铁道", "Honkai", "开拓者", "星琼"],
        "versions": [r"(\d+\.\d+)"],
        "characters": ["飞霄", "银狼", "刃", "卡芙卡", "景元", "姬子", "黑塔",
                       "流萤", "星期日", "知更鸟", "波提欧", "云璃", "椒丘",
                       "翡翠", "阮梅", "真理医生", "托帕", "镜流", "丹恒"],
        "regions": ["翁法罗斯", "匹诺康尼", "仙舟", "雅利洛", "黑塔空间站"],
    },
    "zenless-zone-zero": {
        "names": ["绝区零", "Zenless", "绳匠", "空洞"],
        "versions": [r"(\d+\.\d+)"],
        "characters": ["月城柳", "莱特", "安比", "比利", "妮可", "猫又",
                       "艾莲", "朱鸢", "青衣", "柏妮思", "凯撒", "简",
                       "星见雅", "苍角", "露西"],
        "regions": ["新艾利都"],
    },
}

# ─── 活动类型关键词 ────────────────────────────────────

TYPE_KEYWORDS = [
    ("banner", ["卡池", "祈愿", "UP", "概率UP", "角色活动", "光锥活动", "音擎活动"]),
    ("challenge", ["深境螺旋", "深渊", "混沌回忆", "忘却之庭", "式舆防卫战",
                   "挑战", "高难", "试炼", "模拟宇宙"]),
    ("version-main", ["版本", "主题活动", "版本活动", "庆典"]),
    ("daily", ["签到", "登录", "每日", "七日", "累计"]),
    ("web-event", ["网页活动", "联动", "必胜客", "KFC", "线下"]),
    ("festival", ["海灯节", "周年", "周年庆", "圣诞", "新年", "春节"]),
    ("reward", ["兑换码", "福利", "补偿", "原石", "星琼", "母带"]),
    ("update", ["更新", "维护", "停服", "上线"]),
]

# ─── 日期正则 ────────────────────────────────────────────

DATE_PATTERNS = [
    (re.compile(r"(\d{4})\s*[/年\-]\s*(\d{1,2})\s*[/月\-]\s*(\d{1,2})\s*日?"),  # 2026/08/16, 2026年8月16日
     lambda m: f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"),
    (re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日"),  # 8月16日 (需补年份)
     None),  # 需要上下文当前年份
]


# ─── 公共函数 ────────────────────────────────────────────

def html_to_text(html: str) -> str:
    """去除 HTML 标签，返回纯文本"""
    # 移除标签
    text = re.sub(r"<[^>]+>", " ", html)
    # 解码 HTML 实体
    text = html_mod.unescape(text)
    # 压缩空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_post(post_id: int | str, game_id: str = "genshin-impact") -> dict | None:
    """从米游社 API 获取公告全文"""
    gids = GIDS_MAP.get(game_id, 2)
    url = "https://bbs-api.miyoushe.com/post/wapi/getPostFull"
    params = {"gids": str(gids), "post_id": str(post_id), "read": "1"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/99.0.4844.84 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.miyoushe.com/",
        "x-rpc-client_type": "4",
        "x-rpc-app_version": "2.102.0",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()
        if data.get("retcode") != 0:
            return None
        post = data["data"]["post"]["post"]
        content = post.get("content", "") or ""
        return {
            "subject": post.get("subject", ""),
            "content": content,
            "text": html_to_text(content),
            "post_id": str(post.get("post_id", post_id)),
            "created_at": post.get("created_at", 0),
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_post_list(game_id: str = "genshin-impact", page_size: int = 10) -> list[dict]:
    """获取公告列表"""
    gids = GIDS_MAP.get(game_id, 2)
    url = "https://bbs-api-static.miyoushe.com/painter/wapi/getNewsList"
    params = {"client_type": "4", "gids": str(gids), "page_size": str(page_size), "type": "1"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/99.0.4844.84 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.miyoushe.com/",
        "x-rpc-client_type": "4",
        "x-rpc-app_version": "2.102.0",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()
        if data.get("retcode") != 0:
            return []
        posts = []
        for item in data["data"]["list"]:
            post = item["post"]
            posts.append({
                "post_id": str(post.get("post_id", "")),
                "subject": post.get("subject", ""),
                "created_at": post.get("created_at", 0),
            })
        return posts
    except Exception:
        return []


# ─── 提取引擎 ────────────────────────────────────────────

def extract(text: str, game_id: str = "genshin-impact") -> dict:
    """从公告纯文本中提取活动字段

    返回 dict: {title, type, start_date, end_date, description, tags, confidence}
    """
    result: dict = {}
    game_kw = GAME_KEYWORDS.get(game_id, {})

    # ── 1. 标题: 「...」 书名号 ──
    titles = re.findall(r"[「『]([^」』]{4,60})[」』]", text)
    if titles:
        # 取最长的（通常是主标题）
        titles.sort(key=len, reverse=True)
        result["title"] = titles[0]
    else:
        # 退而求其次: 取第一句包含"版本"或"活动"的句子
        for sent in re.split(r"[。！\n]", text):
            if any(kw in sent for kw in ["版本", "活动", "开启", "上线"]):
                result["title"] = sent.strip()[:60]
                break

    # ── 2. 日期 ──
    dates = []
    # 完整日期: 2026/08/16, 2026年8月16日, 2026-08-16
    for m in re.finditer(r"(\d{4})\s*[/年\-]\s*(\d{1,2})\s*[/月\-]\s*(\d{1,2})\s*日?", text):
        dates.append(f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}")

    # 缩略日期: 08/16, 8月16日 (补当前年份)
    year = datetime.date.today().year
    for m in re.finditer(r"(?:^|[^\d])(\d{1,2})\s*[/月]\s*(\d{1,2})\s*日?(?:[^\d]|$)", text):
        month, day = int(m[1]), int(m[2])
        if 1 <= month <= 12 and 1 <= day <= 31:
            dates.append(f"{year}-{month:02d}-{day:02d}")

    dates = sorted(set(dates))
    if dates:
        result["start_date"] = dates[0]
        if len(dates) >= 2:
            result["end_date"] = dates[-1]

    # ── 3. 活动类型 ──
    text_lower = text.lower()
    type_scores: dict[str, int] = {}
    for type_id, keywords in TYPE_KEYWORDS:
        score = sum(1 for kw in keywords if kw.lower() in text_lower or kw in text)
        if score > 0:
            type_scores[type_id] = score
    if type_scores:
        result["type"] = max(type_scores, key=lambda k: type_scores[k])

    # ── 4. 描述 ──
    # 取标题后的连续文本（或第一段较长的文本）
    paras = [p.strip() for p in re.split(r"[\n。]", text) if len(p.strip()) > 10]
    if paras:
        # 跳过纯数字/时间/格式文本
        for p in paras:
            if not re.match(r"^[\d\s/：:·\-–—、，]+$", p) and len(p) > 8:
                result["description"] = p[:200]
                break

    # ── 5. 标签 ──
    tags: list[str] = []
    if "version" in result:
        m = re.search(r"(\d+\.\d+)", text)
        if m:
            tags.append(f"v{m[1]}")
    # 版本阶段
    for kw in ["上半", "下半", "第一期", "第二期"]:
        if kw in text:
            tags.append(kw)
    # 角色名
    for name in game_kw.get("characters", []):
        if name in text and name not in tags:
            tags.append(name)
    # 地区
    for region in game_kw.get("regions", []):
        if region in text and region not in tags:
            tags.append(region)
    if tags:
        result["tags"] = tags[:8]

    return result
