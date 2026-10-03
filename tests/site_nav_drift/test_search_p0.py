# -*- coding: utf-8 -*-
"""T6 搜索 P0 判据（A3 advisory）。

用 node 直接 import api/search.js 测 buildQueryPlan（真 ESM，打真 translate.js 的
模块加载面但不打网络——buildQueryPlan 是纯函数）。Python 只做驱动与断言收集。
钉住的行为：
- 单词中文 → ["zh" OR "en"]（与旧版一致）；
- 多词中文 → 第一档是逐词英文 AND **不加引号**（旧版整串引号短语是 0 结果根因）；
- 降级档齐全（短语兜底 → 仅英文主词 → 仅首中文词）；
- 翻译全失败（en=null）时档位退化为中文档，不产出 "null" 字符串；
- 限流常量与 429 出口存在；统一链 import 存在（对齐 §8.7）。"""
import json
import subprocess
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE_SCRIPT = r"""
import assert from 'node:assert';
const m = await import(new URL('file:///REPO/api/search.js').href);
const plan = m.buildQueryPlan;

// ① 多词中文（翻译成功）：第一档逐词英文 AND、不加引号
const p1 = plan('视频 创作', new Map([['视频','video'],['创作','creation']]));
assert.equal(p1[0], 'video creation', '多词第一档必须是不加引号的英文 AND，实得: ' + p1[0]);
assert.ok(p1.includes('"视频 创作" OR "video creation"'), '第二档短语兜底');
assert.ok(p1.includes('video'), '仅英文主词档');
assert.ok(p1.includes('视频'), '仅首中文词档');

// ② 单词中文：保持旧版 [zh OR en]
const p2 = plan('视频', new Map([['视频','video']]));
assert.deepEqual(p2, ['视频 OR video']);

// ③ 翻译全失败：退化中文档，不出 null/undefined
const p3 = plan('视频 创作', new Map([['视频',null],['创作',null]]));
assert.ok(p3.every(q => q && !/null|undefined/.test(q)), JSON.stringify(p3));

// ④ 纯英文多词：不翻译也必须以“逐词 AND（无引号）”为首档，短语只作降级档
const p4 = plan('rust cli', new Map());
assert.equal(p4[0], 'rust cli', '纯英文多词首档不许引号短语化: ' + p4[0]);
assert.ok(p4.includes('"rust cli"'), '短语只作降级档');

// ⑤ 统一链 import 与限流出口（源码面）
const fs = await import('node:fs');
const src = fs.readFileSync(new URL('file:///REPO/api/search.js'), 'utf8');
assert.ok(src.includes("from './translate.js'"), '必须复用 translate.js 统一链');
assert.ok(src.includes('429'), '限流 429 出口');
assert.ok(/RATE_IP = 10/.test(src) && /RATE_GLOBAL = 25/.test(src), '限流常量');
console.log('ALL_SEARCH_P0_OK');
""".replace('REPO', ROOT.replace('\\', '/'))


def test_build_query_plan_and_wiring():
    r = subprocess.run(['node', '--input-type=module', '-e', NODE_SCRIPT],
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    out = (r.stdout or '') + (r.stderr or '')
    assert 'ALL_SEARCH_P0_OK' in r.stdout, 'node 断言未通过:\n' + out[-2000:]
