# -*- coding: utf-8 -*-
"""原子推送检查的回归测试：推 workflow 时，它引用的测试路径必须同批推上去或远端与本地逐文件一致。

依据链（不是假想风险，是 09-20 实测）：
- 远端 `update.yml` 的门禁 A2 = `python -m pytest tests/rss_history/ tests/rss_source_coverage/ -q -s`，
  该步骤**没有** `continue-on-error` → blocking；
- `Deploy to Vercel` 步骤**没有** `if:` → 默认 `success()`；
- 所以 "workflow 上去了、新测试目录没上去" 会让 pytest 以退出码 4 失败 →
  **Commit 步骤与 Vercel 部署一起被跳过**，站点整小时冻住（与 `fetch_and_build 吞异常` 那类"CI 绿但产物冻结"相反，这次是 CI 红且冻结）。

2026-09-20 对抗审查后补的三件事（每条都有对应用例）：
- 路径必须相对**仓库根**解析，不能用 CWD；
- 通配/matrix 模板写法不能判红（误伤），也不能悄悄放过（要提示人工确认）；
- 远端"目录存在"不够——里面文件与本地不一致照样会让 A2 红，所以要逐文件比 blob。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import data_api_push as D  # noqa: E402

WF_TEXT = ("      - name: Quality gate A2\n"
           "        run: python -m pytest tests/rss_history/ tests/%s/ -q -s\n")


def _wf(tmp_path, run_line=None, name=None):
    p = tmp_path / "update.yml"
    body = run_line if run_line is not None else (WF_TEXT % name)
    p.write_text("      - name: Quality gate A2\n        run: %s\n" % body, encoding="utf-8")
    return str(p)


def _problems(push_paths, wf):
    return D.ci_atomic_deps(push_paths, wf)[0]


def test_import_does_not_execute_main():
    """模块级 `sys.exit(main())` 会让 pytest 在收集阶段直接退出 —— 必须有 __main__ 守卫。"""
    src = open(os.path.join(ROOT, "tools", "data_api_push.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    assert any(isinstance(n, ast.If) and "__main__" in ast.dump(n.test) for n in tree.body), \
        "data_api_push.py 缺 if __name__ == '__main__' 守卫"
    assert not any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                   and getattr(n.value.func, "attr", "") == "exit" for n in tree.body), \
        "模块级 sys.exit() 会在导入时执行"


def test_no_duplicate_definitions():
    """审查抓到过一次 `def ci_atomic_deps` 写了两遍（前一个是只有 docstring 的死函数）。"""
    src = open(os.path.join(ROOT, "tools", "data_api_push.py"), encoding="utf-8").read()
    names = [n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)]
    dup = sorted({x for x in names if names.count(x) > 1})
    assert not dup, "存在重复定义的顶层函数：%s" % dup


def test_flagged_when_referenced_dir_absent_locally(tmp_path):
    problems = _problems([D.WF], _wf(tmp_path, name="no_such_dir_zz"))
    assert problems, "引用的测试目录本地都不存在，必须判不通过（否则门禁必红）"
    # 只锁"报的是哪条路径"，不锁措辞 —— 变异体 M2 证明改文案不会误红
    assert any("no_such_dir_zz" in p for p in problems)


def test_flagged_when_dir_local_only_and_remote_stale(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("404")
    monkeypatch.setattr(D, "req", boom)
    problems = _problems([D.WF], _wf(tmp_path, name="rss_history"))
    assert problems, "目录本地有、远端取不到、又不在本次推送里 —— 正是停摆组合，必须判不通过"
    assert any("rss_history" in p for p in problems)


def test_flagged_when_remote_exists_but_content_differs(tmp_path, monkeypatch):
    """审查指出的漏口：只判"远端有这个文件"会放行一份远端已过期的测试，A2 照样红。"""
    monkeypatch.setattr(D, "req", lambda *a, **k: {"sha": "0" * 40})
    seen = []
    monkeypatch.setattr(D, "_git_blob_sha", lambda rel: seen.append(rel) or "1" * 40)
    problems = _problems([D.WF], _wf(tmp_path, name="rss_history"))
    assert seen, "必须真的逐文件比过 blob"
    assert problems, "远端 blob 与本地不一致 → 不能算『远端已有』"


def test_clean_when_dir_already_on_remote_identical(tmp_path, monkeypatch):
    def same(method, path, body=None, tries=6):
        return {"sha": D._git_blob_sha(path.split("/contents/")[-1])}
    monkeypatch.setattr(D, "req", same)
    wf = _wf(tmp_path, name="rss_history")
    assert _problems([D.WF], wf) == [], "远端逐文件一致 → 单推 workflow 是安全的，不该误报"


def test_clean_when_dir_shipped_in_same_push(tmp_path, monkeypatch):
    """同一批里带上新目录就不该再要求远端存在 —— 这条是"必须绿"的反向变异靶子。"""
    calls = []

    def spy(*a, **k):
        calls.append(a[1] if len(a) > 1 else k.get("path"))
        raise RuntimeError("不该被调用：路径已在本次推送集里")
    monkeypatch.setattr(D, "req", spy)
    assert _problems([D.WF, "tests/rss_history"], _wf(tmp_path, name="rss_history")) == []
    assert calls == []


def test_glob_and_matrix_paths_are_not_false_red(tmp_path):
    """通配与 matrix 模板不能判红（误伤），但要落到"人工确认"清单里。"""
    for body in ("python -m pytest tests/* -q",
                 "python -m pytest tests/${{ matrix.dir }}/ -q",
                 "python -m pytest tests/ --ignore=tests/slow -q"):
        problems, odd = D.ci_atomic_deps([D.WF], _wf(tmp_path, run_line=body))
        assert problems == [], "非字面路径不该判红：%s → %s" % (body, problems)
        if "--ignore" not in body:
            assert odd, "通配/matrix 写法必须提示人工确认：%s" % body


def test_expand_paths_is_repo_root_relative_not_cwd(tmp_path, monkeypatch):
    """审查抓到的第二类 bug：原实现用 CWD 相对路径，从别的目录调用就误判"本地不存在"。"""
    monkeypatch.chdir(str(tmp_path))
    assert D.list_files("tests/rss_history") and D.norm_path(".\\tests\\rss_history") == "tests/rss_history"
    problems = _problems([D.WF], _wf(tmp_path, name="rss_history"))
    assert not any("本地不存在" in p for p in problems), "换 CWD 不该让已存在的目录判成本地不存在"


def test_expand_paths_skips_pycache(tmp_path):
    d = tmp_path / "pkg"
    (d / "__pycache__").mkdir(parents=True)
    (d / "test_a.py").write_text("x", encoding="utf-8")
    (d / "b.pyc").write_text("x", encoding="utf-8")
    (d / "__pycache__" / "test_a.pyc").write_text("x", encoding="utf-8")
    # tmp_path 在 C: 而仓库在 E: —— 跨盘符时 relpath 会抛 ValueError（审查后修的坑），
    # 所以这里按绝对路径入口验"展开了什么"，不假设能相对化
    got = [os.path.basename(x) for x in D.expand_paths([str(d).replace(os.sep, "/")])]
    assert got == ["test_a.py"], "目录应展开成可枚举文件，且排除 __pycache__ 与 .pyc，实得 %s" % got


def test_binary_payload_is_not_crlf_mangled():
    """仓库里有被跟踪的 .png；无条件 CRLF→LF 会把二进制改坏（审查 P1）。"""
    png = open(os.path.join(ROOT, "actions-step5-expanded.png"), "rb").read(4096)
    assert D.is_binary_bytes(png), "识别不出二进制 → 上传前会被 CRLF 归一毁掉"
    assert not D.is_binary_bytes(b"# -*- coding: utf-8 -*-\r\nprint(1)\r\n")


def test_real_workflows_resolve_from_repo_root():
    """对仓库里真实存在的每个 workflow 跑一遍：不得出现"本地不存在"的误报。"""
    wdir = os.path.join(ROOT, ".github", "workflows")
    for fn in sorted(os.listdir(wdir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        problems, _odd = D.ci_atomic_deps([], ".github/workflows/" + fn)
        assert not [p for p in problems if "本地不存在" in p], "%s: %s" % (fn, problems)
