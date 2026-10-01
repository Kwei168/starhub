# -*- coding: utf-8 -*-
"""批 6 变异电池：健康监测这几条接缝能不能被静默捅穿。

用法：python tools/mut_history_growth.py
判据文件读 STARHUB_GROWTH_TOOL / STARHUB_UPDATE_YML ⇒ 变异体只写临时副本，绝不就地改工具或 workflow。
与 mut_state_cache.py 同一约定：基线不绿就拒绝自评；变异没落到字节上算 INVALID（计为未覆盖）。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "history_growth.py")
WF = os.path.join(ROOT, ".github", "workflows", "update.yml")
TEST = os.path.join("tests", "rss_history", "test_history_growth.py")
TMP = os.path.join(ROOT, ".deploy-tmp")
STEP_MARK = "      - name: Monitor per-build git growth (advisory)\n"


def main():
    tool = open(TOOL, encoding="utf-8").read()
    wf = open(WF, encoding="utf-8").read()
    assert tool.count("def threshold():") == 1 and wf.count(STEP_MARK) == 1, "锚点自检失败"

    MUTS = [
        ("H1 阈值写成 0（天天误报=没人看的告警）", (tool.replace("    return DEFAULT_THRESHOLD", "    return 0", 1), wf)),
        ("H2 verdict 永远 ok（回退 20 MiB/场 也不出声）",
         (tool.replace('    return "warn" if new_bytes >= threshold() else "ok"', '    return "ok"', 1), wf)),
        ("H3 只数新增、不数内容变化（旧 blob 被覆盖仍是永久多一份）",
         (tool.replace("        if prev.get(path, (None,))[0] != sha:",
                       "        if path not in prev:", 1), wf)),
        ("H4 ls-tree 取错列（把 sha 当大小 ⇒ 读数恒 0）",
         (tool.replace('size = 0 if cols[3] == "-" else int(cols[3])', "size = 0", 1), wf)),
        ("H5 播报里去掉 ::warning（只在 stdout 打印会被漏看）",
         (tool.replace('out.append("::warning title=每场新增字节超阈值::', 'out.append("note: ', 1), wf)),
        ("H6 去掉 continue-on-error（advisory 步一红就连坐两次部署）",
         (tool, wf.replace(STEP_MARK + "        #", STEP_MARK + "        #", 1)
               .replace("        continue-on-error: true\n        run: |\n          python tools/history_growth.py",
                        "        run: |\n          python tools/history_growth.py", 1))),
        ("H7 把测量步挪到 Commit 之前（量到上一场，本场膨胀恰好看不见）",
         (tool, wf.replace(STEP_MARK, "", 1).replace(
             "      - name: Commit & push if changed", STEP_MARK + "      - name: Commit & push if changed", 1))),
    ]

    def run(mut_tool, mut_wf, label):
        if (mut_tool == tool) and (mut_wf == wf):
            return "%-56s INVALID（变异没落到任何字节上）" % label, False
        os.makedirs(TMP, exist_ok=True)
        tp = os.path.join(TMP, "_mut_history_growth.py")
        wp = os.path.join(TMP, "_mut_hg_update.yml")
        open(tp, "w", encoding="utf-8", newline="\n").write(mut_tool)
        open(wp, "w", encoding="utf-8", newline="\n").write(mut_wf)
        env = dict(os.environ, STARHUB_GROWTH_TOOL=tp, STARHUB_UPDATE_YML=wp, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                            "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        lines = (p.stdout or "").strip().splitlines()
        failed = sorted({l.split("::")[-1].split(" ")[0] for l in lines if l.startswith("FAILED")})
        return "%-56s %s %s%s" % (label, "RED  " if p.returncode else "GREEN(判据漏了!)",
                                  (lines[-1] if lines else "?")[:56],
                                  ("  <- " + ", ".join(failed[:2])) if failed else ""), p.returncode != 0

    base = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    print("基线（未变异）：%s  rc=%d" % ((base.stdout.strip().splitlines() or ["?"])[-1], base.returncode))
    if base.returncode != 0:
        print(base.stdout[-1500:])
        print("基线不绿 ⇒ 不声称任何覆盖率")
        return 1
    escapes = 0
    for label, (mt, mw) in MUTS:
        out, caught = run(mt, mw, label)
        print(out)
        if not caught:
            escapes += 1
    print("\n未被挡住的变异/无效变异：%d" % escapes)
    return 1 if escapes else 0


if __name__ == "__main__":
    sys.exit(main())
