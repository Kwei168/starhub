# -*- coding: utf-8 -*-
"""生成器解耦判据：非 star 数据的生成器不许挂在 `if stars_ok:` 下面。

起因（2026-10-01 17:00 场实测）：star API 限流时 `index.html` 与 `ai-daily.html` **当场不生成**，
而这两个页面已于 `7c08d02cea` 退出 git ⇒ 工作树没有兜底副本 ⇒ Stage Pages 步缺件后 `exit 1`
（且零输出）⇒ `Upload/Deploy Pages` 双双 skipped ⇒ 站点静默停在上一份产物，构建界面还是绿的。
AI 晨报的数据源是 AIHOT（自带 API→RSS→本地 json 三级回退），与 star 毫无关系；
RSS 聚合、每日洞察同理 ⇒ 它们本就不该被 star 拉取的成功与否门控。

打在**控制流归属**上（AST），不是 grep 字面量：把分支改名成 `if repos:` 也算违规，
所以判据按"是否存在以 `stars_ok` 为条件的 If 且其子树含该调用"来判，同时把
"调用必须还在（不许用删除调用的方式蒙绿）"钉成反向条件。
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAB = os.path.join(ROOT, "fetch_and_build.py")

# 这些生成器的输入与 GitHub star 数据无关，因此不许被 stars_ok 门控
NOT_STAR_GATED = (
    "build_ai_daily.main",           # AI 晨报：AIHOT API → RSS → ai_daily.json
    "build_rss_aggregator.main",     # RSS 聚合：自有信源与缓存
    "build_daily_insight.main",      # 每日洞察：自有语料
)
# index.html 是 star 数据的产物，允许（且应该）被门控 —— 但它必须仍在那里
STAR_GATED_ALLOWED = "build_trending"


def _src():
    with open(FAB, encoding="utf-8") as fh:
        return fh.read()


def _dotted(node):
    f = node.func
    if isinstance(f, ast.Attribute):
        base = f.value
        owner = getattr(base, "id", None) or getattr(getattr(base, "value", None), "id", "")
        return (owner + "." if owner else "") + f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _calls(tree):
    return [(_dotted(n), n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _stars_gated_lines(tree):
    """返回所有"位于某个以 stars_ok 为条件的 If 子树内"的行号集合。"""
    gated = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.If) and getattr(n.test, "id", None) == "stars_ok":
            for m in ast.walk(n):
                if hasattr(m, "lineno"):
                    gated.add(m.lineno)
    return gated


def test_star_unrelated_generators_are_not_gated_by_stars():
    tree = ast.parse(_src())
    gated = _stars_gated_lines(tree)
    hits = [(name, ln) for name, ln in _calls(tree) if name in NOT_STAR_GATED and ln in gated]
    assert not hits, (
        "这些与 star 无关的生成器仍挂在 if stars_ok: 下面（限流场就不生成产物，Pages 会静默不发）：%s"
        % (hits,))


def test_the_generators_still_exist_and_are_still_called():
    """反向护栏：不许靠"干脆不调用了"来让上一条变绿。"""
    tree = ast.parse(_src())
    got = {name for name, _ in _calls(tree)}
    missing = [n for n in NOT_STAR_GATED if n not in got]
    assert not missing, "生成器调用被删掉了（那不是解耦，是砍功能）：%s" % (missing,)
    assert STAR_GATED_ALLOWED in got, "star 数据生产者不见了 ⇒ 本判据的前提已变，需要重写"


def test_probe_bites_on_a_coupled_synthetic_case():
    """反空转：同一个检查器必须能抓出人工构造的耦合形状。"""
    coupled = (
        "def main():\n"
        "    stars_ok = False\n"
        "    if stars_ok:\n"
        "        try:\n"
        "            import build_ai_daily\n"
        "            build_ai_daily.main()\n"
        "        except Exception as e:\n"
        "            print(e)\n"
    )
    decoupled = (
        "def main():\n"
        "    stars_ok = False\n"
        "    if stars_ok:\n"
        "        build_trending()\n"
        "    try:\n"
        "        import build_ai_daily\n"
        "        build_ai_daily.main()\n"
        "    except Exception as e:\n"
        "        print(e)\n"
    )
    g1 = _stars_gated_lines(ast.parse(coupled))
    assert any(ln in g1 for name, ln in _calls(ast.parse(coupled)) if name == "build_ai_daily.main"), \
        "检查器抓不到构造出的耦合 ⇒ 主判据是恒绿的安慰剂"
    g2 = _stars_gated_lines(ast.parse(decoupled))
    assert all(ln not in g2 for name, ln in _calls(ast.parse(decoupled))
               if name == "build_ai_daily.main"), "检查器把已解耦的形状也报成违规"
