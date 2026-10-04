# -*- coding: utf-8 -*-
"""撞车重试判据的变异电池：每条判据都必须被一个对应的坏改动挡住，否则它是空转。

做法与 mut_attention.py 同：真实文件一个字节不动，把 star-fast.yml 复制进临时目录打变异，
用 STAR_FAST_YML 注入点让判据读副本。每轮重打（变异绝不互相掩盖），
并要求"整体红 + 靶判据自己红"两个条件同时成立——只红别的判据算钉错了地方。

用法：py -3.11 tools/mut_push_retry.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YML = os.path.join(".github", "workflows", "star-fast.yml")
TEST = os.path.join("tests", "site_nav_drift", "test_star_fast_wiring.py")

RETRY_BLOCK = """          if ! git push; then
            # 小时场 bot 并发提交 → merge 远端重试一次；再失败放弃提交（下场重新 diff 补判，
            # 数据不丢）。放弃优于阻塞发布。
            # ⚠ fetch 的深度不是可有可无的参数：actions/checkout 是浅检出，`--depth=1` 只取远端
            # tip 一层、把它变成 grafted 历史 ⇒ merge 报 "refusing to merge unrelated histories"
            # 并被下面的 || true 吞掉 ⇒ 二次 push 照旧 non-fast-forward ⇒ 重试永远走放弃分支
            # （判据 test_star_fast_lands_after_a_clean_collision 实测：depth=1 推不上去，2/10 可以）。
            git fetch origin main --depth=10 || true
            git merge origin/main --no-edit || true
            git push || echo "::warning::[fast] star 状态提交被拒，本场放弃（下一场补）"
          fi"""

MUTATIONS = [
    ("M1 浅 fetch 退回 depth=1（生产原状）",
     "git fetch origin main --depth=10 || true", "git fetch origin main --depth=1 || true",
     "test_star_fast_lands_after_a_clean_collision"),
    ("M2 整段重试被删",
     RETRY_BLOCK, "          git push",
     "test_star_fast_lands_after_a_clean_collision"),
    ("M3 merge 的软失败保护被摘",
     "git merge origin/main --no-edit || true", "git merge origin/main --no-edit",
     "test_star_fast_survives_a_merge_conflict"),
    ("M4 放弃改成挡发布（exit 1）",
     'git push || echo "::warning::[fast] star 状态提交被拒，本场放弃（下一场补）"',
     "git push || exit 1",
     "test_star_fast_survives_a_merge_conflict"),
    ("M5 不再写 changed 信号",
     '          echo "changed=true" >> "$GITHUB_OUTPUT"', "",
     "test_star_fast_clean_push_skips_the_retry"),
    # 注：单独把重试里的 push 加 --force 是**无效变异**——merge 已经成功，force 与普通 push 等价，
    # 谁都不会受伤（第一版误把它当缺陷，判据正确地放行了）。有破坏力的是"跳过 merge 直接覆盖远端"，
    # 那才是必须拦的形态。
    ("M6 跳过 merge 直接 force 覆盖远端",
     "            git fetch origin main --depth=10 || true\n"
     "            git merge origin/main --no-edit || true\n"
     '            git push || echo "::warning::[fast] star 状态提交被拒，本场放弃（下一场补）"',
     "            git fetch origin main --depth=10 || true\n"
     '            git push --force || echo "::warning::[fast] star 状态提交被拒，本场放弃（下一场补）"',
     "test_star_fast_lands_after_a_clean_collision"),
]


def _run(tmp, name):
    env = {**os.environ, "STAR_FAST_YML": os.path.join(tmp, YML),
           "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-k", name],
                       cwd=tmp, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _stage(tmp):
    for rel in (YML, TEST, ".gitignore"):
        dst = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dst)


def main():
    if shutil.which("bash") is None or shutil.which("git") is None:
        print("缺 bash/git，无法实跑（这电池必须跑 shell，不降级为文本检查）")
        return 1
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, ".deploy-tmp")) as tmp:
        _stage(tmp)
        for mid, old, new, must in MUTATIONS:
            _stage(tmp)  # 每轮从干净副本重打
            p = os.path.join(tmp, YML)
            s = io.open(p, encoding="utf-8").read()
            n = s.count(old)
            if n != 1:
                bad.append("%s：靶子在 yml 里出现 %d 次 ⇒ 锚点失效，变异没打上" % (mid, n))
                continue
            io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new, 1))
            code, out = _run(tmp, must)
            if code == 0:
                bad.append("%s：打了坏改动，%s 仍然绿 ⇒ 空判据" % (mid, must))
                continue
            if "failed" not in out and "error" not in out.lower():
                bad.append("%s：非零退出但不是判据红（可能是收集崩）：%s" % (mid, out[-300:]))
                continue
            print("  %-38s 挡住 → %s" % (mid, must))

        # 收尾对照：副本恢复原样后三条必须全绿（证明上面的红来自变异，不是环境）
        _stage(tmp)
        code, out = _run(tmp, "clean_collision or merge_conflict or skips_the_retry")
        print("  对照组（未变异副本）：%s" % out.strip().splitlines()[-1])
        if code != 0:
            bad.append("对照组不绿 ⇒ 上面所有红都不能归因于变异")

    if bad:
        print("\n%d 项不合格：" % len(bad))
        for b in bad:
            print("  - " + b)
        return 1
    print("\n全部 %d 个变异都被各自靶判据挡住，且对照组全绿。" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
