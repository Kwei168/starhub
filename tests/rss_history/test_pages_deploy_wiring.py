"""Pages 发布接线的结构判据：大产物不得再进 git，且切换本身不得扩大公开面。

为什么钉这里而不是靠人记：仓库膨胀的唯一主因是每场把 55MB 的 rss-data-1.js 提交进 git
（实测远端全量历史 5.23 GiB，data-* 解包占 45.71 GB）。改由 Pages artifact 发布之后，
只要有人把分块加回 update.yml 的 add 清单，膨胀就静默回来，而构建照样绿。

被测文件路径可用 STARHUB_UPDATE_YML / STARHUB_VERCELIGNORE 覆盖，供变异体在副本上自证能红
（就地改 update.yml 会与推送互斥，见 feedback-mutation-push-mutex）。
"""
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.environ.get("STARHUB_UPDATE_YML") or os.path.join(ROOT, ".github", "workflows", "update.yml")
IGN = os.environ.get("STARHUB_VERCELIGNORE") or os.path.join(ROOT, ".vercelignore")

# 分块里除 chunk 0 以外的任何一个：rss-data-1.js / rss-data-2.js / …
_CHUNK_GT0 = re.compile(r"rss-data-([1-9]\d*)\.js")


def _doc():
    with open(WF, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _steps():
    job = _doc()["jobs"]["update"]
    names = [s.get("name", "") for s in job["steps"]]
    return names, job["steps"]


def _runs():
    """所有 run 脚本的 (步骤名, 正文) —— 判据统计在正文里，不在 YAML 结构里。"""
    return [(s.get("name", ""), s.get("run") or "") for s in _steps()[1] if s.get("run")]


def _add_lines():
    out = []
    for _, body in _runs():
        for line in body.splitlines():
            if re.match(r"\s*git add\b", line):
                out.append(line)
    return out


def _any_add_text():
    """所有出现过 `git add` 的行，含 `if [ -f x ]; then git add x; fi` 这种一行的条件式。

    _add_lines() 只认行首，条件式会从指缝里漏掉 —— 把 HTML 塞进 `if ... git add` 同样能
    把膨胀请回来，所以这条判据必须看见全部 git add。
    """
    out = []
    for _, body in _runs():
        out += [l for l in body.splitlines() if re.search(r"\bgit add\b", l)]
    return out


# 4 个纯产物页面：同场生成、无人跨场读回，退出 git 后由 staging 按名字从工作目录取。
_PAGE_HTML = ("index.html", "ai-daily.html", "rss-aggregator.html",
              "daily-insight-history.html")


def test_no_page_html_is_committed():
    """4 个页面 HTML 不许再进任何 git add（含条件式）。它们在 update.yml 里曾占约 3.8MB/场。"""
    lines = _any_add_text()
    assert lines, "没找到任何 git add 行（update.yml 结构变了，本判据失去意义）"
    for name in _PAGE_HTML:
        hits = [ln.strip() for ln in lines if re.search(r"(^|\s)%s(\s|$)" % re.escape(name), ln)]
        assert not hits, "%s 被加回提交清单，每场 %s 会重新攒进 git 历史：%s" % (
            name, name, hits[0][:160])


def test_pages_html_ship_from_workdir_not_from_git():
    """staging 必须按名字把 4 个页面从工作目录补进制品，不能只靠 `git ls-files`。

    它们已停止提交，main 上那份是过期副本：只按 git 清单取文件 = 把旧页面发上线；
    而存量清理要把这些过期副本从历史里剔除，届时它们连"被跟踪"都不是。
    """
    stage = [b for n, b in _runs() if n.startswith("Stage Pages site")]
    assert stage, "没有 staging 步骤"
    body = stage[0]
    loop = [ln for ln in body.splitlines()
            if re.match(r"\s*for f in .*html.*; do", ln)]
    assert loop, "staging 不再按名字补页面 HTML，git 里的过期副本会被发上线：%s" % body
    listed = loop[0]
    for name in _PAGE_HTML:
        assert name in listed, "%s 不在页面补入的名单里：%s" % (name, listed.strip())
    assert 'cp -f "$f" _pages/' in body, "页面补入的那步被改动，_pages 里不会有新鲜页面：%s" % body


def test_staging_refuses_empty_artifact():
    """空制品必须在 staging 就红，而不是发布出一个空站点。

    页面 HTML 出仓之后，这条是"生成器没跑出来 = 不发空站点"的唯一防线：缺哪一个都必须
    当场红，而不是让 deploy-pages 把缺文件的那一份当成新站点替换上去（= 死链）。
    """
    stage = [b for n, b in _runs() if n.startswith("Stage Pages site")]
    assert stage, "没有 staging 步骤"
    checks = re.findall(r"^\s*test -s (\S+)$", stage[0], re.M)
    for must in ("_pages/rss-data-0.js", "_pages/rss-data-1.js",
                 "_pages/rss-aggregator.html", "_pages/index.html",
                 "_pages/ai-daily.html", "_pages/daily-insight-history.html"):
        assert must in checks, "staging 缺少 %s 的非空断言，空制品会被当成功发布：%s" % (must, checks)


def test_no_big_chunk_is_committed():
    """提交清单里不许出现 chunk1 及以后的分块；chunk 0 必须还在（真实分块用例读它）。

    只禁字面 `rss-data-*.js` 是不够的：显式写 `rss-data-1.js` 同样把 55MB 塞回历史，
    而按文件名过滤行会让 `git add -A` 整条绕过判据 —— 两个洞都在这条里堵掉。
    """
    lines = _add_lines()
    assert lines, "没找到任何 git add 行（update.yml 结构变了，本判据失去意义）"
    for ln in lines:
        assert not re.search(r"git add\b[^\n]*\s(-A|\.)\b", ln), (
            "出现 git add -A/.：会把 _pages 暂存目录与全部未 ignore 文件一起提交：%s" % ln)
    joined = "\n".join(lines)
    assert "rss-data-*" not in joined, (
        "分块通配被加回提交清单，每场 55MB 会重新攒进 git 历史")
    hits = _CHUNK_GT0.findall(joined)
    assert not hits, "分块 chunk%s 被加回提交清单，每场 55MB 会重新攒进 git 历史" % ",".join(hits)
    assert any("rss-data-0.js" in ln for ln in lines), (
        "chunk 0 也不提交了，tests/rss_composite 的真实分块用例就读不到已入库数据")


def test_staging_takes_the_git_tree_not_the_worktree():
    """staging 必须按 `git ls-files` 取清单：legacy 发的是 git 树，照工作目录整拷会泄露缓存语料。

    工作目录里有 cache restore-keys 放回、被 .gitignore 排除的原始语料（实测本地合计 398M：
    rss_cache 110M / rss_history 62M / rss_api_snapshot 41M / daily_insight_* 146M），
    它们今天不在 Pages 上。整拷 ./ 等于这次切换顺手把它们公开发布。
    """
    stage = [b for n, b in _runs() if n.startswith("Stage Pages site")]
    assert stage, "没有 staging 步骤"
    body = stage[0]
    assert "git ls-files" in body, "staging 不再按 git 树取清单，会把 .gitignore 排除的缓存语料发布出去：%s" % body
    assert "--files-from" in body, "staging 没用 git ls-files 的清单喂 rsync：%s" % body
    assert "[._]" in body, "staging 不再剔除 `.`/`_` 开头文件，公开面会比今天变宽：%s" % body
    # 合法的 rsync 一定是被 git ls-files 的清单喂进去的；整拷 ./ 会带出被 ignore 的缓存语料
    for ln in [l for l in body.splitlines() if "rsync" in l]:
        assert "--files-from" in ln, "staging 又变成整拷工作目录：%s" % ln


def test_staging_never_copies_the_worktree_wholesale():
    """往 _pages 里拷文件只许按名字单拷；出现递归整拷就是把被 ignore 的语料公开发布。

    页面 HTML 出仓之后，staging 里多了两个"按名字补文件"的循环，这正是最容易顺手写成
    `cp -rf . _pages` 的地方 —— 而 rsync 那条判据看不见 cp。被 .gitignore 排除、由
    cache restore-keys 放回磁盘的语料（实测本地合计 398M）会第一次进 Pages。
    """
    stage = [b for n, b in _runs() if n.startswith("Stage Pages site")]
    assert stage, "没有 staging 步骤"
    bad = [ln.strip() for ln in stage[0].splitlines()
           if re.search(r"\bcp\s+(-[a-zA-Z]*[ra][a-zA-Z]*\s+|-r\b|-a\b)", ln)
           and '_pages' in ln and '--files-from' not in ln
           and not re.search(r'cp\s+-f\s+"\$f"\s+_pages/', ln)]
    assert not bad, "staging 里有递归整拷进 _pages 的写法，会把被 gitignore 的语料发布出去：%s" % bad


def test_chunks_ship_without_being_tracked():
    """分块必须按名字模式进制品，不能只靠 `git ls-files`。

    chunk1+ 自 2026-09-30 起不再提交，main 上那份是停在旧流程的过期副本：
    只按 git 清单取文件 = 把过期块发上线；而存量清理要把这些过期副本从历史里剔除，
    届时它们连"被跟踪"都不是，页面会直接少一块。
    """
    stage = [b for n, b in _runs() if n.startswith("Stage Pages site")]
    assert stage, "没有 staging 步骤"
    body = stage[0]
    assert re.search(r"for f in rss-data-\*\.js", body), (
        "staging 不再按模式补分块，剔除历史里的过期副本后页面会缺块：%s" % body)
    assert 'cp -f "$f" _pages/' in body, "模式补块的那步被改动，_pages 里不会有新鲜 chunk1：%s" % body


def test_pages_steps_present_and_cannot_block_vercel():
    """Pages 两步必须在，且排在 Vercel 之后 —— Pages 失败不许连坐 Vercel 部署。"""
    names, steps = _steps()
    assert any(n.startswith("Upload Pages artifact") for n in names), names
    assert any(n.startswith("Deploy to GitHub Pages") for n in names), names
    i_vercel = [i for i, n in enumerate(names) if n == "Deploy to Vercel"]
    i_pages = [i for i, n in enumerate(names) if n.startswith("Upload Pages artifact")]
    assert i_vercel and i_pages, "缺少 Vercel 或 Pages 步骤"
    assert i_pages[0] > i_vercel[0], "Pages 发布排到了 Vercel 之前，它一红就会跳过 Vercel 部署"
    deploy = [s for s in steps if (s.get("name") or "").startswith("Deploy to GitHub Pages")][0]
    assert "steps.pages_upload.outcome" in (deploy.get("if") or ""), (
        "deploy 步不检查 upload 结果，upload 失败照样跑 deploy：%s" % deploy.get("if"))


def test_upload_fails_on_empty_artifact():
    """actions/upload-pages-artifact 默认 if-no-files-found=warn —— 不显式设 error 就是空发布。"""
    _, steps = _steps()
    up = [s for s in steps if (s.get("name") or "").startswith("Upload Pages artifact")]
    assert up, "没有 upload 步骤"
    assert (up[0].get("with") or {}).get("if-no-files-found") == "error", up[0].get("with")


def test_staging_runs_before_prune():
    """staging 必须早于 prune：prune 会把大产物从工作目录删掉，晚一步制品就是空的。"""
    names, _ = _steps()
    i_stage = [i for i, n in enumerate(names) if n.startswith("Stage Pages site")]
    i_prune = [i for i, n in enumerate(names) if n.startswith("Prune large build artifacts")]
    assert i_stage and i_prune, "缺少 staging 或 prune 步骤"
    assert i_stage[0] < i_prune[0], "staging 跑在 prune 之后，Pages 制品里不会有大产物"


def test_pages_permissions_granted():
    perms = _doc()["permissions"]
    assert perms.get("pages") == "write", perms
    assert perms.get("id-token") == "write", "缺 id-token 时 deploy-pages 拿不到 OIDC 令牌"


def test_staging_cannot_block_vercel():
    """staging 排在 Vercel 之前（prune 会删产物，没得选），所以它必须不能连坐 Vercel。

    两条一起才成立：staging 设 continue-on-error（失败不阻断后续），
    同时 upload 依赖 steps.stage.outcome（否则残缺的 _pages 会被照常发布，站点半坏）。
    """
    _, steps = _steps()
    names = [s.get("name", "") for s in steps]
    i_vercel = names.index("Deploy to Vercel")
    stage = [s for s in steps if (s.get("name") or "").startswith("Stage Pages site")][0]
    assert stage.get("continue-on-error") is True, (
        "staging 排在 Vercel 之前却没有 continue-on-error，它一红就跳过 Vercel 部署")
    assert stage.get("id"), "staging 没有 id，后面的 if 无法引用它的 outcome"
    i_stage = names.index(stage.get("name"))
    assert i_stage < i_vercel, "staging 必须在 prune/Vercel 之前，否则制品里没有大产物"
    up = [s for s in steps if (s.get("name") or "").startswith("Upload Pages artifact")][0]
    assert "steps.%s.outcome" % stage["id"] in (up.get("if") or ""), (
        "upload 不检查 staging 结果，残缺制品会被发布：%s" % up.get("if"))


def test_staging_dir_is_hidden_from_vercel():
    """_pages/ 必须在 .vercelignore 里：它是产物的全量副本，且活到 Vercel 部署那一步。

    prune 步骤删掉的正是那些大文件，但 staging 跑在 prune 之前，副本已经落进 _pages ——
    少了这一行 ignore，prune 的体积保护等于没做，会重新撞上它注释里写的上传超限。
    """
    with open(IGN, encoding="utf-8") as fh:
        lines = [l.strip() for l in fh if not l.strip().startswith("#")]
    assert "_pages/" in lines or "_pages" in lines, (
        ".vercelignore 里没有 _pages/，Vercel 会把 Pages 暂存目录整个打包：%s" % lines)
