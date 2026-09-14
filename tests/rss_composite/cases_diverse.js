/* tests/rss_composite/cases_diverse.js
   weightedShuffle() 断言用例 — TDD RED
   运行方式：由 test_diverse_js.py 拼接进 harness 后交给 node 执行。 */

var PASS = 0, FAIL = 0, FAILED_NAMES = [];

function eq(got, want, msg) {
  var ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) { PASS++; console.log('  ok   ' + msg); }
  else { FAIL++; FAILED_NAMES.push(msg); console.log('  FAIL ' + msg + '\n         got  = ' + JSON.stringify(got) + '\n         want = ' + JSON.stringify(want)); }
}
function ok(cond, msg) { eq(!!cond, true, msg); }
function it(name, fn) {
  try { fn(); } catch (e) { FAIL++; FAILED_NAMES.push(name); console.log('  FAIL ' + name + '\n         threw: ' + e.message); }
}

var _Q = {}; // quality map: source_key → score (0-100)

/* D1: 空数组不抛异常 */
it('D1 空数组返回空', function () {
  eq(weightedShuffle([], 120, _Q), [], 'D1 空输入 → 空输出');
});

/* D2: 单条原样返回 */
it('D2 单条原样返回', function () {
  var a = [{ t: 'only', date: '2026-09-14T10:00:00+08:00', sk: 'S1' }];
  var r = weightedShuffle(a, 120, _Q);
  eq(r.length, 1, 'D2 单条返回 1 篇');
  eq(r[0].t, 'only', 'D2 内容不变');
});

/* D3: 窗口=0 时退化为纯时间降序（不打散） */
it('D3 窗口=0 退化为时间降序', function () {
  var arts = [
    { t: 'old', date: '2026-09-14T08:00:00+08:00', sk: 'S1' },
    { t: 'new', date: '2026-09-14T12:00:00+08:00', sk: 'S2' },
    { t: 'mid', date: '2026-09-14T10:00:00+08:00', sk: 'S3' }
  ];
  var r = weightedShuffle(arts, 0, _Q);
  eq(r.map(function (a) { return a.t; }), ['new', 'mid', 'old'], 'D3 窗口=0 严格时间降序');
});

/* D4: 无日期条目沉底，不丢失 */
it('D4 无日期沉底不丢失', function () {
  var arts = [
    { t: 'nodate', date: null, sk: 'S1' },
    { t: 'dated', date: '2026-09-14T10:00:00+08:00', sk: 'S2' }
  ];
  var r = weightedShuffle(arts, 120, _Q);
  eq(r.length, 2, 'D4a 条目数守恒');
  eq(r[r.length - 1].t, 'nodate', 'D4b 无日期沉底');
});

/* D5: 同窗口内高信誉源有更高概率排在前面（统计测试：100 次中 ≥60 次 S-Hi 在 S-Lo 前） */
it('D5 高信誉源在同窗口内倾向靠前', function () {
  var qmap = { 'S-HI': 90, 'S-LO': 10 };
  var baseDate = '2026-09-14T10:00:00+08:00';
  var hiFirst = 0;
  for (var trial = 0; trial < 100; trial++) {
    var arts = [
      { t: 'lo', date: baseDate, sk: 'S-LO' },
      { t: 'hi', date: baseDate, sk: 'S-HI' }
    ];
    var r = weightedShuffle(arts, 120, qmap);
    if (r[0].t === 'hi') hiFirst++;
  }
  ok(hiFirst >= 60, 'D5 高信誉(90) vs 低信誉(10)：100 次中高信誉排首位 ≥60 次（实际 ' + hiFirst + '）');
});

/* D6: 不同窗口的文章不被打散（时序保持） */
it('D6 跨窗口不打散', function () {
  var arts = [
    { t: 'far-old', date: '2026-09-14T06:00:00+08:00', sk: 'S1' },
    { t: 'recent', date: '2026-09-14T12:00:00+08:00', sk: 'S2' }
  ];
  // 窗口 60 分钟，两条间隔 6h >> 60min → 各自独立窗口 → 按时间降序
  var r = weightedShuffle(arts, 60, _Q);
  eq(r.map(function (a) { return a.t; }), ['recent', 'far-old'], 'D6 跨窗口保持时间降序');
});

/* D7: 不修改入参数组（纯函数） */
it('D7 不修改入参', function () {
  var arts = [
    { t: 'a', date: '2026-09-14T10:00:00+08:00', sk: 'S1' },
    { t: 'b', date: '2026-09-14T11:00:00+08:00', sk: 'S2' }
  ];
  var orig = JSON.parse(JSON.stringify(arts));
  weightedShuffle(arts, 120, _Q);
  eq(arts.map(function (a) { return a.t; }), orig.map(function (a) { return a.t; }), 'D7 入参顺序不变');
});

/* D8: 确定性 — quality 全相等时，同输入同输出（不引入随机性） */
it('D8 quality 全相等时同输入同输出', function () {
  var qmap = { 'S1': 50, 'S2': 50, 'S3': 50 };
  var baseDate = '2026-09-14T10:00:00+08:00';
  var arts = [
    { t: 'a', date: baseDate, sk: 'S1' },
    { t: 'b', date: baseDate, sk: 'S2' },
    { t: 'c', date: baseDate, sk: 'S3' }
  ];
  var r1 = weightedShuffle(arts, 120, qmap).map(function (a) { return a.t; }).join(',');
  var r2 = weightedShuffle(arts, 120, qmap).map(function (a) { return a.t; }).join(',');
  eq(r1, r2, 'D8 两次调用结果一致（确定性）');
});

/* D9: quality 缺失的源按默认值 50 处理 */
it('D9 quality 缺失按默认值', function () {
  var arts = [
    { t: 'no-q', date: '2026-09-14T10:00:00+08:00', sk: 'UNKNOWN' },
    { t: 'has-q', date: '2026-09-14T10:00:00+08:00', sk: 'KNOWN' }
  ];
  var r = weightedShuffle(arts, 120, { 'KNOWN': 90 });
  eq(r.length, 2, 'D9 不丢条目');
});

/* D10: 条目总数守恒 */
it('D10 条目总数守恒', function () {
  var arts = [];
  for (var i = 0; i < 50; i++) {
    arts.push({ t: 'a' + i, date: '2026-09-14T10:00:00+08:00', sk: 'S' + (i % 5) });
  }
  var r = weightedShuffle(arts, 120, _Q);
  eq(r.length, 50, 'D10 50 条进 50 条出');
});

/* D11: applySort diverse 模式调用 weightedShuffle */
it('D11 applySort diverse 模式', function () {
  ART.length = 0;
  ART.push(
    { t: 'lo', sk: 'S-LO', date: '2026-09-14T10:00:00+08:00', ti: 2 },
    { t: 'hi', sk: 'S-HI', date: '2026-09-14T10:00:00+08:00', ti: 2 }
  );
  sortMode = 'diverse';
  ANALYSIS_DATA = { quality: { 'S-HI': 90, 'S-LO': 10 } };
  applySort();
  eq(ART.map(function (a) { return a.t; }).join(','), 'hi,lo', 'D11 diverse 模式高信誉靠前');
  sortMode = 'newest';
  ANALYSIS_DATA = null;
});

/* D12: diverse 模式条目守恒——打散不得丢篇 */
it('D12 diverse 模式条目守恒', function () {
  ART.length = 0;
  for (var i = 0; i < 20; i++) {
    ART.push({ t: 'a' + i, sk: 'S' + (i % 4), date: '2026-09-14T10:0' + (i % 10) + ':00+08:00', ti: 2 });
  }
  sortMode = 'diverse';
  ANALYSIS_DATA = { quality: { S0: 90, S1: 70, S2: 50, S3: 30 } };
  applySort();
  eq(ART.length, 20, 'D12 diverse 模式不丢条目');
  sortMode = 'newest';
  ANALYSIS_DATA = null;
});

/* D13: 窗口=0 必须与纯时间降序逐条一致（V2 的可执行形态） */
it('D13 窗口=0 与纯时间降序逐条一致', function () {
  var arts = [];
  for (var i = 0; i < 40; i++) {
    arts.push({
      t: 'a' + i,
      sk: 'S' + (i % 6),
      date: (i % 7 === 0) ? null : '2026-09-14T' + (10 + (i % 12)) + ':' + (i % 60) + ':00+08:00'
    });
  }
  var got = weightedShuffle(arts, 0, _Q).map(function (a) { return a.t; });
  var want = arts.slice().sort(function (a, b) { return _dateCmpDesc(a.date, b.date); })
                        .map(function (a) { return a.t; });
  eq(got, want, 'D13 窗口=0 输出 == 纯时间降序（含无日期沉底）');
});

/* D14: 任意窗口下条目集合守恒（打散不得吞掉或复制条目） */
it('D14 窗口内条目集合守恒', function () {
  var arts = [];
  for (var i = 0; i < 30; i++) {
    arts.push({ t: 'x' + i, sk: 'S' + (i % 3), date: '2026-09-14T10:' + (i % 50) + ':00+08:00' });
  }
  var got = weightedShuffle(arts, 120, { S0: 95, S1: 40, S2: 5 }).map(function (a) { return a.t; }).sort();
  var want = arts.map(function (a) { return a.t; }).sort();
  eq(got, want, 'D14 打散前后条目集合完全一致');
});

console.log('\nRESULT: ' + PASS + ' passed, ' + FAIL + ' failed');
if (FAIL) { console.log('FAILED: ' + FAILED_NAMES.join(' | ')); process.exit(1); }
process.exit(0);
