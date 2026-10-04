# -*- coding: utf-8 -*-
"""T5 触发链与健康探活判据（A3 advisory）。

钉住四件事（v7 计划 Task 5）：
- refresh.js 的 mode 白名单分流：star → star-fast.yml、缺省 → update.yml，
  且 dispatch 必须发生在 X-Refresh-Key 校验之后（无头扫描器拿不到 key 就打不到 GH 配额）；
- api/health.js 只读探活：响应结构完整；「最近【成功】构建年龄」口径（status=success，
  不是最近 run——失败场不算活）；secrets 三项一律 Boolean 包装，payload 组装区
  不许出现 env 字符串拼接（泄密红线）；不健康返回 503（外部探活"非 2xx 告警"才抓得住静默退化）；
- update.yml 的 `Fetch stars & build` 步注入 GITHUB_TOKEN
  （fetch_and_build.py:1217 消费；缺失 = 小时场 stars 拉取全程匿名 60 req/h 配额）；
- vercel.json 为 health.js 声明 maxDuration（函数超时是部署契约的一部分）。
文本断言（不引 YAML/JS 解析依赖），离线自洽。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFRESH = os.path.join(ROOT, "api", "refresh.js")
HEALTH = os.path.join(ROOT, "api", "health.js")
UPDATE_YML = os.path.join(ROOT, ".github", "workflows", "update.yml")
VERCEL_JSON = os.path.join(ROOT, "vercel.json")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------- refresh.js 分流（已实现，这里钉住行为） ----------

def test_refresh_mode_whitelist_maps_star_to_star_fast():
    src = _read(REFRESH)
    m = re.search(r"WORKFLOW_BY_MODE\s*=\s*\{([^}]*)\}", src)
    assert m, "mode 白名单表必须存在（防任意 workflow 名注入）"
    table = m.group(1)
    assert re.search(r"star:\s*'star-fast\.yml'", table), "mode=star 必须分流到 star-fast.yml"
    assert re.search(r"''\s*:\s*'update\.yml'", table), "缺省必须分流到 update.yml"


def test_refresh_dispatch_after_key_check():
    src = _read(REFRESH)
    key_pos = src.find("keyValid")
    dispatch_pos = src.find("/dispatches")
    assert key_pos != -1 and dispatch_pos != -1
    assert key_pos < dispatch_pos, "dispatch 必须在 X-Refresh-Key 校验之后"


def test_refresh_dispatch_body_pins_ref_main():
    src = _read(REFRESH)
    assert re.search(r"JSON\.stringify\(\{\s*ref:\s*'main'\s*\}\)", src), "dispatch body 必须钉 ref=main"


def test_refresh_unknown_mode_is_400():
    src = _read(REFRESH)
    assert "未知 mode" in src and "400" in src, "白名单外的 mode 必须 400"


# ---------- api/health.js ----------

def test_health_exists_with_full_response_shape():
    src = _read(HEALTH)
    for key in ("ok", "last_build_age_minutes", "star_fast_age_minutes", "pages_ok"):
        assert key in src, "health 响应缺字段: %s" % key
    m = re.search(r"secrets\s*:\s*\{([^}]*)\}", src)
    assert m, "secrets 子对象必须存在"
    for k in ("agnes", "gh_token", "refresh_key"):
        assert k in m.group(1), "secrets 缺布尔项: %s" % k


def test_health_secrets_only_as_booleans():
    src = _read(HEALTH)
    # 取【真对象】而不是文件头注释里的示意形：secrets 块必须含 process.env 引用
    blocks = re.findall(r"secrets\s*:\s*\{([^}]*)\}", src)
    blocks = [b for b in blocks if "process.env" in b]
    assert blocks, "secrets 子对象（含 Boolean 探测）必须存在"
    block = blocks[0]
    for k in ("agnes", "gh_token", "refresh_key"):
        assert re.search(r"%s\s*:\s*Boolean\(" % k, block), "secrets.%s 必须 Boolean 包装" % k
    # 泄密红线：payload 组装区不许把 env 值拼进字符串（Boolean( 探测之外的原始引用）
    payload_zone = src[src.find("const payload"):] if "const payload" in src else src
    assert not re.search(r"[\"'`]\s*\+\s*process\.env\.|process\.env\.\w+\s*\+", payload_zone), \
        "payload 区出现 env 拼接——原始 secret 值可能进入响应"


def test_health_ages_are_last_success_not_last_run():
    src = _read(HEALTH)
    # workflow 名是参数（同一查询函数复用），钉"两个 workflow 都被查"+"成功口径"
    assert "/actions/workflows/" in src, "必须走 workflow runs API"
    assert re.search(r"lastSuccessAgeMinutes\(\s*'update\.yml'\s*\)", src), "必须查小时场 run"
    assert re.search(r"lastSuccessAgeMinutes\(\s*'star-fast\.yml'\s*\)", src), "必须查快车道 run"
    # 幻影读数复盘（2026-10-04 两次实锤，锚点都是 09-24T18:00Z=#1361）：
    # 服务端 status=success 过滤视图会间歇性停在 9 天前 ⇒ 必须【不过滤】拉最近
    # 30 场、客户端按 conclusion 挑最新 success——不信任服务端过滤索引。
    assert not re.search(r"set\(\s*'status'\s*,\s*'success'\s*\)", src), \
        "禁止服务端 status=success 过滤（幻影视图源头，两次实锤）"
    assert re.search(r"per_page'\s*,\s*'30'", src), "必须拉最近 30 场（覆盖 ≥24h，保证页内有 success）"
    assert re.search(r"conclusion\s*===?\s*'success'", src), "必须客户端按 conclusion 挑最新 success"
    assert "Authorization" in src, "runs 查询要带 token（匿名 60/h 会被探活自己烧穿）"


def test_health_pages_probe_rejects_placeholder_body():
    src = _read(HEALTH)
    assert "kwei168.github.io/starhub/index.html" in src, "pages 探活必须打真实首页"
    # 占位体 ~698B 假绿教训（HANDOFF §8.20）：只认 200 不够，必须卡最小体积
    assert "MIN_INDEX_BYTES" in src, "pages 判定必须含最小体积信号（防限流占位页假绿）"


def test_health_unhealthy_is_503_for_uptime_monitors():
    src = _read(HEALTH)
    assert "STALE_BUILD_MINUTES" in src, "ok 必须有新鲜度阈值（连续缺席才算不健康）"
    # 「非 2xx 告警」要抓住静默退化，前提是 ok 决定 200/503——且两条返回路径
    # （缓存重放 + 新计算）都必须走同一三元式，只改一处另一处会漏
    ternaries = re.findall(r"(?:cache\.ok|ok)\s*\?\s*200\s*:\s*503", src)
    assert len(ternaries) >= 2, \
        "缓存重放与新计算两条路径都必须 ok?200:503（恒 200 会让探活抓不住静默退化）"


def test_health_has_response_cache():
    src = _read(HEALTH)
    assert re.search(r"TTL", src), "探活结果必须有短缓存（防监控轮询烧 GH 配额）"


def test_health_get_only():
    src = _read(HEALTH)
    assert re.search(r"method\s*!==?\s*'GET'|'OPTIONS'", src), "health 只读：GET/OPTIONS 之外必须拒绝"


# ---------- update.yml build 步 token ----------

def _build_step_text():
    yml = _read(UPDATE_YML)
    i = yml.find("Fetch stars & build")
    assert i != -1, "update.yml 必须有 Fetch stars & build 步"
    nxt = yml.find("- name:", i + 1)
    return yml[i:nxt if nxt != -1 else len(yml)]


def test_update_build_step_injects_github_token():
    step = _build_step_text()
    assert re.search(r"GITHUB_TOKEN:\s*\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}", step), \
        "Fetch stars & build 必须注入 GITHUB_TOKEN（缺失 = 匿名 60 req/h）"


def test_update_build_step_keeps_id_and_run():
    step = _build_step_text()
    assert "id: build" in step, "build 步 id 不能动（后续步骤按 id 引用）"
    assert "python fetch_and_build.py $MODE" in step, "构建命令不能动"


# ---------- vercel.json ----------

def test_vercel_declares_health_max_duration():
    src = _read(VERCEL_JSON)
    m = re.search(r'"api/health\.js"\s*:\s*\{\s*"maxDuration"\s*:\s*(\d+)\s*\}', src)
    assert m, "health.js 必须在 vercel.json 声明 maxDuration"
    assert 10 <= int(m.group(1)) <= 60


# ---------- 翻译方向（T6 修正3）----------
# 线上实测（2026-10-04 00:2x）：search 拿 →中文 的链做 中→英，中文输入时 MyMemory
# langpair=zh-CN|zh-CN 返回错误文案 "PLEASE SELECT TWO DISTINCT LANGUAGES" 被当成功
# 译文缓存并组进 GitHub 查询串 ⇒ 全是无关仓库。链必须带方向，en 方向跳过硬编码
# "译成中文" 的 LLM 腿，MyMemory 必须拒收错误横幅。

TRANSLATE = os.path.join(ROOT, "api", "translate.js")


def test_translate_chain_takes_direction_param():
    src = _read(TRANSLATE)
    assert re.search(r"translateWithFallback\(\s*text\s*,\s*\{\s*to\s*=\s*'zh-CN'", src), \
        "统一链必须带 to 方向参数（默认 zh-CN 向后兼容）"
    assert "tl=zh-CN" not in src, "GTX 端点不得硬编码 tl=zh-CN（方向必须进 URL）"
    assert re.search(r"tl=\$\{to\}|tl=' \+ to", src), "GTX 的 target 必须用 to"
    assert "|${to}" in src or "|' + to" in src, "MyMemory langpair 的目标语言必须用 to"
    assert re.search(r"langpair=\$\{src\}\|\$\{to\}|langpair=\$\{src\}\|' \+ to", src)


def test_translate_cache_key_separates_direction():
    src = _read(TRANSLATE)
    assert re.search(r"\+\s*'\|'\s*\+\s*to|\`\|\$\{to\}", src), \
        "链内缓存键必须带方向维度——否则 en 译文会被 zh 请求命中（反向同理）"
    assert "zh-CN" in src, "默认方向必须是 zh-CN（rss/translate 既有行为零变化）"


def test_llm_legs_skipped_for_non_chinese_direction():
    src = _read(TRANSLATE)
    chain_start = src.find("async function translateWithFallback")
    assert chain_start != -1
    # 从链定义处起找【调用点】——find 全文会先命中文件前部的函数定义（锚错位的教训）
    agnes_leg = src.find("translateOne(text", chain_start)
    zen_leg = src.find("translateZen(text", chain_start)
    assert agnes_leg != -1 and zen_leg != -1, "链内必须有 Agnes/Zen 调用点"
    gate = "if (to === 'zh-CN')"
    assert src.rfind(gate, chain_start, agnes_leg) != -1, "Agnes 腿必须在 zh-CN 门内（prompt 硬编码译成中文）"
    assert src.rfind(gate, chain_start, zen_leg) != -1, "Zen 腿必须与 Agnes 同门"


def test_mymemory_rejects_error_banners():
    src = _read(TRANSLATE)
    # §8.17 教训：注释会喂假读数——先剥 // 注释行，横幅黑名单必须在【可执行代码】里
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))
    assert "responseStatus" in code, "MyMemory 必须查 responseStatus（200 才算成功）"
    assert re.search(r"PLEASE SELECT", code), \
        "错误横幅黑名单必须含 PLEASE SELECT（zh|zh 同语言实测返回）"


def test_search_requests_english_direction():
    src = _read(os.path.join(ROOT, "api", "search.js"))
    assert re.search(r"translateWithFallback\(\s*term\s*,\s*\{\s*to:\s*'en'\s*\}\)", src), \
        "search 必须显式请求 en 方向（默认链是 →中文 的）"
