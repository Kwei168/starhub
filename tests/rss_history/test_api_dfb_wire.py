# -*- coding: utf-8 -*-
"""/api/rss 两条实时压缩出口必须带出「收录」标记（任务 #30，门禁 A2）。

现场：`api/rss.js:255-259` 的 `datedOrCapture()` 已经算出 `{pub_date, date_fallback:true}`，
`:425/:450` 也把它挂到条目上，但 `?source=KEY` 与 `?batch=N` 两条出口都把条目重写成
压缩对象（键 t/u/s/d），标记在这一步被丢掉 —— 于是实时路径的卡片仍把"抓取时刻"
当发布时间显示，前端无从区分。构建期快照走的是另一条路（build_rss_aggregator 写
`item["date_fallback"]`），所以只有这两条出口漏了。

线上传输键名沿用快照既有口径 **长名 `date_fallback`**（浏览器侧 `buildArt`/
`_mergeRemoteSources` 读的都是这个键），不引入新键名。

本文件不做文本断言：把 api/rss.js 转成 CJS、stub 掉 fetch、**真调 handler**，
检查响应体里的条目。两条出口各一条用例（少接一处必须红，见变异体记录）。
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GEN_REL = os.path.join("tests", "rss_js", "_rss_dfb_generated.cjs").replace("\\", "/")

DRIVER = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = process.argv[2];
const MODE = process.argv[3];          // 'source' | 'batch'
const WORK = process.argv[4];          // 作为 process.cwd() 的临时目录
const out = {};

// ── 1. 转 CJS，并把留存闸门指到绝对路径（生成的文件在 tests/ 下，相对 require 会指错目录）──
let src = fs.readFileSync(path.join(ROOT, 'api', 'rss.js'), 'utf8');
const before = src;
src = src.replace("import { readFileSync } from 'fs';", "const { readFileSync } = require('fs');");
src = src.replace("import { join } from 'path';", "const { join } = require('path');");
src = src.replace("export default async function handler", "module.exports = async function handler");
src = src.replace("require('../lib/rss_retention.js')", "require(process.env.STARHUB_RSS_LIB)");
if (src === before) { throw new Error('转译没生效：api/rss.js 的 import/export 写法变了'); }
if (src.indexOf("require(process.env.STARHUB_RSS_LIB)") < 0) {
  throw new Error('闸门 require 改写没生效：api/rss.js 的加载写法变了，测试探针已失效');
}
fs.writeFileSync(path.join(ROOT, '__GEN__'), src);

// ── 2. 假上游：一条带 pubDate、一条**不带** pubDate，绝不打网络 ──
const pub = new Date(Date.now() - 3600000).toUTCString();
const xml = '<?xml version="1.0" encoding="UTF-8"?>'
  + '<rss version="2.0"><channel><title>T</title>'
  + '<item><title>dated one</title><link>http://e/dated</link>'
  + '<pubDate>' + pub + '</pubDate><description>d</description></item>'
  + '<item><title>undated one</title><link>http://e/undated</link>'
  + '<description>d</description></item>'
  + '</channel></rss>';
global.fetch = async () => ({
  ok: true, status: 200,
  headers: { get: () => 'application/rss+xml' },
  text: async () => xml,
});

// loadSources()/loadSnapshot() 读的是 process.cwd()，所以用 WORK 目录放一份两源的清单，
// 既让 batch 出口只抓 2 个源（不必遍历 970 源），也不把判据绑在会变的真实源清单上。
fs.writeFileSync(path.join(WORK, 'rss_sources.json'), JSON.stringify([
  { key: 'dfa', name: 'A', cat: 'c', color: '#f00', url: 'http://up/a', tier: 3 },
  { key: 'dfb', name: 'B', cat: 'c', color: '#f00', url: 'http://up/b', tier: 3 },
]));

const handler = require(path.join(ROOT, '__GEN__'));
const res = {
  statusCode: 0, body: null, headers: {},
  status(c) { this.statusCode = c; return this; },
  json(b) { this.body = b; return this; },
  setHeader(k, v) { this.headers[k] = v; return this; },
};

(async () => {
  try {
    const query = MODE === 'batch' ? { batch: '0' } : { source: 'dfa' };
    await handler({ query: query, headers: {} }, res);
    out.status = res.statusCode;
    out.retentionHeader = res.headers['X-RSS-Retention'];
    let items = [];
    if (MODE === 'batch') {
      for (const s of (res.body && res.body.sources) || []) {
        items = items.concat((s.items || []).map(it => Object.assign({ _key: s.key }, it)));
      }
    } else {
      items = (res.body && res.body.items) || [];
    }
    out.byLink = {};
    for (const x of items) {
      out.byLink[x.u || x.link] = {
        d: x.d || x.pub_date || '',
        flag: (x.date_fallback === undefined ? null : x.date_fallback),
      };
    }
    out.keys = items.length ? Object.keys(items[0]) : [];
    out.count = items.length;
    out.ok = true;
  } catch (e) {
    out.reason = String(e && e.message);
  }
  process.stdout.write("RESULT:" + JSON.stringify(out) + String.fromCharCode(10));
})();
""".replace("__GEN__", GEN_REL)

GEN = os.path.join(ROOT, GEN_REL)


def _node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=20)
        return True
    except Exception:
        return False


def _run(mode, tmp_path):
    work = str(tmp_path).replace("\\", "/")
    drv = tmp_path / ("driver_%s.cjs" % mode)
    drv.write_text(DRIVER, encoding="utf-8")
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env["STARHUB_RSS_LIB"] = os.path.join(ROOT, "lib", "rss_retention.js").replace("\\", "/")
    try:
        r = subprocess.run(["node", str(drv), ROOT, mode, work], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=240, cwd=work, env=env)
        assert r.returncode == 0, "driver 跑挂: rc=%s %s %s" % (
            r.returncode, r.stdout[-400:], r.stderr[-400:])
        line = [l for l in r.stdout.splitlines() if l.startswith("RESULT:")]
        assert line, "没有结果行，stdout 前 400 字：%s stderr 前 400 字：%s" % (
            r.stdout[:400], r.stderr[:400])
        got = json.loads(line[-1][len("RESULT:"):])
        assert got.get("ok"), "handler 抛异常: %s" % got.get("reason")
        assert got["status"] == 200, got
        # 闸门必须真的在跑：装载失败时它会打印 unavailable，测试就会测到一条没过滤的路径
        assert got.get("retentionHeader") == "on", got
        return got
    finally:
        # 生成物不许留在工作树：CI 的 git add 按文件名匹配，脏文件可能被顺手提交
        if os.path.exists(GEN):
            os.remove(GEN)


def _assert_marker(got):
    und = got["byLink"].get("http://e/undated")
    den = got["byLink"].get("http://e/dated")
    assert und, "无日期条目没出现在响应里（它应靠收录时刻入窗）：%s" % list(got["byLink"])
    assert den, "带日期条目丢了：%s" % list(got["byLink"])
    assert und.get("flag"), (
        "无日期条目出网时没带 date_fallback ⇒ 前端把抓取时刻当发布时间显示；"
        "该条目键=%s" % got["keys"])
    assert not den.get("flag"), "带真实 pubDate 的条目被误标成收录"


@pytest.mark.skipif(not _node(), reason="本机没有 node（CI 上有）")
def test_single_source_wire_ships_the_capture_marker(tmp_path):
    """?source=KEY —— 抽屉实时抓取出口（fetchOne 的压缩映射）。"""
    _assert_marker(_run("source", tmp_path))


@pytest.mark.skipif(not _node(), reason="本机没有 node（CI 上有）")
def test_batch_wire_ships_the_capture_marker(tmp_path):
    """?batch=N —— 分批刷新出口（formattedSources 的压缩映射）。

    这条是独立的一处丢字段点：两处映射各自重写条目对象，只修一处必然另一处仍错。
    """
    _assert_marker(_run("batch", tmp_path))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
