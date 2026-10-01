# -*- coding: utf-8 -*-
"""冷启动回灌（修 批 5a 自己造成的伤害）：只在文件缺失时从钉住的 sha 取回历史副本。

背景（实测，2026-10-01）：批 5a 把 starhub-state 缓存的 path 从 7 条加到 10 条，
`actions/cache` 把 path 清单算进缓存身份 ⇒ 整族旧缓存瞬间不可达（
`Cache not found for input keys: starhub-state-Linux-...`），14:00 场 6 个状态文件 MISSING。
到 15:34 场虽然"文件都在盘上"，但尺寸塌了：
`hot_history` 8,278,933 → 47,073；`translations` 3,313,241 → 198,958；
`analysis_snapshot` 3,645,569 → 122,213；`daily_insight_history` 263,570 → 17,177；
`rss_trend_history` 1,153,325 → 1,980；`insight_tracking` 778,323 → 2,473。
这些是 append-only 历史与"每场只补新增"的译文缓存，**不会自愈**：趋势面板要重新积 7 天，
新到的英文标题/描述会被反复重译烧配额。

而全尺寸副本仍在 git 历史里（`8a48fa7878` 的 7 个 raw URL 实测 200 + 原始字节数）。
所以这里的修法刻意满足四条：
  ① 只在**缺失**时动作（`[ ! -f ]`），缓存正常时每场零开销；
  ② 只写工作目录 —— 绝不 `git add`/`git push`（否则又把冻结副本塞回库里，白做批 3）；
  ③ advisory（continue-on-error），取不到就当没这步，不许把部署冻住；
  ④ 位置必须在缓存 restore 之后、`Fetch stars & build` 之前 —— 早于 restore 会被缓存盖掉，
     晚于 build 则本场已经按冷启动跑完了。
暖起来之后这步应当摘掉（判据里钉着它，摘掉时记得同批删这条判据，别留孤儿判据）。
"""
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.environ.get("STARHUB_UPDATE_YML") or os.path.join(ROOT, ".github", "workflows", "update.yml")
STEP = "Seed cross-build state from history (cold-start repair)"
PINNED_SHA = os.environ.get("STARHUB_SEED_SHA") or "8a48fa7878"
SEED_FILES = ("hot_history.json", "analysis_snapshot.json", "translations.json",
              "rss_trend_history.json", "insight_tracking_history.jsonl",
              "daily_insight_tracking_history.jsonl", "daily_insight_history.json")


def _steps():
    with open(WF, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["jobs"]["update"]["steps"]


def _step():
    hits = [s for s in _steps() if (s.get("name") or "") == STEP]
    assert len(hits) == 1, "步骤 %r 命中 %d 个（应为 1）" % (STEP, len(hits))
    return hits[0]


def test_seed_step_exists_and_is_advisory():
    st = _step()
    assert st.get("continue-on-error") is True, (
        "回灌步必须 advisory：它只是补救，取不到不能把两次部署冻住")
    body = st.get("run") or ""
    assert body.strip(), "回灌步没有正文"


def test_seed_fetches_all_seven_only_when_they_are_shorter():
    """7 个都要覆盖，且必须"够长就不动"。

    实测教训：第一版守卫写成 `[ ! -f ]`（只在缺失时取），可 14:00 场的伤害形态不是"缺失"而是
    "都在盘上但塌了"（`hot_history` 8,278,933→47,073、`translations` 3,313,241→198,958）。
    那种守卫下一场也不会动 ⇒ 判据绿而问题没修，正是"代理信号绿≠事情做了"。
    所以现在的条件是本地字节数 < 历史副本的 Content-Length 才回灌。
    """
    body = _step().get("run") or ""
    missing = [f for f in SEED_FILES if f not in body]
    assert not missing, "回灌名单少了：%s" % missing
    looped = re.search(r"for f in ([^;]+); do", body)
    assert looped, "回灌应按名单循环，逐个硬写会让名单与状态族清单漂移"
    listed = looped.group(1).split()
    assert set(listed) == set(SEED_FILES), (
        "回灌名单与 7 个跨场状态不一致：多=%s 少=%s"
        % (sorted(set(listed) - set(SEED_FILES)), sorted(set(SEED_FILES) - set(listed))))
    assert re.search(r"content-length", body, re.I), (
        "必须先问历史副本有多大（HEAD/Content-Length），否则没法判断「本地是不是塌了」")
    assert re.search(r"-lt\b", body), (
        "必须有「本地字节 < 历史字节」的比较；只判存在性的守卫对本场的伤害形态一动不动")


def test_seed_is_one_shot_per_pinned_sha():
    """一次性的东西必须留下"已经做过"的凭据，否则每场都会拿旧副本盖住新数据。

    具体风险：`translations.json` 有 `TRANS_CACHE_MAX=30000` 的 LRU 裁剪，尺寸会在上限附近摆动；
    没有 marker 的话，"本地比历史小"会反复成立 ⇒ 每场把 12:58 那份旧译文请回来，
    译文缓存永远降不下去、也永远学不到新条目。marker 落在 `build_logs/` 里 ——
    那个目录已经在缓存 path 里，所以能跨场存活；
    **不能**为此往缓存名单里加新文件，改名单等于换族（批 5a 的学费）。
    """
    body = _step().get("run") or ""
    m = re.search(r"^\s*(\w+)\s*=\s*(\S*build_logs/\S*seed\S*)\s*$", body, re.M)
    assert m, (
        "没找到形如 `X=build_logs/<...>seed<...>` 的 marker 变量 —— 没有它这步就是每场重跑的常驻机制")
    var, path = m.group(1), m.group(2)
    assert body.count(var) >= 3, (
        "marker 变量 %s 只出现 %d 次：应当是「读取比较 / 早退 / 完成后写入」三处都用它"
        % (var, body.count(var)))
    assert path.startswith("build_logs/"), (
        "marker 落在 %s：它必须待在已经在缓存 path 里的目录里，否则跨不了场；"
        "而为此往缓存名单加新文件 = 换族（批 5a 的学费）" % path)
    assert re.search(r"cat[^\n]*" + re.escape("$" + var), body), "早退前没把 marker 读出来"
    assert re.search(r"\]\s*&&\s*\[\s*\"\$\(cat", body) or re.search(r"=\s*\"?\$SEED_SHA", body), (
        "读出来的 marker 必须与钉住的 sha 比较（`= \"$SEED_SHA\"`），否则早退分支不看内容")
    assert re.search(r"\"?\$SEED_SHA\"?\s*\]", body), "早退分支没跟钉住的 sha 比较"
    assert re.search(r"echo\s+\"?\$SEED_SHA\"?[^\n]*>\s*\"?\$" + var, body), (
        "回灌结束后没写 marker ⇒ 下一场还会再盖一次")
    assert "exit 0" in body, "早退要 exit 0（advisory 步也不该在已完成时白跑 7 次 HEAD）"


def test_seed_never_touches_git():
    """只写工作目录。任何 `git add`/`git commit`/`git push` 都会把冻结副本请回库里，白做批 3。"""
    body = _step().get("run") or ""
    for forbidden in ("git add", "git commit", "git push", "git checkout"):
        assert forbidden not in body, "回灌步里出现 %r" % forbidden
    assert "raw.githubusercontent.com" in body or "api.github.com" in body, (
        "回灌必须从历史取副本（raw/api 域名），否则它从哪拿数据？")
    assert PINNED_SHA in body, "没有钉住的 sha ⇒ 回灌目标会随 main 前进而漂移（批 3 之后就取不到了）"
    assert re.search(r"[0-9a-f]{8,40}", body), "钉的 sha 形状不对"


def test_seed_runs_after_restore_and_before_build():
    names = [s.get("name") for s in _steps()]
    assert STEP in names, "回灌步不在步骤序列里"
    i_restore = names.index("Restore cross-build state cache")
    i_build = names.index("Fetch stars & build")
    i_seed = names.index(STEP)
    assert i_restore < i_seed < i_build, (
        "顺序错了：restore(%d) < seed(%d) < build(%d) 才成立 —— 早于 restore 会被缓存盖掉，"
        "晚于 build 则本场已按冷启动跑完" % (i_restore, i_seed, i_build))


def test_seed_probe_is_not_vacuous():
    """反空转：把守卫/名单/顺序从正文里抽走后，抽取器必须报"什么都没有"，而不是假装齐全。

    没有这条，上面几条判据可能只是在一个空 `run` 上跑绿（本仓这类假绿已修过四轮）。
    """
    body = _step().get("run") or ""
    assert len(body) > 200, "正文只有 %d 字节，不足以完成 7 个文件的回灌" % len(body)
    assert body.count("curl") >= 1, "回灌要有真取数动作（curl/wget），实测没有"
    # 每个文件名的出现次数必须 ≥1，且 curl 目标里带 sha ⇒ 证明是"从那个提交取"，不是从 main 取
    assert PINNED_SHA in (body.split("raw.githubusercontent.com")[1][:200]
                          if "raw.githubusercontent.com" in body else ""), (
        "raw 地址后面看不到钉住的 sha ⇒ 可能是在取 main（main 上这些路径已经不存在）")
