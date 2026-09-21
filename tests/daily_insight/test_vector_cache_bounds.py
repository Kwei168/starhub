# -*- coding: utf-8 -*-
"""向量缓存合并处的淘汰与封顶（任务 #29，2026-09-21）。

现场（run 35566639074，14:13 场）：
    数据汇总: RSS 12244, 热榜 400, AIHOT 100, AGI Hunt 2245      ← RSS 占输入 82%
    增量合并: 旧 33485 + 新增 19125 = 52610 (去重后)
    FAISS 索引构建: 33797 向量
    meta.bm25_window = {non_rss:33697, rss_total:100, rss_budget_slots:0}
原实现 `build_daily_insight.py:5206-5214` 有三个问题，且**上限那一支自己没生效**：
    budget = MAX_EMBED_CHUNKS - len(other_mc)   # 30000 - 33697 = -3697
    if budget < 100: budget = 100               # RSS 从此钉死在 100 条
    merged = rss_mc + other_mc                  # 100 + 33697 = 33797 > 30000，封顶形同虚设
非RSS 一支从头到尾没有任何淘汰（同日 7 场 non_rss 单调 31840→33697，约 +370/场），
这与用户最初提的"不能无限增长、总有一天会撑爆"是同一缺陷族，只是长在洞察侧。

口径：RSS 优先按新鲜度保留，剩余名额给非RSS 按新鲜度填；两边都按 pub_date 淘汰超龄，
判不了龄的一律丢弃（与 :5130 的 `_hours_ago(None)==999 > 168` 现有边界一致，
所以无日期条目本来也进不了洞察 —— 沿用同一规则，不新造一类永生条目）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as B


def _mk(htype, idx, age_h, text=None):
    """造一个 chunk。age_h = 距今小时数；传 None 表示"判不了龄"（pub_date 空串）。"""
    from datetime import datetime, timedelta, timezone
    BJT = timezone(timedelta(hours=8))
    # 先算 pub 再判 age_h 会在 timedelta(hours=None) 上直接炸 —— 这就是"造数必须照出厂形状"
    pub = (datetime.now(BJT) - timedelta(hours=age_h)).isoformat() if age_h is not None else ""
    h = "h%s_%06d" % (htype[0], idx)
    return {"chunk_id": "c_" + h, "content_hash": h, "source_type": htype,
            "title": "t" + h, "pub_date": pub,
            "text": text or ("body " + h)}


def _split(merged):
    rss = [c for c in merged if c.get("source_type") == "rss"]
    other = [c for c in merged if c.get("source_type") != "rss"]
    return rss, other


def _age_h(c):
    """测试自己算龄期：生产里的 `_hours_ago` 依赖 main() 才初始化的 NOW_BJ，
    在测试上下文里是 None，会炸成 TypeError 而不是暴露判据问题。"""
    from datetime import datetime, timedelta, timezone
    dt = B._parse_iso(c.get("pub_date", ""))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    return (datetime.now(timezone(timedelta(hours=8))) - dt).total_seconds() / 3600.0


class TestMergeContract:
    def test_helper_exists_and_is_called(self):
        """新逻辑必须是可测函数，且真的被构建调用（防写成死函数/空转）。"""
        assert hasattr(B, "_merge_vector_cache"), \
            "合并逻辑仍内联在构建主流程里，无法被断言覆盖"
        src = open(os.path.join(os.path.dirname(__file__), "..", "..",
                                "build_daily_insight.py"), encoding="utf-8").read()
        assert src.count("_merge_vector_cache(") >= 2, \
            "_merge_vector_cache 只有定义没有调用点 ⇒ 判据锁的是死代码"

    def test_old_amputation_branch_is_gone(self):
        """`budget < 100 → 100` 这一支必须整体消失，不能只是被绕过。"""
        src = open(os.path.join(os.path.dirname(__file__), "..", "..",
                                "build_daily_insight.py"), encoding="utf-8").read()
        assert "if budget < 100:" not in src, \
            "旧兜底仍在：非RSS 撑满时 RSS 会被钉死在 100 条"
        assert "rss_mc[:budget]" not in src, "旧的 RSS 单支截断仍在"


class TestRssNotStarved:
    def test_rss_survives_a_crowded_non_rss_pool(self):
        """本判据就是今天那个故障的最小复现：12,244 RSS + 33,697 非RSS。"""
        old = [_mk("hot", i, 1) for i in range(33697)]
        new = [_mk("rss", i, 1) for i in range(12244)]
        merged, st = B._merge_vector_cache(old, new)
        rss, other = _split(merged)
        assert len(merged) <= B.MAX_EMBED_CHUNKS, \
            "封顶没生效：合并后 %d 条 > 上限 %d" % (len(merged), B.MAX_EMBED_CHUNKS)
        assert len(rss) > 1000, (
            "RSS 只剩 %d 条 —— 与今天的 100 条同一种饥饿，非RSS 撑满时 RSS 必须按新鲜度保住份额"
            % len(rss))

    def test_cap_is_enforced_even_when_non_rss_exceeds_it(self):
        old = [_mk("agihunt", i, 1) for i in range(40000)]
        new = [_mk("rss", i, 1) for i in range(500)]
        merged, st = B._merge_vector_cache(old, new)
        assert len(merged) == B.MAX_EMBED_CHUNKS, \
            "非RSS 超上限时结果应为恰好封顶，实际 %d" % len(merged)
        assert len(st.get("dropped_hashes") or []) > 0, "必须报告丢了哪些，否则淘汰不可核对"


class TestEvictionActuallyHappens:
    def test_stale_non_rss_is_evicted_and_counted(self):
        """造数必须越过阈值并自证机制动手了：只比键集合不算证明淘汰发生。"""
        stale = [_mk("hot", i, 30 * 24) for i in range(500)]      # 30 天前
        fresh = [_mk("hot", 900000 + i, 2) for i in range(500)]   # 2 小时前
        merged, st = B._merge_vector_cache(stale, fresh)
        n_other = len(_split(merged)[1])
        assert n_other == 500, (
            "陈旧非RSS 没被淘汰：合并后仍有 %d 条（应只剩 500 条新鲜的）" % n_other)
        assert st["evicted_stale"] >= 500, "evicted_stale 计数必须真实发生，实际 %s" % st.get("evicted_stale")

    def test_rss_window_is_the_168h_it_declares(self):
        """RSS 用 168h，不能悄悄跟非RSS 共用一个窗口。"""
        old_rss = [_mk("rss", i, 20 * 24) for i in range(300)]    # 20 天 > 168h
        fresh_rss = [_mk("rss", 800000 + i, 3) for i in range(50)]
        merged, st = B._merge_vector_cache(old_rss, fresh_rss)
        rss, _ = _split(merged)
        assert len(rss) == 50, "超 168h 的 RSS 应被淘汰，实际留下 %d 条" % len(rss)

    def test_undated_chunks_are_dropped_not_kept_forever(self):
        """无日期条目一律丢弃：留着就是当初"无日期回退成 now"那类永生条目的复活。"""
        undated = [_mk("hot", i, None) for i in range(40)]
        fresh = [_mk("rss", 700000 + i, 1) for i in range(10)]
        merged, st = B._merge_vector_cache(undated, fresh)
        assert all(c.get("pub_date") for c in merged), "合并结果里仍有无日期 chunk ⇒ 会永生"
        assert st.get("dropped_undated", 0) >= 40, \
            "判不了龄的数量必须单独计数上报，否则淘汰原因不可归因"


class TestDedupAndAlignment:
    def test_today_version_wins_over_stale_cache_copy(self):
        a_old = _mk("rss", 1, 5)
        a_old["title"] = "旧标题"
        a_new = _mk("rss", 1, 1)
        a_new["title"] = "新标题"
        merged, st = B._merge_vector_cache([a_old], [a_new])
        assert len(merged) == 1, "同一 content_hash 出现两次 ⇒ 去重没做"
        assert merged[0]["title"] == "新标题", "必须保留本场版本，不能保留旧缓存副本"

    def test_dropped_hashes_are_the_exact_complement(self):
        """淘汰清单要能与留存清单逐条对上，防止"统计说丢了、实际没丢"。"""
        old = [_mk("hot", i, 40 * 24 if i % 2 else 1) for i in range(200)]
        merged, st = B._merge_vector_cache(old, [])
        kept = {c["content_hash"] for c in merged}
        dropped = set(st["dropped_hashes"])
        assert not (kept & dropped), "同一 hash 既在留存又在淘汰 ⇒ 统计是编的"
        assert len(kept) + len(dropped) == 200, \
            "留存 %d + 淘汰 %d != 输入 200 ⇒ 有 chunk 静默消失" % (len(kept), len(dropped))

    def test_row_assembly_stays_aligned_after_eviction(self):
        """淘汰必须不破坏 chunk↔向量对齐：装配要按 content_hash 取行，不能按位置。

        这是改这个函数最容易出的事故 —— 一旦按位置切片，检索会拿错向量，
        而且**不会报错**（FAISS 只看形状），比现在的问题更隐蔽。
        """
        old = [_mk("hot", i, 30 * 24 if i < 100 else 1) for i in range(150)]
        merged, st = B._merge_vector_cache(old, [])
        kept = {c["content_hash"] for c in merged}
        assert len(kept) == len(merged) == 50
        # 装配出的向量数必须与留存 chunk 数严格相等
        vec_rows = [i for i, c in enumerate(old) if c["content_hash"] in kept]
        assert len(vec_rows) == len(merged), "向量行号与留存 chunk 数不等 ⇒ 会错位"
        assert all(old[i]["content_hash"] in kept for i in vec_rows), "行号指向了被淘汰的 chunk"


class TestNoSideStarved:
    """两个方向都要锁。只锁 RSS 会把偏见翻到另一边：本期 12 个事件 12/12 来自 agihunt，
    非RSS 一旦被清零，报告就直接退化成一个 RSS 摘要器。"""

    def test_minuscule_non_rss_side_is_not_rounded_away(self):
        rss = [_mk("rss", i, 1) for i in range(10000)]
        other = [_mk("hot", 1, 1)]
        merged, st = B._merge_vector_cache([], rss + other, cap=1000)
        assert st["kept_other"] == 1, (
            "非RSS 只有 1 条时被比例取整抹成 0 ⇒ 保底额没生效（kept_other=%d）"
            % st["kept_other"])
        assert len(merged) == 1000, "省下的名额必须回填给另一侧，实际留了 %d" % len(merged)

    def test_backfill_does_not_break_the_cap(self):
        rss = [_mk("rss", i, 1) for i in range(50)]
        other = [_mk("aihot", i, 1) for i in range(100000)]
        merged, st = B._merge_vector_cache([], rss + other, cap=30000)
        assert len(merged) == 30000, "回填后仍须严格封顶，实际 %d" % len(merged)
        assert st["kept_rss"] >= 1 and st["kept_other"] >= 1



class TestTrimOrder:
    def test_trim_under_pressure_keeps_the_newest(self):
        """名额不够时必须丢最旧的 —— 方向反过来（留最旧）在别的判据里看不出来。

        这条是推演变异体时补的：只断言"总数不超上限"或"淘汰计数>0"都抓不到排序反向，
        而反向的后果恰恰是池子塞满陈年旧文、本场新内容进不来，与今天的故障同形。
        """
        n = B.MAX_EMBED_CHUNKS + 8000
        # 全部落在 48h 窗口内（最大 40h），确保"少下来的那些"只能是上限截断造成的，
        # 不是超龄淘汰 —— 否则这条判据在测两件不同的事，失败时无法归因。
        old = [_mk("hot", i, 40.0 * i / n) for i in range(n)]
        merged, st = B._merge_vector_cache(old, [])
        assert len(merged) == B.MAX_EMBED_CHUNKS, \
            "留存 %d 条，应为恰好封顶 %d 条" % (len(merged), B.MAX_EMBED_CHUNKS)
        assert st["evicted_stale"] == 0, "本例不该触发超龄淘汰，实际 %d" % st["evicted_stale"]
        kept_age = [_age_h(c) for c in merged]
        dropped = set(st["dropped_hashes"])
        dropped_age = [40.0 * i / n for i in range(n) if ("hh_%06d" % i) in dropped]
        assert len(dropped_age) == n - B.MAX_EMBED_CHUNKS
        assert max(kept_age) < min(dropped_age), (
            "留存里最旧的（%.2fh）不比被淘汰里最新的（%.2fh）更新 ⇒ 截断方向反了"
            % (max(kept_age), min(dropped_age)))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
