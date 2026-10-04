# -*- coding: utf-8 -*-
"""T3 快车道判据（A3 advisory）：
- 无新星 → 零文件写（index.html/三缓存都不动）；
- 有新星 → index.html 重生成且新星在 DATA 中、三缓存写回含新星；
- 拉取失败 → ::warning:: 退出 0，不炸 CI；
- 红线：不 import fetch_and_build 的 main（RSS/洞察/Vercel 不许被触发）。
网络全打桩；断言不写死日期。"""
import importlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fetch_and_build as fab  # noqa: E402
import fast_refresh as fr  # noqa: E402


def _repo(fn, desc="demo project"):
    owner, name = fn.split("/")
    return {"full_name": fn, "name": name, "owner": owner, "description": desc,
            "language": "Python", "stargazers_count": 42, "topics": ["ai"],
            "html_url": "https://github.com/%s" % fn,
            "pushed_at": "2026-09-01T00:00:00Z", "starred_at": "2026-10-01T00:00:00Z"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """把快车道的读写都引到 tmp_path（ monkeypatch 模块常量）。"""
    monkeypatch.setattr(fr, "ROOT", str(tmp_path))
    monkeypatch.setattr(fr, "KC_PATH", str(tmp_path / "known_categories.json"))
    monkeypatch.setattr(fr, "NOTES_PATH", str(tmp_path / "known_notes.json"))
    monkeypatch.setattr(fr, "DESC_PATH", str(tmp_path / "descriptions_zh.json"))
    monkeypatch.setattr(fr, "_atomic_write_json", fr._atomic_write_json)
    # build_index_html 读模板+写 index.html：模板读真实文件，index.html 写进 tmp_path
    monkeypatch.chdir(tmp_path)
    known = {"old/one": "coding", "old/two": "video"}
    (tmp_path / "known_categories.json").write_text(json.dumps(known), encoding="utf-8")
    (tmp_path / "descriptions_zh.json").write_text("{}", encoding="utf-8")
    # 侧栏快照现在是快车道的**前置条件**（缺它就不发布首页，见 test_sidebar_snapshot_wiring.py），
    # 所以这里给一份合法的：本文件继续测自己的主题（新星重生成整页 + 三缓存写回），
    # 而不是被前置缺失牵着走——注意这是补条件，不是放松任何一条断言。
    (tmp_path / "sidebar_snapshot.json").write_text(json.dumps({
        "trending": {"rising": [{"full_name": "old/one", "stars": 5}], "total": [], "new": []},
        "feed": [{"full_name": "someone/event"}], "ai_summary_html": ""}), encoding="utf-8")
    return tmp_path


def test_no_new_star_means_zero_writes(env, monkeypatch):
    monkeypatch.setattr(fab, "fetch_stars", lambda token: [_repo("old/one"), _repo("old/two")])
    before = sorted(os.listdir(env))
    rc = fr.main()
    assert rc == 0
    assert sorted(os.listdir(env)) == before          # 零新文件（index.html/三缓存都不动）


def test_no_new_star_logs_skip(env, monkeypatch, capsys):
    monkeypatch.setattr(fab, "fetch_stars", lambda token: [_repo("old/one")])
    assert fr.main() == 0
    assert "no change, skip write" in capsys.readouterr().out


def test_new_star_regenerates_index_and_writes_caches(env, monkeypatch, capsys):
    monkeypatch.setattr(fab, "fetch_stars",
                        lambda token: [_repo("old/one"), _repo("brand/new", "a brand new thing")])
    monkeypatch.setattr(fab, "classify_llm",
                        lambda *a, **k: {"category": "tools", "note": "小工具一枚"})
    rc = fr.main()
    assert rc == 0
    html = (env / "index.html").read_text(encoding="utf-8")
    assert '"brand/new"' in html                       # 新星进了 DATA
    assert '"old/one"' in html                         # 全量重组（老星也在）
    known = json.loads((env / "known_categories.json").read_text(encoding="utf-8"))
    assert known["brand/new"] == "tools"
    notes = json.loads((env / "known_notes.json").read_text(encoding="utf-8"))
    assert notes.get("brand/new") == "小工具一枚"
    desc = json.loads((env / "descriptions_zh.json").read_text(encoding="utf-8"))
    assert isinstance(desc, dict)
    assert "wrote 1" in capsys.readouterr().out


def test_fetch_failure_warns_and_exits_zero(env, monkeypatch, capsys):
    monkeypatch.setattr(fab, "fetch_stars", lambda token: None)
    assert fr.main() == 0
    out = capsys.readouterr().out
    assert "::warning::" in out and "拉取 star 失败" in out


def test_fast_refresh_never_imports_main_pipeline():
    """红线：快车道不许触发 RSS/洞察/Vercel——import fast_refresh 不产生任何产物文件。"""
    mod = importlib.reload(fr)
    assert hasattr(mod, "main")
    # fetch_and_build 的 main 不在 fast_refresh 的调用面里（源码静态断言）
    src = open(mod.__file__, encoding="utf-8").read()
    assert ".main(" not in src
