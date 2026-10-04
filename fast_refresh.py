# -*- coding: utf-8 -*-
"""15 分钟新星快车道（SPEC 2026-10-02 §4-T3）。

只做四件事：拉 star（带 token）→ 与已知集合 diff → 新星分类/点评/翻译 →
重生成 index.html 并写回三缓存。RSS 聚合、每日洞察、Vercel 部署一概不碰
（那些留在 update.yml 的小时场）；不再触发 fetch_and_build.main。

设计约束（来自实施计划）：
- index.html 的 DATA 是全量内联 ⇒ 每场都用全量 repos 重组条目（assemble_entries 共用出口）；
  「新星」只决定 known_categories/known_notes/descriptions_zh 的增量写回与 CI 日志口径。
- 有新 star 才写回并让 CI 提交（避免 known_categories 的 git 增量被 15 分钟节奏放大，
  手册 §8.16 正为它的每场重写挂账）；无新星零文件写、零提交。
- 拉取失败：打 ::warning:: 后正常退出——上一版 Pages 制品继续在线，15 分钟后下一场重试；
  连续失败的断链由 /api/health 的 star_fast_age 报警（T5），这里不做重试风暴。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_and_build as fab  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
KC_PATH = os.path.join(ROOT, "known_categories.json")
NOTES_PATH = os.path.join(ROOT, "known_notes.json")
DESC_PATH = os.path.join(ROOT, "descriptions_zh.json")


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repos = fab.fetch_stars(token)
    if repos is None:
        print("::warning::[fast] 拉取 star 失败（限流/网络），本场跳过——线上保持上一版制品")
        return 0

    known = _load_json(KC_PATH, {})
    notes = _load_json(NOTES_PATH, {})
    desc_zh = _load_json(DESC_PATH, {})
    new_repos = [r for r in repos if r.get("full_name") and r["full_name"] not in known]
    if not new_repos:
        print("[fast] no change, skip write（%d 条，无新星）" % len(repos))
        return 0
    print("[fast] 新星 %d 条：%s" % (len(new_repos), ", ".join(r["full_name"] for r in new_repos[:8])))

    cat_label = {c["key"]: c["label"] for c in fab.CATS}
    out = fab.assemble_entries(repos, known, desc_zh, cat_label, token, notes=notes)
    # 提醒条必须与小时场同版：快车道只在有新星时重生成 index.html，这一版若缺块，
    # 页面上的提醒就会在"有新星"那场静默消失（两边共用 build_index_html，所以两处都得传）。
    attention_html = fab.render_star_attention(
        fab.star_attention_items(repos, known, notes, desc_zh))
    # 排行榜与 AI 摘要的回填源，就是浏览器读的同一个出口件（star-fast.yml 在生成整页之前
    # 把它 curl 回工作目录）。取不到时留空内联也不要紧——前端仍会 fetch 同一份文件，
    # 回填只是让首屏兜底也有数据，不是唯一通路。
    # 这里原先读的是 sidebar_snapshot.json：为同一目的另造的一份状态 + 一条缓存族，
    # 出口件落地后它既冗余又是单点（restore 不到 ⇒ 整页不发布），2026-10-04 拆掉。
    board = _load_json(os.path.join(ROOT, fab.TRENDING_BOARD), None) or {}
    html = fab.build_index_html(out, fab.CATS, trending=board.get("trending"),
                                ai_summary_html=board.get("ai_summary_html") or "",
                                attention_html=attention_html)
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # 新星点评沉淀（classify_repo 对老星查表命中 note=""，只有新星带点评）
    for e in out:
        if e.get("note") and not notes.get(e["full_name"]):
            notes[e["full_name"]] = e["note"]

    _atomic_write_json(KC_PATH, known)
    _atomic_write_json(NOTES_PATH, notes)
    _atomic_write_json(DESC_PATH, desc_zh)
    print("[fast] wrote %d（index.html 已重生成，缓存已写回，待 CI 提交）" % len(new_repos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
