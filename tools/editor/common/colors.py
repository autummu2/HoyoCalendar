"""封面图取色：下载图片 → 取饱和度最高的主色 → 调成浅色 pastel（黑字可读）。

两条管线共用：原神与星铁的常规活动/卡池颜色都不写死，按各自公告的封面图取。
（高难/版本更新/前瞻/大月卡这类没有封面图的，颜色由各管线的 rules 给固定值。）
"""

import colorsys
import io

import requests
from PIL import Image

FALLBACK_COLOR = "#cce0f0"


def pastel_from_url(url: str) -> str:
    """下载封面图，取饱和度最高的主色，调成浅色 pastel。失败返回 FALLBACK_COLOR。"""
    try:
        r = requests.get(url, timeout=15)
        im = Image.open(io.BytesIO(r.content)).convert("RGB").resize((48, 48))
        counts = im.getcolors(48 * 48)  # [(count, (r,g,b))]
        counts.sort(reverse=True)
        best = None
        for _cnt, (r_, g_, b_) in counts:
            mx, mn = max(r_, g_, b_), min(r_, g_, b_)
            if mx - mn >= 25 and mx < 250:  # 跳过灰度 / 近纯白
                best = (r_, g_, b_)
                break
        if best is None:
            best = counts[0][1]
    except Exception:
        return FALLBACK_COLOR
    h, _l, s = colorsys.rgb_to_hls(best[0] / 255, best[1] / 255, best[2] / 255)
    s = min(s, 0.7)
    l = 0.84
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return "#{:02x}{:02x}{:02x}".format(int(r2 * 255), int(g2 * 255), int(b2 * 255))
