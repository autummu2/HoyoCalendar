"""可选凭据：环境变量优先，Windows 上再从 HKCU\\Environment 补。

本机用 setx 写的是注册表（见记忆 bili-sessdata-registry），GitHub Actions 上
则只有环境变量（当前不配 Secrets，两个都为空也能跑）。调用方必须在本模块之后、
import bilibili / extractor 之前调用 load_env()：`bilibili.SESSDATA` 在模块导入时
读环境变量。
"""
import os

_NAMES = ("BILI_SESSDATA", "MIYOUSHE_COOKIE")


def load_env() -> None:
    """把注册表里的凭据补进 os.environ；非 Windows 或读取失败时静默跳过。"""
    if os.name != "nt":
        return
    import winreg  # 只在 Windows 分支导入，Linux 不会执行到

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    except OSError:
        return
    try:
        for name in _NAMES:
            if os.environ.get(name):
                continue  # 显式环境变量优先
            try:
                os.environ[name] = winreg.QueryValueEx(key, name)[0]
            except OSError:
                pass
    finally:
        winreg.CloseKey(key)
