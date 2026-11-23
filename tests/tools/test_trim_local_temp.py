# -*- coding: utf-8 -*-
"""tools/trim_local_temp.py 的守卫测试：白名单 / keep-N / 可再生识别 / 散文件不碰。

只测纯函数 plan()/is_retained()，用 tmp_path 造假目录，不触碰真实 _scratch/.deploy-tmp，
也不执行回收（回收机制由 --self-test 单独验）。
"""
import os
import time

import pytest

import tools.trim_local_temp as t


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "ROOT", str(tmp_path))
    (tmp_path / "_scratch").mkdir()
    (tmp_path / ".deploy-tmp").mkdir()
    return tmp_path


def _mksub(base, name, age_days, now):
    p = base / name
    p.mkdir()
    f = p / "data.bin"
    f.write_bytes(b"x" * 10)
    mt = now - age_days * 86400
    os.utime(f, (mt, mt))
    return p


def test_retain_push_lock_and_fixtures(fake_root):
    assert t.is_retained(os.path.join("_scratch", ".mutation-lock"))
    assert t.is_retained(os.path.join(".deploy-tmp", "live-api-rss.json"))
    assert t.is_retained(os.path.join(".deploy-tmp", "_full_sort_harness.js"))
    assert t.is_retained(os.path.join(".deploy-tmp", "trigger-workflow.cjs"))
    assert not t.is_retained(os.path.join("_scratch", "diag"))


def test_regenerable_always_pruned(fake_root):
    now = time.time()
    sc = fake_root / "_scratch"
    _mksub(sc, "__pycache__", 1, now)
    _mksub(sc, "_mut_foo", 1, now)
    (sc / "empty_dir").mkdir()
    targets, _ = t.plan("_scratch", keep=5, days=30, now=now)
    names = {os.path.basename(p) for p in targets}
    assert {"__pycache__", "_mut_foo", "empty_dir"} <= names


def test_keep_newest_k_and_age(fake_root):
    now = time.time()
    sc = fake_root / "_scratch"
    # 6 个超龄子目录（年龄各异，排序确定）+ 2 个新鲜子目录
    for i in range(6):
        _mksub(sc, "old%d" % i, 60 + i, now)
    _mksub(sc, "fresh1", 1, now)
    _mksub(sc, "fresh2", 2, now)
    targets, kept = t.plan("_scratch", keep=5, days=30, now=now)
    # 保留最近 5 个：fresh1/fresh2 + 相对最新的 old0/old1/old2
    assert len(kept) == 5
    kept_names = {os.path.basename(p) for p in kept}
    assert {"fresh1", "fresh2", "old0", "old1", "old2"} == kept_names
    # 超龄且落在最近 5 个之外者被清
    tgt_names = {os.path.basename(p) for p in targets}
    assert tgt_names == {"old3", "old4", "old5"}
    # 新鲜子目录永不被清
    assert "fresh1" not in tgt_names and "fresh2" not in tgt_names


def test_loose_files_never_touched(fake_root):
    now = time.time()
    sc = fake_root / "_scratch"
    (sc / "big_snapshot.js").write_bytes(b"x" * 100)
    (sc / "script.py").write_bytes(b"x" * 100)
    targets, _ = t.plan("_scratch", keep=5, days=30, now=now)
    assert all(os.path.isdir(p) for p in targets)


def test_deploy_tmp_no_age_pruning(fake_root):
    now = time.time()
    dt = fake_root / ".deploy-tmp"
    _mksub(dt, "local-fixtures", 200, now)   # 超龄但在用夹具：保守档不清
    _mksub(dt, "__pycache__", 1, now)        # 可再生：清
    targets, kept = t.plan(".deploy-tmp", keep=5, days=30, now=now)
    names = {os.path.basename(p) for p in targets}
    assert "local-fixtures" not in names
    assert "__pycache__" in names
    assert kept == []


def test_retained_subdir_never_targeted(fake_root, monkeypatch):
    now = time.time()
    sc = fake_root / "_scratch"
    _mksub(sc, "protected", 200, now)
    monkeypatch.setattr(t, "RETAIN_REL", {os.path.join("_scratch", "protected")})
    targets, _ = t.plan("_scratch", keep=0 + 1, days=30, now=now)
    assert all(os.path.basename(p) != "protected" for p in targets)