# -*- coding: utf-8 -*-
"""原子推送检查的回归测试：推 workflow 时，它引用的测试路径必须同批推上去或远端已有。

依据链（不是假想风险，是 09-20 实测）：
- 远端 `update.yml` 的门禁 A2 = `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`，
  该步骤**没有** `continue-on-error` → blocking；
- `Deploy to Vercel` 步骤**没有** `if:` → 默认 `success()`；
- 所以 "workflow 上去了、新测试目录没上去" 会让 pytest 以退出码 4 失败 →
  **Commit 步骤与 Vercel 部署一起被跳过**，站点整小时冻住（与 `fetch_and_build 吞异常` 那类"CI 绿但产物冻结"相反，这次是 CI 红且冻结）。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import data_api_push as D  # noqa: E402

WF_TEXT = ("      - name: Quality gate A2\n"
           "        run: python -m pytest tests/rss_history/ tests/%s/ -q -s\n")


def _wf(tmp_path, name):
    p = tmp_path / "update.yml"
    p.write_text(WF_TEXT % name, encoding="utf-8")
    return str(p)


def test_import_does_not_execute_main():
    """模块级 `sys.exit(main())` 会让 pytest 在收集阶段直接退出 —— 必须有 __main__ 守卫。"""
    src = open(os.path.join(ROOT, "tools", "data_api_push.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    guards = [n for n in tree.body if isinstance(n, ast.If)
              and "__main__" in ast.dump(n.test)]
    assert guards, "data_api_push.py 缺 if __name__ == '__main__' 守卫"
    assert not any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                   and getattr(n.value.func, "attr", "") == "exit" for n in tree.body), \
        "模块级 sys.exit() 会在导入时执行"


def test_flagged_when_referenced_dir_absent_locally(tmp_path):
    wf = _wf(tmp_path, "no_such_dir_zz")
    problems = D.ci_atomic_deps([D.WF, "build_rss_aggregator.py"], wf=wf)
    assert problems, "引用的测试目录本地都不存在，必须判不通过（否则 A2 必红）"
    # 只锁"报的是哪条路径"，不锁措辞 —— 变异体 M2 证明改文案不会误红
    assert any("no_such_dir_zz" in p for p in problems)


def test_flagged_when_dir_local_only_and_not_on_remote(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("404")
    monkeypatch.setattr(D, "req", boom)
    wf = _wf(tmp_path, "rss_history")
    problems = D.ci_atomic_deps([D.WF], wf=wf)
    assert problems, "目录本地有、远端没有、又不在本次推送里 —— 正是停摆组合，必须判不通过"
    assert any("rss_history" in p for p in problems)


def test_clean_when_dir_already_on_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "req", lambda *a, **k: {"sha": "x"})
    wf = _wf(tmp_path, "rss_history")
    assert D.ci_atomic_deps([D.WF], wf=wf) == [], "远端已有该目录 → 单推 workflow 是安全的，不该误报"


def test_clean_when_dir_shipped_in_same_push(tmp_path, monkeypatch):
    """同一批里带上新目录就不该再要求远端存在 —— 这条是"必须绿"的反向变异靶子。"""
    calls = []

    def spy(*a, **k):
        calls.append(a[1] if len(a) > 1 else k.get("path"))
        raise RuntimeError("不该被调用：路径已在本次推送集里")
    monkeypatch.setattr(D, "req", spy)
    wf = _wf(tmp_path, "rss_history")
    assert D.ci_atomic_deps([D.WF, "tests/rss_history"], wf=wf) == []
    assert calls == []


def test_expand_paths_expands_dirs_and_skips_pycache(tmp_path):
    d = tmp_path / "tests" / "pkg"
    (d / "__pycache__").mkdir(parents=True)
    (d / "test_a.py").write_text("x", encoding="utf-8")
    (d / "b.pyc").write_text("x", encoding="utf-8")
    (d / "__pycache__" / "test_a.pyc").write_text("x", encoding="utf-8")
    rel = str(d).replace(os.sep, "/")
    out = D.expand_paths([rel])
    assert out == [rel + "/test_a.py"], "目录应展开成可枚举文件，且排除 __pycache__ 与 .pyc"


def test_real_workflow_paths_resolve():
    """对仓库里真实的 update.yml 跑一遍：它引用的测试路径此刻必须可解析（本地存在）。"""
    wf = os.path.join(ROOT, D.WF.replace("/", os.sep))
    if not os.path.exists(wf):
        return
    problems = [p for p in D.ci_atomic_deps([D.WF], wf=wf) if "本地不存在" in p]
    assert not problems, "本地 update.yml 引用了本地不存在的测试路径：%s" % problems
