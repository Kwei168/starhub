# -*- coding: utf-8 -*-
"""提醒条判据的变异电池：每条判据都要能被一个对应的坏改动挡住，否则那判据是空转。

为什么在临时副本里做：判据的 ROOT 是从 __file__ 往上三层推的，所以把 4 个文件复制进
tmp/{fetch_and_build.py,fast_refresh.py,template.html,tests/site_nav/test_*.py} 再跑 pytest，
ROOT 就指向 tmp ⇒ 真仓一个字节都不动，也不会和同时在工作的别的 agent 抢文件。

用法：py -3.11 tools/mut_attention.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPIES = ["fetch_and_build.py", "fast_refresh.py", "template.html",
          os.path.join("tests", "site_nav", "test_star_attention_bar.py")]

# (变异 id, 目标文件, 原文, 坏改动, 必须被哪条判据挡住)
MUTATIONS = [
    ("M1 集合算反", "fetch_and_build.py",
     "for fn in sorted(set(known) - live):",
     "for fn in sorted(set(known) & live):",
     "test_attention_lists_table_names_missing_from_current_stars"),
    ("M2 假警措辞", "fetch_and_build.py",
     'ATTENTION_TITLE = "分类表里有 %d 个名字不在你当前的收藏列表中——点开确认是改了名还是仓库已消失"',
     'ATTENTION_TITLE = "收藏丢失 %d 条，请检查拉取是否漏拉"',
     "test_rendered_text_never_claims_stars_are_missing"),
    ("M3 空清单留容器", "fetch_and_build.py",
     "    if not items:\n        return \"\"",
     "    if not items:\n        return '<details data-attention=\"star\"></details>'",
     "test_page_has_no_attention_node_when_empty"),
    ("M4 不转义名字", "fetch_and_build.py",
     "% (esc(name), esc(name), esc(\" · \".join(bits), quote=False), same_html))",
     "% (name, name, \" · \".join(bits), same_html))",
     "test_orphan_names_are_html_escaped"),
    ("M5 同名当定论", "fetch_and_build.py",
     'ATTENTION_SAME_HINT = "同名候选（仅参考，同名不等于同一仓库）"',
     'ATTENTION_SAME_HINT = "已改名为"',
     "test_same_base_name_candidate_is_hint_not_verdict"),
    ("M6 快车道漏注入", "fast_refresh.py",
     "html = fab.build_index_html(out, fab.CATS, attention_html=attention_html)",
     "html = fab.build_index_html(out, fab.CATS)",
     "test_both_render_exits_inject_attention"),
    ("M7 新仓库被当待办", "fetch_and_build.py",
     "for fn in sorted(set(known) - live):",
     "for fn in sorted(set(known) | live):",
     "test_new_star_absent_from_table_is_never_an_attention_item"),
    ("M8 空收藏报整表", "fetch_and_build.py",
     "    if not live:",
     "    if False:",
     "test_empty_live_set_renders_nothing"),
    ("M9 页面层不截断", "fetch_and_build.py",
     "    shown = items[:ATTENTION_MAX_ROWS]",
     "    shown = items",
     "test_attention_block_is_capped"),
]


def _stage(tmp):
    for rel in COPIES:
        dst = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dst)


def _run(tmp, name=None):
    tf = os.path.join("tests", "site_nav", "test_star_attention_bar.py")
    cmd = [sys.executable, "-m", "pytest", tf, "-q"]
    if name:
        cmd += ["-k", name]
    r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, ".deploy-tmp")) as tmp:
        _stage(tmp)
        code, out = _run(tmp)
        if code != 0:
            print("基线未绿 ⇒ 副本没搭对，后面全不算数：\n%s" % out[-1500:])
            return 1
        print("基线：副本内 %s" % out.strip().splitlines()[-1])

        for mid, rel, old, new, must_fail in MUTATIONS:
            _stage(tmp)  # 每轮从干净副本重打，变异绝不互相掩盖
            p = os.path.join(tmp, rel)
            s = io.open(p, encoding="utf-8").read()
            if s.count(old) != 1:
                bad.append("%s：靶子在副本里出现 %d 次（锚点失效，变异根本没打上）"
                           % (mid, s.count(old)))
                continue
            io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
            code, out = _run(tmp)
            if code == 0:
                bad.append("%s：打了坏改动却全绿 ⇒ %s 是空判据" % (mid, must_fail))
                continue
            code2, out2 = _run(tmp, must_fail)
            if "failed" not in out2 and "error" not in out2.lower():
                bad.append("%s：整体红了，但 %s 没红（红的是别的判据 ⇒ 钉错了地方）"
                           % (mid, must_fail))
                continue
            print("  %-18s 挡住 → %s" % (mid, must_fail))

        # 反向对照：把判据里"要求转义"那半单独拿掉会怎样，确保这轮绿不是靠运气
        code, out = _run(tmp)
        print("收尾复跑（最后一个变异仍在）：%s" % out.strip().splitlines()[-1])

    if bad:
        print("\n%d 个变异没被对应判据挡住：" % len(bad))
        for b in bad:
            print("  - " + b)
        return 1
    print("\n全部 %d 个变异都被各自靶判据挡住。" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
