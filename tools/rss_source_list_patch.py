"""RSS 源清单变更的可重放补丁：按 key 删、按 key 改址、补缺失源。

为什么是脚本而不是一份最终文件：2026-09-20 与「72h 留存」改造并行，对方以已推远端的
版本为基线也在改 rss_sources.json。整文件覆盖会把对方对清单的增删静默抹掉，
所以这里只声明「对哪些 key 做什么」，在任何版本的清单上重放一遍即可。

幂等：目标 key 不存在（已被删/已改过）时只报告，不报错。
用法：python tools/rss_source_list_patch.py [--apply]   默认只 dry-run
"""
import json
import os
import sys

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "rss_sources.json")

# 已确认彻底失效或字面重复的源（依据见 docs/superpowers/plans/2026-09-20-rss-coverage-fix-pending-push.md）
DELETE_KEYS = {
    "cs_cl_updates_on_arxiv_org_599",   # 与 arXiv NLP 同一 feed（export 旧址）
    "cs_lg_updates_on_arxiv_org_740",   # 与 arXiv 机器学习 同一 feed
    "唐巧博客_28",                        # 与「唐巧的博客」同一 atom.xml
    "卫诗婕商业漫谈_6",                    # URL 与另一条字面全同
}
DELETE_BY_NAME = {
    # name: url 必须包含的子串（None = 不校验）
    "Codrops": None,                     # HTTP 410 Gone
    "Reuters World": None,               # 404，reutersagency.com 已废弃
    "謝懿Shine": None,                   # 域名停放页
    "FreeBuf 网络安全行业门户": None,        # 阿里云 WAF 滑块，无可用替代
    "AP News": None,                     # Cloudflare 全站挑战
    "CISA": None,                        # Akamai 拒所有 .xml
    "LlamaIndex Blog": None,             # 官方 RSS 已下线
    "MongoDB Blog": None,                # 官方 feed 404，Medium 镜像非官方域
    "FireCrawl Blog": None,              # api.bestblogs.dev 恒 0 条、从未产出
    "Groq": None,                        # 同上
    "Hugging Face": "wechat2rss",        # 桥接返回 "feed not found"
    "ShowMeAI研究中心": "wechat2rss",
    "Thoughtworks洞见": "wechat2rss",
    "yikai 的摸鱼笔记": "wechat2rss",
    "开源服务指南": "wechat2rss",
    "青哥谈AI": "wechat2rss",
}

# 换址：保留 key（同一出版方，历史数据继续挂同一信源）
URL_FIX = {
    "grafana_labs_382": "https://grafana.com/blog/index.xml",
    "langchain_blog_378": "https://www.langchain.com/blog/rss.xml",
    "hf_daily_papers_803": "https://rsshub.bestblogs.dev/huggingface/daily-papers",
    "nikkei_rsshub_802": "https://rsshub.bestblogs.dev/nikkei/index",
    "arxiv_cs_14": "https://rss.arxiv.org/rss/cs",
    "cs_cv_updates_on_arxiv_org_739": "https://rss.arxiv.org/rss/cs.CV",
}
NAME_FIX = {"cs_cv_updates_on_arxiv_org_739": "arXiv 计算机视觉"}
# 按 UA 拦的源（CloudFront 对 Chrome 串 403、对 curl 串 200）
UA_FIX = {"engadget_667": "curl/8.5.0", "engadget_4": "curl/8.5.0"}
# RSSHub 实例迁移：按 url 后缀路由匹配，key 可能随清单变动
ROUTE_FIX = [("/xiaoyuzhou/podcast/5f22729f9504bbdb77253e46",
              "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5f22729f9504bbdb77253e46")]
ADD_SOURCES = [
    {"key": "rfi_cn_779", "name": "RFI 中文", "cat": "news", "color": "#8a6d1f",
     "url": "https://www.rfi.fr/cn/rss", "tier": 3},   # 顶替 France24 中文（其 feed 不存在）
]
DROP_THEN_ADD = {"france24_zh_779": "rfi_cn_779"}

# ───────────────── 2026-09-21 批次：逐条没有发布日期的源 ─────────────────
# 单独成批、可单独重放（--scope dateless）。理由：远端 rss_sources.json 至今仍是
# **没打过任何补丁的 1005 条**（上面那些删除/改址只存在于本地提交里，工具文件本身
# 也从没进远端），把两批混推等于让一批 09-20 的旧判定跟着今天的实测一起落地。
# 旧判定确实会过期：caixin_latest_rsshub_806 当时记为"响应 0 字节的死源"，
# 今天重测是 20/20 条带 pubDate 的正常源。
DATELESS_DELETE_KEYS = {
    # 判据：修复 _RSS_DATE_RE（支持裸两位偏移 +08）之后重测，feed 里连日期元素都不存在
    # ⇒ 唯一的时钟只剩"首次抓到"，卡片上显示的日期必然是收录时间冒充发布时间。
    "nikkei_rsshub_802",      # 远端现行 rssforever 实例抓到 0 条；bestblogs 镜像 28 条、零日期
    "喷嚏网铂程斋_11",          # plink.anyfeeder 代理结构性丢日期：14 条仅 title/link/content
    "bbc英语教学_13",           # 同上：5 条
    "中国日报双语_2",            # 同上：5 条
    # 与 google_developers_blog_406 是同一家：地址只差一个结尾斜杠，逐条零日期，
    # 出口 20 条卡片连时间位都是空的。_406 已换到逐条带 pubDate 的官方地址，
    # 这个重复钥匙留着只多一份空卡片和一次白抓。
    "google_dev_76",
}
# 内容质量类删除：**日期没问题**，纯粹是判定这个源的内容不值得占配额。
# 单独成块的原因：混进 DATELESS_DELETE_KEYS 等于在清单里留下一条假原因，
# 下一个人会以为超能网的 feed 缺日期，而它今天实测 30/30 带 pubDate。
QUALITY_DELETE_KEYS = {
    "超能网_31",               # 2026-09-21 用户判定"内容质量不行"
}

DATED_URL_FIX = {
    # 这两个不是"上游不给日期"，是我们接的地址不给 —— 换址就保住内容，删掉是净损失。
    # 备选地址都过真实解析器复测：逐条 pub_date 命中 100%，且不是同一分钟的批次时间。
    "google_developers_blog_406": "https://blog.google/technology/developers/rss/",
    "美团技术团队_0": "https://tech.meituan.com/atom.xml",
}


def run(apply=False, scope="all"):
    src = json.load(open(PATH, encoding="utf-8"))
    n0 = len(src)
    log = []
    by_key = {s["key"]: s for s in src}

    # scope="dateless" 只重放 2026-09-21 这一批；其余改动留给各自的批次落地
    if scope == "all":
        del_keys = DELETE_KEYS | DATELESS_DELETE_KEYS | QUALITY_DELETE_KEYS
        del_names, drop_then_add = DELETE_BY_NAME, DROP_THEN_ADD
        url_fix = dict(URL_FIX)
        url_fix.update(DATED_URL_FIX)
        name_fix, ua_fix, route_fix, adds = NAME_FIX, UA_FIX, ROUTE_FIX, ADD_SOURCES
    elif scope == "dateless":
        del_keys = DATELESS_DELETE_KEYS | QUALITY_DELETE_KEYS
        del_names, drop_then_add = {}, {}
        url_fix, name_fix, ua_fix = dict(DATED_URL_FIX), {}, {}
        route_fix, adds = [], []
    else:
        raise SystemExit("未知 scope: %s" % scope)

    gone = [k for k in del_keys if k in by_key]
    for nm, frag in del_names.items():
        for s in src:
            if s["name"] == nm and (frag is None or frag in (s.get("url") or "")):
                gone.append(s["key"])
    for k in drop_then_add:
        if k in by_key:
            gone.append(k)
    gone = set(gone)
    declared = len(del_keys | set(del_names) | set(drop_then_add))
    src = [s for s in src if s["key"] not in gone]
    log.append("删除 %d 条（清单中已不存在的目标：%d）" % (len(gone), declared - len(gone)))

    changed = 0
    for s in src:
        k = s["key"]
        if k in url_fix and s.get("url") != url_fix[k]:
            s["url"] = url_fix[k]; changed += 1
        if k in name_fix and s.get("name") != name_fix[k]:
            s["name"] = name_fix[k]; changed += 1
        if k in ua_fix and s.get("ua") != ua_fix[k]:
            s["ua"] = ua_fix[k]; changed += 1
        for suffix, newurl in route_fix:
            if (s.get("url") or "").endswith(suffix) and s.get("url") != newurl:
                s["url"] = newurl; changed += 1
    log.append("改址/加字段 %d 处" % changed)

    have = {s["key"] for s in src}
    added = [s for s in adds if s["key"] not in have]
    src.extend(added)
    log.append("新增 %d 条" % len(added))

    keys = [s["key"] for s in src]
    assert len(keys) == len(set(keys)), "出现重复 key"
    for s in src:
        assert s.get("key") and s.get("name") and (s.get("url") or "").startswith("http"), s

    print(" | ".join(log))
    print("源数 %d -> %d%s" % (n0, len(src), "  （dry-run，未写盘）" if not apply else ""))
    # 只改址不改条数时也必须写盘：旧条件 len(src) != n0 会让纯 URL_FIX 的重放静默不落盘，
    # 于是"补丁已重放"成了假话 —— 清单与声明长期不一致正是这个工具要防的事。
    if apply and (len(src) != n0 or changed or added):
        with open(PATH, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(src, ensure_ascii=False, separators=(",", ":")))
        print("已写回 rss_sources.json")
    elif apply:
        print("无改动，不写盘")
    return len(src)


if __name__ == "__main__":
    run(apply="--apply" in sys.argv,
        scope="dateless" if "dateless" in sys.argv else "all")
