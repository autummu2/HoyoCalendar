"""公告解析引擎 — 纯规则提取，不依赖 LLM。

支持:
- 从米游社 API 获取公告正文
- 从粘贴文本提取活动字段
- 输出结构化 dict 供编辑器表单填充
"""

import datetime
import json
import os
import re
import html as html_mod

import requests

# ─── 游戏 ID 映射 ──────────────────────────────────────

GIDS_MAP = {
    "genshin-impact": 2,
    "honkai-star-rail": 6,
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
    ("卡池", ["卡池", "祈愿", "UP", "概率UP", "角色活动", "光锥活动", "音擎活动"]),
    ("常规活动", ["活动", "奖励", "参与", "签到", "登录", "每日", "七日", "累计", "兑换码", "福利"]),
    ("版本大活动", ["版本活动", "主题活动", "庆典", "海灯节", "周年", "大版本"]),
    ("版本更新", ["更新", "维护", "停服", "上线", "版本更新"]),
    ("网页活动", ["网页活动", "联动", "必胜客", "KFC", "线下", "网页"]),
    ("高难挑战", ["深境螺旋", "深渊", "混沌回忆", "忘却之庭", "式舆防卫战",
                  "高难", "试炼", "挑战", "模拟宇宙", "危战", "危途"]),
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
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_post_text(content: str, post: dict) -> str:
    """从帖子内容中提取纯文本（兼容不同游戏的内容格式）

    原神: HTML <div>...<p>text</p>...</div>
    ZZZ/HSR: JSON {"describe":"text", "imgs":[...]}
    通版: structured_content [{"insert":"text"},...]
    """
    # 1. 尝试 JSON 格式 (ZZZ/HSR)
    if content.startswith("{") and '"describe"' in content:
        try:
            obj = json.loads(content)
            describe = obj.get("describe", "")
            if describe:
                return describe.strip()
        except json.JSONDecodeError:
            pass

    # 2. 尝试 structured_content 字段
    sc = post.get("structured_content", "")
    if sc:
        try:
            if isinstance(sc, str):
                sc = json.loads(sc)
            if isinstance(sc, list):
                parts = [item.get("insert", "") for item in sc if isinstance(item, dict)]
                text = "".join(parts).strip()
                if text:
                    return text
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. HTML 格式 (原神)
    if "<" in content:
        text = html_to_text(content)
        if text:
            return text

    # 4. 纯文本 / 兜底
    return html_to_text(content) if "<" in content else content.strip()


def _cookie_header() -> str:
    """米游社登录 cookie（可选，见 fetch_post 注释）。

    在调用时读取而非导入时，避免依赖 import 顺序（管线会先从注册表预读进 os.environ）。
    """
    return os.environ.get("MIYOUSHE_COOKIE", "")


def fetch_post(post_id: int | str, game_id: str = "genshin-impact") -> dict | None:
    """从米游社 API 获取公告全文

    未登录的请求会被风控拦截（`retcode 1034`，`message` 为空），连续多次运行尤其容易触发。
    登录态可提高信任等级、降低触发概率。浏览器登录米游社后，从开发者工具复制 cookie，
    设为环境变量（cookie 本身不要写进仓库）：
      setx MIYOUSHE_COOKIE "ltoken_v2=…; ltuid_v2=…; cookie_token_v2=…; account_id=…"
    """
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
    cookie = _cookie_header()
    if cookie:
        headers["Cookie"] = cookie
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()
        if data.get("retcode") != 0:
            # 带上 retcode：风控（1034）的 message 是空的，只报 message 事后无法分辨原因
            return {"error": f"API 返回错误: retcode={data.get('retcode')} {data.get('message', '')}".strip()}
        # 数据结构: data → post → post
        outer = data.get("data", {})
        if not isinstance(outer, dict):
            return {"error": "data 字段不是对象"}
        middle = outer.get("post", {})
        if not isinstance(middle, dict):
            return {"error": "data.post 字段不是对象"}
        post = middle.get("post", middle) if "post" in middle else middle
        if not isinstance(post, dict):
            return {"error": "未找到 post 数据"}
        content = post.get("content", "") or ""
        subject = post.get("subject", "") or ""

        # 提取正文文本（不同游戏格式不同）
        text = _extract_post_text(content, post)

        # 如果标题为空，尝试从正文提取
        if not subject and text:
            # 取正文第一句作为标题
            first_sent = text.split("。")[0].strip()
            if len(first_sent) > 4:
                subject = first_sent[:60]

        return {
            "subject": subject,
            "content": content,
            "text": text,
            "images": post.get("images", []) or [],
            "post_id": str(post.get("post_id", post_id)),
            "created_at": post.get("created_at", 0),
        }
    except requests.RequestException as e:
        return {"error": f"网络错误: {e}"}
    except Exception as e:
        return {"error": str(e)}


def find_banner_announcements(posts: list[dict]) -> list[dict]:
    """从米游社公告列表筛出卡池公告，返回 [{title, created_at, post_id}]。

    卡池标题形如「冰绡鹄影」祈愿：「翾风回雪·奥黛塔(冰)」概率UP！，
    完整包含卡池名与 5 星全名（带属性），去尾部感叹号后直接作为标题。
    created_at 用于按版本节奏推断卡池阶段（上半/下半，见 inference.infer_banner_dates）。
    排除溯光祈愿 / 集录祈愿等特殊祈愿。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if "祈愿" in s and "概率" in s and "溯光祈愿" not in s and "集录祈愿" not in s:
            out.append({
                "title": s.rstrip("！!。"),
                "created_at": p.get("created_at", 0),
                "post_id": p.get("post_id", ""),
            })
    return out


# ─── 活动公告（常规活动 / 版本大活动） ───────────────────────

# 负向关键词：命中即非「常规/版本大」活动（版本更新/维护、反馈、优化、
# 赛季、装扮上新、礼包、首充等，见 genshin/RULES.md 第五节）
ACTIVITY_SKIP_KEYWORDS = [
    "首充双倍", "集中反馈", "优化说明", "版本更新", "维护预告", "更新说明",
    "版本说明", "赛季开启", "装扮上新", "冒险助力礼包", "设备性能",
    "云·原神", "游戏问题", "更新修复", "更新维护",
    "纪行",  # 大月卡（纪行），非常规活动，另由 find_battle_pass_announcements 单独提取
    # 世界任务说明：正文用「〓任务开放时间〓」，parse_activity_body 不识别该段，
    # 提取后无日期会污染下游。本就不记录此类条目，直接跳过。
    "世界任务说明",
]

# 高难挑战有独立类型（深境螺旋 / 幻想真境剧诗 / 幽境危战 等），不归入常规活动
CHALLENGE_KEYWORDS = ["危战", "深境螺旋", "深渊", "幻想真境剧诗", "混沌回忆", "忘却之庭"]


def find_activity_announcements(posts: list[dict]) -> list[dict]:
    """从米游社公告列表筛出活动公告（常规/版本大），返回 [{title, name, created_at, post_id, tags?}]。

    排除卡池、版本更新/维护、首充双倍、集中反馈、优化说明、赛季、装扮上新、
    礼包、纪行（大月卡）、高难挑战等。title 为最终标题（取「」括号内活动名；
    「七圣召唤」例外保留完整标题）；name 为括号内活动名，用于与 B站动态匹配。
    限时剧情/探索奖励（「时限内完成魔神任务/探索任务」）打对应 tag。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if "概率" in s or "溯光祈愿" in s or "集录祈愿" in s:
            # 卡池/祈愿：常规祈愿标题含「概率UP」，特殊祈愿含「溯光祈愿/集录祈愿」。
            # 不可用宽泛的 "祈愿" in s——会误杀标题里恰好带「祈愿」二字的常规活动公告。
            continue
        if any(kw in s for kw in ACTIVITY_SKIP_KEYWORDS):
            continue
        if any(kw in s for kw in CHALLENGE_KEYWORDS):
            continue
        if "七圣召唤" in s:
            # 例外：括号内是系统名，保留完整标题（genshin/RULES.md 第二节）
            title = s.rstrip("！!。：:")
            name = "七圣召唤"
        else:
            m = re.search(r"[「『]([^」』]{2,40})[」』]", s)
            if not m:
                continue
            name = m.group(1).rstrip("！!。：:")
            title = f"「{name}」"
        entry = {
            "title": title,
            "name": name,
            "created_at": p.get("created_at", 0),
            "post_id": p.get("post_id", ""),
        }
        if "时限内" in s:
            if "魔神任务" in s:
                entry["tags"] = ["限时剧情奖励"]
            elif "探索任务" in s:
                entry["tags"] = ["限时探索奖励"]
        out.append(entry)
    return out


def find_challenge_announcements(posts: list[dict]) -> list[dict]:
    """检测幽境危战公告 → 高难挑战（每版本都有、名字不变，单独处理）。

    幽境危战有独立公告（标题「幽境危战」活动：X），不参与常规/版本大活动提取
    （find_activity_announcements 已按 CHALLENGE_KEYWORDS 排除），也不靠推理——
    有公告就有准确日期，故单独识别后抓正文即可。深境螺旋/幻想真境剧诗无公告，不在此列。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if "幽境危战" not in s:
            continue
        m = re.search(r"[「『]([^」』]{2,40})[」』]", s)
        name = m.group(1).rstrip("！!。：:") if m else "幽境危战"
        out.append({
            "title": f"「{name}」",
            "type": "高难挑战",
            "name": name,
            "created_at": p.get("created_at", 0),
            "post_id": p.get("post_id", ""),
        })
    return out


def find_maintenance_posts(posts: list[dict]) -> list[dict]:
    """筛出「X.Y版本更新维护预告」公告，返回 [{post_id, subject, version}]。

    该公告发布于版本更新前约 2 天，正文同时给出**更新日期 + 版本号 + 版本名**，
    是「版本更新」条目最权威的校准来源（比 B站前瞻公告更晚、更准）。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if "版本更新维护预告" not in s:
            continue
        m = re.search(r"(\d+)\.(\d+)\s*版本", s)
        out.append({
            "post_id": p.get("post_id", ""),
            "subject": s,
            "version": f"{m.group(1)}.{m.group(2)}" if m else None,
        })
    return out


def parse_maintenance_body(text: str) -> dict | None:
    """解析维护预告正文 → {date, name?}（name 为版本名）。

    正文形如：「制作组预计将于2026/09/23 06:00进行版本更新维护，维护完成后，
    游戏将更新为全新7.1版本——「往冥府的安魂歌」。」
    日期优先取「〓更新维护信息〓」段内的首个「YYYY/MM/DD HH:MM」，否则取首个
    后接「版本更新维护」的日期——正文后面还有补偿范围、更新说明等同类日期，
    不能盲取第一个。
    """
    m = re.search(r"〓更新维护信息〓(.*?)(?=〓|$)", text, re.S)
    seg = m.group(1) if m else text
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})\s+\d{1,2}:\d{2}", seg)
    if not m and seg is text:
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})\s+\d{1,2}:\d{2}[^。]{0,12}版本更新维护", text)
    if not m:
        return None
    y, mo, d = m.groups()
    result = {"date": f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"}
    m = re.search(r"版本——[「『]([^」』]{2,40})[」』]", text)
    if m:
        result["name"] = m.group(1)
    return result


def find_battle_pass_announcements(posts: list[dict]) -> list[dict]:
    """检测纪行（大月卡）公告 → 大月卡。特征「XX纪行」（如霜游纪行）。

    纪行是每版本的大月卡，标题「XX纪行」，日期在正文（「版本更新后 ~ Y」），
    不参与常规活动提取（find_activity_announcements 已按 ACTIVITY_SKIP_KEYWORDS 排除），
    由 genshin/pipeline.py 单独抓正文后经 resolve_version_starts 补 start。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if "纪行" not in s:
            continue
        m = re.search(r"[「『]([^」』]{2,40})[」』]", s)
        name = m.group(1).rstrip("！!。：:") if m else "纪行"
        out.append({
            "title": f"「{name}」",
            "type": "大月卡",
            "name": name,
            "created_at": p.get("created_at", 0),
            "post_id": p.get("post_id", ""),
        })
    return out


def find_special_banner_announcements(posts: list[dict]) -> list[dict]:
    """检测特殊祈愿公告 → 卡池。关键词：溯光祈愿 / 集录祈愿。

    特殊祈愿角色池大，标题不写具体角色、只写祈愿名（去尾部感叹号），
    如「辉天的星告」祈愿：溯光祈愿开启。日期与普通祈愿一样：
    米游社取标题 → infer_banner_dates 推断 + B站总览补充。
    """
    out = []
    for p in posts:
        s = p.get("subject", "")
        if "溯光祈愿" not in s and "集录祈愿" not in s:
            continue
        out.append({
            "title": s.rstrip("！!。"),
            "type": "卡池",
            "created_at": p.get("created_at", 0),
            "post_id": p.get("post_id", ""),
        })
    return out


def _parse_time_segment(seg: str) -> tuple[str | None, str | None]:
    """从时间段文本提取 (start, end)，返回 ISO 日期或 None。

    - 整体结束取第 2 个日期（避开「任务完成时间」等子区间）。
    - end 时间若为 03:59（游戏日边界）减一天；其余（14:59/17:59/5:59）直接抄。
    """
    pairs = re.findall(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*(\d{1,2}):(\d{2})", seg)
    if not pairs:
        return None, None
    if len(pairs) >= 2:
        start = f"{int(pairs[0][0]):04d}-{int(pairs[0][1]):02d}-{int(pairs[0][2]):02d}"
        y, mo, d, hh, mm = pairs[1]
    else:
        start = None  # 单日期 = 「版本更新后 ~ Y」，start 待版本更新日补
        y, mo, d, hh, mm = pairs[0]
    end_date = datetime.date(int(y), int(mo), int(d))
    if f"{int(hh):02d}:{mm}" == "03:59":
        end_date -= datetime.timedelta(days=1)
    return start, end_date.isoformat()


def parse_activity_body(text: str) -> dict:
    """解析米游社活动正文，返回 {description, start_date?, end_date?, permanent?, version_period?}。

    时间来源：优先「〓活动时间〓」，其次「〓获取奖励时限〓」（限时剧情/探索奖励）。
    特殊标记：
    - permanent=True：「永久开放」，不进日历。
    - version_period=True：「版本期间持续开放」，起止 = 整版本周期（inference.resolve_version_period 补）。
    - 日期三况见 genshin/RULES.md；end 03:59 减一天、其余时间直接抄。
    """
    result = {"description": text.strip() or None}
    m = re.search(r"〓活动时间〓(.*?)(?=〓|$)", text, re.S)
    if not m:
        m = re.search(r"〓获取奖励时限〓(.*?)(?=〓|$)", text, re.S)
    if not m:
        return result
    seg = m.group(1)
    if "永久开放" in seg:
        result["permanent"] = True
        return result
    if "版本期间" in seg:
        result["version_period"] = True
        return result
    start, end = _parse_time_segment(seg)
    if start:
        result["start_date"] = start
    if end:
        result["end_date"] = end
    return result


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

    # ── 1. 标题: 「...」 书名号（取第一个出现的位置） ──
    titles = [(m.start(), m[1]) for m in re.finditer(r"[「『]([^」』]{4,60})[」』]", text)]
    if titles:
        # 优先取前 3 个中出现版本号或活动关键词的
        picked = None
        for _, t in titles[:3]:
            if any(kw in t for kw in ["版本", "活动", "开启", "上线", "更新"]):
                picked = t
                break
        result["title"] = picked or titles[0][1]
    else:
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
