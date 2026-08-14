#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地开发工具：从现有 index.html 提取已注入的数据，重新渲染 template.html 生成 index.html。
仅用于本地预览模板改动；不参与 GitHub Actions 构建。"""
import json
import re

SRC = "index.html"
TPL = "template.html"

# (常量名, 模板占位符, 后继行前缀)：占位符名与常量名不同（__LANGS__/__FAVS__），
# 用后继常量行作截取边界，避免 JSON 内部分号误伤（DEFAULT_FAVS 后继是 STORE_KEY 非 UPDATED）
PAIRS = [
    ("DATA", "__DATA__", "const CATS"),
    ("CATS", "__CATS__", "const LANG_COLORS"),
    ("LANG_COLORS", "__LANGS__", "const DEFAULT_FAVS"),
    ("DEFAULT_FAVS", "__FAVS__", "const STORE_KEY"),
    ("UPDATED", "__UPDATED__", "const TRENDING"),
    ("TRENDING", "__TRENDING__", "const FEED"),
    ("FEED", "__FEED__", "\nconst $"),
]


# 常量名 → 模板占位符
PLACEHOLDER = {name: ph for name, ph, _ in PAIRS}


def main():
    src = open(SRC, encoding="utf-8").read()
    tpl = open(TPL, encoding="utf-8").read()
    for name, ph, nxt in PAIRS:
        pat = r"const %s = (.*?);\n%s" % (name, re.escape(nxt))
        m = re.search(pat, src, re.S)
        if not m:
            raise SystemExit("index.html 中未找到常量 %s" % name)
        raw = m.group(1)
        if name != "UPDATED":
            json.loads(raw)  # 校验数据完整（UPDATED 是带引号的字符串，跳过）
        if ph not in tpl:
            raise SystemExit("template.html 中缺少占位符 %s" % ph)
        tpl = tpl.replace(ph, raw)
    open(SRC, "w", encoding="utf-8").write(tpl)
    print("渲染完成：index.html 已由 template.html 重新生成")


if __name__ == "__main__":
    main()
