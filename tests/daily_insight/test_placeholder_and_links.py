# -*- coding: utf-8 -*-
"""Task 1: [信息不足] 前缀匹配 + key_links 多样性校验。"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import build_daily_insight as bdi


class TestIsInsufficient:
    def test_exact_marker(self):
        assert bdi._is_insufficient("xx[信息不足]xx") is True

    def test_colon_variant(self):
        # LLM 实际输出 [信息不足：解释...]，旧 `'[]' in` 判断漏过（9/18 evt_004 实锤）
        assert bdi._is_insufficient("[信息不足：素材库中面板数据分属不同来源]") is True

    def test_normal_text(self):
        assert bdi._is_insufficient("OpenAI 发布了新模型") is False

    def test_none_safe(self):
        assert bdi._is_insufficient(None) is False


class TestValidateKeyLinks:
    def test_keeps_diverse_links(self):
        links = ["https://a.com/1", "https://b.com/2"]
        assert bdi._validate_key_links(links, []) == links

    def test_dedups_same_link(self):
        assert bdi._validate_key_links(["https://a.com/1", "https://a.com/1"], []) == ["https://a.com/1"]

    def test_all_identical_falls_back_to_item_urls(self):
        # 9/18 实锤：全事件 key_links 指向同一 AIHOT URL
        same = ["https://x.com/s"]
        items = [{"url": "https://r1.com/a"}, {"url": "https://r2.com/b"}, {"url": "https://x.com/s"}]
        out = bdi._validate_key_links(same, items)
        assert len(out) == 3 and "https://x.com/s" in out

    def test_empty_links_uses_items(self):
        out = bdi._validate_key_links([], [{"link": "https://i.com/1"}])
        assert out == ["https://i.com/1"]

    def test_capped_at_5(self):
        links = ["https://i.com/%d" % i for i in range(10)]
        assert len(bdi._validate_key_links(links, [])) == 5

    def test_url_variants_count_as_one(self):
        # 对抗审查 P2-8：仅协议/www/尾斜杠不同的同一 URL 不应算 2 个多样链接
        variants = ["http://a.com/x/", "https://www.a.com/x"]
        out = bdi._validate_key_links(variants, [{"url": "https://b.com/y"}])
        assert out == ["http://a.com/x/", "https://b.com/y"]
