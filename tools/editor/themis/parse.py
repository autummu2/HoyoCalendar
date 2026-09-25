"""未定事件簿的公告解析：从列表 + 正文纯规则地判出「类型 / 标题 / 时段」。

不进网络、不写文件，所有函数都是纯函数（pipeline.py 负责抓取与落盘，
selftest.py 拿 fixtures/ 里的真实公告断言这里的每一条规则）。判据出处见 RULES.md §2。

未定与另三端最不一样的一点：**信息以「一篇帖子」为单位，不是一个活动一份公告**。
所以这里没有「总纲」也没有分组机制——每篇帖子自己判、自己解日期，
解不出来就丢（`classify` 返回 None 或 `parse_period` 返回空），等下一篇带完整时段的。
"""
from __future__ import annotations

import datetime
import re

from themis import rules

# 时段：`2026年9月15日11:00-9月20日04:00`。
# 起点时刻**可以缺席**（写成 `…8月20日更新后-8月27日04:00`）或写成 `更新后` 这类
# 相对措辞——后者指的就是这一天的开服时刻，日期部分照抄即可（实测 95 篇里唯一的
# 相对写法就是它，见 rules.DAY_BOUNDARY_END 的注）。
# 终点年份也可以缺席（同期省略年份），跨年时按月序补。
#
# 分隔符只认 `-` `–` `—`（半角连字符 / 短破折号 / 全角破折号），**故意不认 `至`**：
# 95 篇实测里 `至` 的三次命中全是假阳性（「将于 1月6日10:30 左右进行更新」、
# 「拖动拼图碎片摆放至正确的位置」），没有一次是真的 `A日至B日` 时段。
PERIOD_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(?:(\d{1,2}):(\d{2})|更新后)?"
    r"\s*[-–—]\s*"
    r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:(\d{1,2}):(\d{2}))?"
)


def split_subject(subject: str) -> tuple[str, str]:
    """`主题丨子标题` → (主题, 子标题)。

    未定的资讯栏标题一律是这个形状（半角 `丨`，U+4E28）。⚠️ 主题是**所有**帖子的
    命名法（`插画分享` / `商城上新` 也长这样），所以它只用来判「是不是往期复刻」
    与兜底取标题，**不是**分类枢纽（RULES §2.1）。
    没有 `丨` 的（公告栏的整句式标题）子标题返回空串。
    """
    parts = (subject or "").split("丨", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def find_news(posts: list[dict]) -> list[dict]:
    """第一道闸：标题命中负向名单的直接丢，**不取正文**（RULES §2.2）。

    只看标题就能判掉 19/50 篇，省掉 19 次正文请求。
    """
    out = []
    for p in posts:
        s = p.get("subject") or ""
        if any(kw in s for kw in rules.TITLE_SKIP_KEYWORDS):
            continue
        out.append(p)
    return out


def big_event_label(text: str) -> str | None:
    """正文里的官方复合标签 → 活动名；没有返回 None（RULES §2.4-4）。"""
    m = rules.BIG_EVENT_LABEL.search(text or "")
    return m.group(1) if m else None


def classify(subject: str, text: str) -> str | None:
    """一篇帖子属于哪一类；返回 None = 丢弃（不上日历）。

    顺序即 RULES §2.2 的决策树：第三关（复刻二分）→ 第四关（版本大活动标签）→ 归类。

    ⚠️ **「思绪帖」不在判据里**：`…全新◯◯SSR思绪【◯◯】` 这类新卡展示帖按旧稿要单独
    挡一次，但实测它们**正文里都没有完整时段**（`9月30日更新后` 这类相对写法解不出
    终点），第二道闸已经全部拦下；而带完整时段的思绪帖（`轮替女神之影丨莫弈SSR
    【莫负良辰】限时返场`）本来就该是卡池，单独挡反而会漏。所以判据只留一条：
    **有完整时段才进候选**（在 pipeline.collect 里）。
    """
    topic, sub = split_subject(subject)

    # 第三关：往期复刻要二分 —— 女神之影是卡池，活动系列/礼包/商城上架不上日历
    if topic == rules.REPRINT_TOPIC:
        # 卡池信号：标题里有（`轮替女神之影更新丨…`）、或只在正文里有
        # （`往期复刻丨莫弈生日系列限时复刻` 正文通篇女神之影）。实测另 3 篇复刻帖正文 0 命中。
        if rules.BANNER_KEYWORD in subject or rules.BANNER_KEYWORD in (text or ""):
            return "卡池"
        if any(kw in sub for kw in rules.REPRINT_DROP_KEYWORDS):
            return None
        return "常规活动"

    # 第四关：官方复合标签（大型〈季节〉/〈◯◯〉主题/〈◯◯〉联动 ×活动「活动名」）
    if big_event_label(text):
        return "版本大活动"

    # 判据取**整条标题**而不是子标题：轮替返场的卡池信号在主题里
    # （`轮替女神之影更新丨夏彦SSR【夏花永隽】限时返场`，子标题只有角色名）。
    # 实测资讯栏 50 篇里 `女神之影` 出现在标题上的共 4 篇，**全是卡池**、零假阳性；
    # 另有一条「返场」但整体不含「女神之影」的 —— 没有，所以不再单列 `限时返场`。
    if rules.BANNER_KEYWORD in subject:
        return "卡池"
    if rules.BATTLE_PASS_KEYWORD in sub or topic == rules.BATTLE_PASS_KEYWORD:
        return "大月卡"
    if rules.LOGIN_KEYWORD in sub:
        return "登录福利"
    # 节日福利的判据是「主题以『快乐』结尾 + 正文说登录领邮件」，不是节日名单：
    #   `中秋快乐丨佳节长相伴` / `教师节快乐丨春风化雨，桃李芬芳` 都落在这里。
    if topic.endswith(rules.FESTIVAL_SUFFIX) \
            and any(m in (text or "") for m in rules.LOGIN_BODY_MARKERS):
        return "登录福利"
    return "常规活动"


def title_of(subject: str, text: str, etype: str) -> str:
    """取条目标题（RULES §4.2）。

    🔒 取「活动名」而不是整条 `主题丨子标题`：`丨` 前缀是**栏目名**
    （`往期复刻` / `轮替女神之影` / `商城上新` 都会撞名），拿它当标题会撞。

      - 复刻帖：子标题原样（`「濯影拾辉」活动限时复刻`）——子标题本身就以「活动名」开头
      - 卡池：`角色+稀有度+【思绪名】`（`夏彦SSR【换日线】`），子标题里找不到就退回子标题
        （复刻卡池的子标题是整句 `「NXX-冰原上的审判」活动女神之影限时复刻`，本身就是活动名。
        ⚠️ 不去正文里找：正文里冒出的是**别的**卡池的思绪名，取到就成张冠李戴）
      - 其余：子标题里第一个 `「…」`（`「青葱寄愿」限时活动开启` → `「青葱寄愿」`），
        取不到时退回主题（`爱的未定式·夏彦篇丨限时活动预告` → `「爱的未定式·夏彦篇」`），
        并补上 `rules.TITLE_SUFFIX_WORDS` 里命中的区分后缀（`…生日拼图`）
    """
    topic, sub = split_subject(subject)
    if topic == rules.REPRINT_TOPIC:
        return sub or topic
    if etype == "卡池":
        m = rules.CARD_TITLE_RE.search(sub)
        return m.group(0) if m else (sub or topic)
    m = re.search(r"「([^」]{2,40})」", sub)
    if m:
        return f"「{m.group(1)}」"
    # 后缀只在这一支加：标题是从主题抄来的，正说明子标题里没有「活动名」可抄 ——
    # 缺什么补什么。卡池与复刻帖的标题本来就抄自子标题，再补会重复。
    suffix = next((w for w in rules.TITLE_SUFFIX_WORDS if w in sub), "")
    return f"「{topic}」{suffix}"


def detect_tags(subject: str, text: str) -> list[str]:
    """认标签：男主名 → 稀有度 → 联动（RULES §4.4）。

    未定手工数据里 tags 只有这三样（19 条里 15 条有），三样都是游戏自己的固定词表，
    不是会过期的活动名单，所以**不用维护任何标签名单**（原神那种 `限时剧情奖励` 未定没有）。

    顺序按手工数据的惯例：四人按官方顺序（夏彦→左然→莫弈→陆景和），稀有度在后
    —— 与最新三条手工条目（陆景和SSS / 夏彦SSR / 莫弈SSR）一致。命中不到的词不给标签。

    **标题命中就不看正文**：标题是「这篇指向谁」（`夏彦SSR【夏花永隽】`），正文是上下文
    —— 轮替返场帖的正文会把整个轮替池的角色都列一遍，只看正文会把两条轮替帖打成四人全中。
    标题一个标签都认不出时才退到正文：复刻帖的标题只有活动名（`「濯影拾辉」活动限时复刻`
    → 左然 MR 只在正文里），七夕/多人活动也只有正文才有名字。

    判据是「整条标题有命中就整条不看正文」而不是「按名字/稀有度分别兜底」：手工数据里
    `「爱的未定式·夏彦篇」` 的正文写着 SSR（description 就是「邀请函、SSR、限时活动」）
    而 tags 只有 `夏彦` —— 分别兜底会多打一个 SSR。反过来，标题没提谁时正文就该全信：
    `「NXX-冰原上的审判」活动女神之影限时复刻` 的 SSR 与四个人名都只有正文有，手工也正是这么记的。
    """
    tags = _tags_in(subject or "")
    return tags or _tags_in(f"{subject or ''}\n{text or ''}")


def _tags_in(hay: str) -> list[str]:
    tags = [h for h in rules.HEROES if h in hay]
    # lookaround 卡边界：`SR` 不能命中 `SSR` 里面的两个字
    tags += [r for r in rules.RARITIES if re.search(rf"(?<![A-Z]){r}(?![A-Z])", hay)]
    if rules.COLLAB_KEYWORD in hay:
        tags.append(rules.COLLAB_KEYWORD)
    return tags


def parse_period(text: str) -> tuple[str | None, str | None]:
    """正文里的**第一段**完整时段 → (start, end)（ISO 日期），解不出返回 (None, None)。

    「取第一段」是裁定：复刻帖常见两段（活动本体一段、兑换所一段），实测两段日期
    相同；不同时以第一段为准（RULES §4.1）。日期解不出来就没有可落日历的值 ——
    这是第二道闸的判据本身。

    日边界：终点 `04:00` 是未定的游戏日边界 → **终点日减一天**，起点日不减
    （原神把同一个边界写成 `03:59`，两边口径同源）。
    """
    m = PERIOD_RE.search(text or "")
    if not m:
        return None, None
    sy, sm, sd, _sh, _smin, ey, em, ed, eh, emin = m.groups()
    start_year, end_year = int(sy), int(ey) if ey else int(sy)
    if end_year == start_year and int(em) < int(sm):
        end_year += 1        # 终点省略年份且月份回绕 → 跨年
    start = datetime.date(start_year, int(sm), int(sd))
    end = datetime.date(end_year, int(em), int(ed))
    if eh and f"{int(eh):02d}:{emin}" == rules.DAY_BOUNDARY_END:
        end -= datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def parse_version_notes(posts: list[dict]) -> list[dict]:
    """公告栏里的停服更新公告 → [{version, date, subject, post_id}]。

    `5.6版本更新丨2月10日08:00停服更新公告`：版本号与开服日**都在标题里**，
    不取正文（RULES §2.4-1）。标题没有年份，年份取自公告的发布日；跨年（12 月发
    1 月的公告）按月份回绕补一年。
    """
    out = []
    for p in posts:
        m = re.match(rules.VERSION_NOTES_PATTERN, p.get("subject") or "")
        if not m:
            continue
        major, minor, month, day = (int(g) for g in m.groups())
        try:
            created = datetime.datetime.fromtimestamp(int(p.get("created_at") or 0))
        except (TypeError, ValueError, OSError):
            created = None
        year = created.year if created else datetime.date.today().year
        if created and month < created.month:
            year += 1        # 12 月发的公告里写「1月X日」→ 是明年
        out.append({
            "version": f"{major}.{minor}",
            "date": datetime.date(year, month, day).isoformat(),
            "subject": p.get("subject"),
            "post_id": p.get("post_id"),
        })
    return out
