"""无人值守推送：提交 data/events 的变更 → develop，快进 main。

供 Windows 计划任务在 maintain.py 之后调用（见 maintain_and_push.bat）。规则与
gui.py 的「一键推送」一致：只在 develop 上执行、只提交 data/events、其它改动则拒绝。
"""
import datetime
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=check)


def main() -> int:
    # 计划任务不一定继承 ssh-agent，显式指定未加密的默认密钥
    key = Path(os.environ.get("USERPROFILE", "")) / ".ssh" / "id_rsa"
    if key.exists() and "GIT_SSH_COMMAND" not in os.environ:
        os.environ["GIT_SSH_COMMAND"] = (
            f'ssh -i "{key}" -o IdentitiesOnly=yes -o BatchMode=yes')

    branch = git("branch", "--show-current").stdout.strip()
    if branch != "develop":
        print(f"当前在 {branch} 分支，自动推送只在 develop 上执行")
        return 1

    lines = [l for l in git("status", "--porcelain").stdout.splitlines() if l.strip()]
    data_changed = [l for l in lines if "data/events/" in l]
    other = [l for l in lines if "data/events/" not in l]
    if other:
        print("工作区有非数据文件改动，停止推送：")
        for line in other:
            print(" ", line)
        return 1

    git("pull", "--ff-only", "origin", "develop")
    if data_changed:
        git("add", "data/events/")
        git("commit", "-m", f"data: 自动维护 {datetime.date.today():%Y-%m-%d}")

    # 本地可能有上次推送失败留下的提交，先推完再判断「无变更」
    ahead = int(git("rev-list", "--count", "origin/develop..develop").stdout.strip() or 0)
    if not ahead:
        print("数据无变更，无需推送")
        return 0
    git("push", "origin", "develop")

    git("fetch", "origin", "main")
    git("checkout", "main")
    try:
        git("pull", "--ff-only", "origin", "main")
        git("merge", "--ff-only", "develop")
        git("push", "origin", "main")
    finally:
        git("checkout", "develop", check=False)
    print("已推送 develop 并快进 main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
