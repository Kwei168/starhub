# -*- coding: utf-8 -*-
"""死路由判据：删掉恒为 0 的 /api/build_log，并保证删除本身不留尾巴。

为什么这个端点是死的（2026-10-01 实测，HANDOFF §10.17/§10.18）：
  `api/build_log.js:14` 读 `join(process.cwd(), 'build_logs')`，目录不存在就返回空；
  而 `build_logs/` 被 **两道**排除同时挡住 —— `.vercelignore:31` 与 update.yml 的 prune 步
  （`rm -rf ... build_logs docs`，在 `vercel --prod` 之前）⇒ 线上永远读不到数据：
  `?summary=1` 实测 `{"date":"2026-09-30","builds":0,...}`，无参实测 `{"total":0,"entries":[]}`；
  全仓前端（*.html / 生成脚本）**零引用**。
所以删函数 + 删 vercel.json 声明；日志本身照写（14 天轮转在跑，人要在 GitHub 上看）。

判据不只钉这一个文件，钉两条会长期防腐的不变量 —— 因为"删干净"最容易留下的正是这两种残渣：
  ① vercel.json 声明了某个 api 函数，但文件不存在（悬空声明：部署期报错或静默无效）
  ② 页面引用了某个 `/api/<名字>`，但 `api/<名字>.js` 不存在（用户点了才发现的死链）
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERCEL = os.path.join(ROOT, "vercel.json")
API_DIR = os.path.join(ROOT, "api")

# 已判定为死、且**禁止再被加回来**的路由：文件与 vercel.json 声明都不许出现。
# 删完不要把这里清空 —— 清空后这条判据就永不检查，等于自我注销（我差点这么写）。
# 只有当某天真的让端点可用（数据能读到 + 有前端调用方）时，才把它从这里移除。
DEAD_ROUTES = ["api/build_log.js"]

# 只认**同源**写法：引号/反引号/左括号后紧跟 /api/。
# 不这么收紧就会把 `https://aihot.example/api/v1/...` 这类外部 API 也算进来
# （我第一版就是这样，判据红在一堆与本题无关的 v1/s/query 上）。
API_REF_RE = re.compile(r"""['"`(]/api/([a-z0-9_-]+)""")


def _vercel_functions():
    return json.load(io.open(VERCEL, encoding="utf-8")).get("functions", {})


def test_dead_routes_are_really_gone():
    """死端点的函数文件与路由声明必须都不在。"""
    funcs = _vercel_functions()
    offenders = []
    for p in DEAD_ROUTES:
        if os.path.isfile(os.path.join(ROOT, p.replace("/", os.sep))):
            offenders.append("%s（文件还在）" % p)
        if p in funcs:
            offenders.append("%s（vercel.json 还声明着）" % p)
    assert not offenders, (
        "这些端点实测恒为 0 且零引用，却仍留在仓库/路由表里：%s" % ", ".join(offenders))


def test_no_dangling_vercel_function_declaration():
    """① vercel.json 声明的每个 api 函数都必须真的存在。"""
    missing = [k for k in _vercel_functions() if not os.path.isfile(os.path.join(ROOT, k.replace("/", os.sep)))]
    assert not missing, (
        "vercel.json 声明了不存在的函数（悬空声明）：%s" % ", ".join(missing))


def _api_refs_in_pages():
    """页面与其生成端里出现的 /api/<名字> 引用。"""
    refs = set()
    sources = []
    for name in ("index.html", "rss-aggregator.html", "ai-daily.html",
                 "daily-insight-history.html", "template.html"):
        p = os.path.join(ROOT, name)
        if os.path.isfile(p):
            sources.append((name, io.open(p, encoding="utf-8").read()))
    for name in ("build_rss_aggregator.py", "fetch_and_build.py", "build_ai_daily.py"):
        p = os.path.join(ROOT, name)
        if os.path.isfile(p):
            sources.append((name, io.open(p, encoding="utf-8").read()))
    for name, text in sources:
        for m in API_REF_RE.finditer(text):
            refs.add((m.group(1), name))
    return refs


def test_pages_never_reference_a_missing_api():
    """② 页面/生成端引用的每个 /api/<名字> 都必须有对应函数文件。

    这条同时兜住"我这次删端点会不会留下引用"：删之前它要是红，就说明还有人在调。
    """
    have = {f[:-3] for f in os.listdir(API_DIR) if f.endswith(".js")} if os.path.isdir(API_DIR) else set()
    dangling = sorted({(r, src) for r, src in _api_refs_in_pages()
                       if r not in have and r not in ("", )})
    assert not dangling, (
        "这些 /api/ 引用找不到对应函数（死链，用户点了才 404）：%s" % dangling[:8])
