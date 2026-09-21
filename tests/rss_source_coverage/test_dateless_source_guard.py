# tests/rss_source_coverage/test_dateless_source_guard.py
# -*- coding: utf-8 -*-
"""「逐条没有发布日期的源」这一批的落地判据。

Why（哪次故障逼出来的）：2026-09-21 统计线上产物时发现有 321 条正靠降级日期显示，
追到源头是几类 feed 里压根没有日期元素（plink.anyfeeder 代理结构性丢日期、
RSSHub 的日经路由、旧 Blogger 地址）。用户判定：真没日期的源可以去掉，
给了日期却被我们判成没给的（裸两位偏移 +08）要修算法不许删。

这批改动有两处静默失效的面，所以判据必须成对：
  1) 工具里声明了，清单文件没重放 ⇒ 线上照旧抓那 4 个源（补丁"看起来在"但没生效）；
  2) 清单改了，工具里的声明被回滚 ⇒ 下一次任何人在别的基线上重放，源又回来了。
所以除了查最终文件，还查"重放幂等"（把 dateless 批次重放到当前清单的副本上，必须零动作）。

三条判据都是离线的：不抓网络、不看时钟，可以进 blocking 门禁 A2。
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _loader import load_build  # noqa: E402

LIST_PATH = os.path.join(ROOT, "rss_sources.json")
TOOL_PATH = os.path.join(ROOT, "tools", "rss_source_list_patch.py")

# 逐条零日期、且没有任何备选地址能补上日期的源（探测记录见 specs 2026-09-20-rss-72h-retention-design §16/§17）
DATELESS_GONE = ["nikkei_rsshub_802", "喷嚏网铂程斋_11", "bbc英语教学_13", "中国日报双语_2",
                 "google_dev_76"]
# 内容质量类删除：日期是好的，理由不能混进"没日期"那一堆
QUALITY_GONE = ["超能网_31"]
GONE = DATELESS_GONE + QUALITY_GONE
# 曾经"没日期"其实是我们接错地址：官方镜像逐条带 pubDate，删掉就是净损失
DATED_MOVED = {
    "google_developers_blog_406": "https://blog.google/technology/developers/rss/",
    "美团技术团队_0": "https://tech.meituan.com/atom.xml",
}
OLD_DATELESS_URLS = {
    "google_developers_blog_406": "https://developers.googleblog.com/feeds/posts/default",
    "美团技术团队_0": "https://tech.meituan.com/feed",
}
# 这批改动落地前的原始条目（取自 origin/main 的 1005 条清单），用于"声明真的能干活"的重放判据。
PRE_BATCH_DELETED = [
    {"key": "nikkei_rsshub_802", "name": "日经新闻", "cat": "news", "color": "#003366",
     "url": "https://rsshub.rssforever.com/nikkei/index", "tier": 2},
    {"key": "喷嚏网铂程斋_11", "name": "喷嚏网铂程斋", "cat": "news", "color": "#1565c0",
     "url": "https://plink.anyfeeder.com/dapenti/xilei", "tier": 2},
    {"key": "bbc英语教学_13", "name": "BBC英语教学", "cat": "news", "color": "#bb1919",
     "url": "https://plink.anyfeeder.com/bbc/learningenglish", "tier": 3},
    {"key": "中国日报双语_2", "name": "中国日报双语", "cat": "news", "color": "#cc0000",
     "url": "https://plink.anyfeeder.com/chinadaily/dual", "tier": 3},
    {"key": "google_dev_76", "name": "Google Developers", "cat": "tech", "color": "#4285f4",
     "url": "https://developers.googleblog.com/feeds/posts/default/", "tier": 3},
    {"key": "超能网_31", "name": "超能网", "cat": "cn_tech", "color": "#0091ea",
     "url": "https://plink.anyfeeder.com/expreview", "tier": 2, "pub_date_offset_min": -480},
]


def _tool():
    spec = importlib.util.spec_from_file_location("rss_source_list_patch", TOOL_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _replay(entries, scope="dateless"):
    """把补丁重放到给定清单上，返回重放后的清单（写盘走临时目录，不碰工作区）。"""
    tool = _tool()
    tmp = tempfile.mkdtemp(prefix="rsplist-")
    try:
        dst = os.path.join(tmp, "rss_sources.json")
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(entries, ensure_ascii=False, separators=(",", ":")))
        tool.PATH = dst
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):   # 工具打中文，Windows 控制台编码能炸
            tool.run(apply=True, scope=scope)
        with open(dst, encoding="utf-8") as f:
            return json.load(f), open(dst, "rb").read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _list_sources():
    with open(LIST_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_source_list_is_loaded_and_nontrivial():
    """防空跑：清单只有几条时后面所有"某 key 不存在"的断言都是白过的。

    这是同日对抗审查里点名的同类缺陷（隔离树 git ls-files 返回空 ⇒ 全仓扫描静默 no-op）。
    """
    src = _list_sources()
    assert len(src) > 500, "rss_sources.json 只读到 %d 条，判据视为无效" % len(src)
    keys = [s.get("key") for s in src]
    assert len(keys) == len(set(keys)), "清单有重复 key，后面的按 key 断言不可信"


def test_dateless_sources_stay_deleted():
    src = _list_sources()
    by_key = {s.get("key"): s for s in src}
    for key in GONE:
        assert key not in by_key, (
            "%s 又回到清单里了：它属于本批判定要剔除的源（无逐条日期或内容质量），"
            "重新加回请先给出对应理由" % key)


def test_no_source_keeps_the_old_dateless_blogger_url():
    """同一家出版方不能留两把钥匙，其中一把还指着逐条零日期的旧 Blogger 地址。

    google_dev_76 与 google_developers_blog_406 只差一个结尾斜杠。_406 换址之后，
    旧地址若还被某个 key 用着，那 20 条卡片就永远没有时间位（产物实测 time_str 全空）。
    """
    for s in _list_sources():
        url = (s.get("url") or "").rstrip("/")
        assert not url.endswith("developers.googleblog.com/feeds/posts/default"), (
            "%s 仍指向无日期的旧 Blogger 地址 %s" % (s.get("key"), s.get("url")))


def test_dateless_sources_not_in_loaded_module():
    """构建脚本实际加载的清单也必须与文件一致（防"改了文件但构建读的是另一份"）。"""
    mod = load_build()
    live = {s.get("key") for s in mod.RSS_SOURCES}
    assert len(live) > 500, "RSS_SOURCES 只加载到 %d 条" % len(live)
    for key in GONE:
        assert key not in live, "%s 仍在构建期生效" % key


def test_moved_sources_point_at_dated_feeds():
    by_key = {s.get("key"): s for s in _list_sources()}
    for key, want in DATED_MOVED.items():
        got = (by_key.get(key) or {}).get("url")
        assert got == want, "%s 的地址应是带逐条日期的 %s，实际 %r" % (key, want, got)
        assert got != OLD_DATELESS_URLS[key], "%s 退回了没有日期字段的旧地址" % key


def test_declaration_actually_produces_the_shipped_list():
    """把"改动前"的清单交给工具重放，必须正好得到现在这份 shipped 清单。

    这条查的是声明能不能干活，而不是文件看起来对不对。变异体 M6（工具里 `if apply and
    len(src) != n0` 的原写法）专治这种：纯改址不动条数，旧写法根本不写盘，
    于是"重放过了"是假的 —— 只查最终文件永远看不出这个分叉。
    """
    shipped = _list_sources()
    pre = [dict(s) for s in shipped]
    by_key = {s["key"]: s for s in pre}
    for key, old in OLD_DATELESS_URLS.items():
        by_key[key]["url"] = old
    pre.extend(dict(s) for s in PRE_BATCH_DELETED)

    got, _ = _replay(pre)
    keys = {s["key"] for s in got}
    for key in GONE:
        assert key not in keys, "重放声明后 %s 仍在清单 ⇒ 工具里的删除没生效" % key
    for key, want in sorted(DATED_MOVED.items()):
        got_url = next((s["url"] for s in got if s["key"] == key), None)
        assert got_url == want, "重放声明后 %s 的地址是 %r，应为 %r（旧写法会静默不落盘）" % (key, got_url, want)
    assert len(got) == len(shipped), "重放结果 %d 条，与线上清单 %d 条不等 ⇒ 批次隔离被破坏" % (
        len(got), len(shipped))


def test_url_only_replay_actually_persists():
    """只改址、不动条数的那一半也必须落盘。

    工具原写法是 `if apply and len(src) != n0`：条数没变就不写盘，于是"删 4 条"生效了、
    "换 2 个地址"静默丢失 —— 清单看起来重放过了，两个源还在抓没有日期字段的旧地址。
    上一用例里条数会变，掩盖了这个分支，所以单独一条把 count 不变的情形钉住。
    """
    shipped = _list_sources()
    pre = [dict(s) for s in shipped]
    by_key = {s["key"]: s for s in pre}
    for key, old in OLD_DATELESS_URLS.items():
        by_key[key]["url"] = old
    got, raw = _replay(pre)
    for key, want in sorted(DATED_MOVED.items()):
        got_url = next((s["url"] for s in got if s["key"] == key), None)
        assert got_url == want, (
            "%s 重放后仍是 %r：纯改址没写盘，源会继续抓到没有日期字段的地址" % (key, got_url))
    assert len(got) == len(shipped)


def test_dateless_batch_replay_is_a_noop():
    """把这一批重放到当前清单上必须零动作 —— 声明与文件长期一致的可核对形式。

    变异体 M1/M2（清单被回滚）与 M4（dateless 批次偷偷执行了全量补丁）都由本用例拦截。
    """
    before = open(LIST_PATH, "rb").read()
    _, after = _replay(json.loads(before.decode("utf-8")))
    assert after == before, (
        "dateless 批次重放后清单变了 ⇒ 文件与 tools/rss_source_list_patch.py 的声明不一致："
        "要么这批没重放完，要么有人手改了文件而没进声明")


def test_batch_keys_are_declared_in_the_tool():
    """判据与声明同源：测试里写死的 key 必须真的出现在工具声明里，
    否则工具被人删掉一批时测试会一直绿着（锁错了对象）。"""
    tool = _tool()
    # 两个理由桶分别锁死：把"内容质量"塞进"没日期"（或反之）虽然都删得掉，
    # 却会在清单里留下一条假原因 —— 超能网今天实测 30/30 带 pubDate。
    assert set(tool.DATELESS_DELETE_KEYS) == set(DATELESS_GONE), "无日期桶与判据不一致"
    assert set(tool.QUALITY_DELETE_KEYS) == set(QUALITY_GONE), "内容质量桶与判据不一致"
    assert tool.DATED_URL_FIX == DATED_MOVED


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
