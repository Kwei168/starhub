// Vercel Serverless Function：API-First 实时 RSS 聚合
// GET /api/rss → 返回 JSON（服务端缓存 5 分钟）
// 页面加载时立即调用，获取全部源的最新内容
// 失败时回退到滚动缓存（上次成功抓取的数据）

import { readFileSync } from 'fs';
import { join } from 'path';

const FETCH_TIMEOUT = 5000;     // 单源超时 5s（从8s降低以加快失败速度）
const CONCURRENCY = 20;         // 20 路并发（从10提高到20以加快速度）
const CACHE_TTL = 5 * 60 * 1000;  // 服务端缓存 5 分钟
const BATCH_SIZE = 200;          // 分批刷新每批源数量（200源 × 20并发 ≈ 10s/批）
const UA = 'starhub-rss-aggregator/1.0';

// ── 运行时留存闸门 ──
// 规则在 lib/rss_retention.js，与构建期 build_rss_aggregator._apply_retention 同一套口径
// （基线 72h、按源发布间隔放宽到最多 168h、每源保底 3 条且保底也受 168h、判不了龄一律丢）。
// 为什么运行时也要过：?batch=N 与 ?source=KEY 是本函数自己发 HTTP 抓上游，完全不吃构建产物，
// 只裁构建产物会出现"页面刷新一下，4 年前的旧文整批回来"（2026-09-20 对抗审查 P0-2）。
// 加载失败绝不打断响应（宁可放过不可 500），但必须出声：打 ::warning 并在响应头留痕，
// 静默退化是本项目付过两次代价的形态。
let RETENTION = null;
let RETENTION_FAILED = false;   // 计算期异常也算降级，见 gateSources
try {
  RETENTION = require('../lib/rss_retention.js');
} catch (e) {
  console.error('[rss] 留存闸门模块加载失败:', e && e.message);
  console.log('::warning title=RSS 运行时留存闸门不可用::' + (e && e.message));
}

/** 响应头口径：装载失败或计算异常都必须显式露出来，不许静默当成"已过滤"。 */
function retentionHeader() {
  return (RETENTION && !RETENTION_FAILED) ? 'on' : 'unavailable';
}

/** 从**已加载**的快照对象建 URL→日期索引（等价于 Python 侧的 first_seen）。
 *  刻意不在这里 loadSnapshot()：快照有 ~80MB，每次 batch 请求多解析一遍会在
 *  serverless 内存上限下把端点自己打挂 —— 调用方手里已经有快照，必须由它传进来。 */
function buildDateIndex(snap) {
  const map = new Map();
  try {
    if (snap && snap.sources) {
      for (const s of snap.sources) {
        for (const it of (s.items || [])) {
          if (it.u && it.d && !map.has(it.u)) map.set(it.u, it.d);
        }
      }
    }
  } catch (e) { /* 快照结构异常时按"没有可核时间"处理，闸门会丢掉判不了龄的条目 */ }
  return map;
}

/** 源声明的 pub_date 时区偏移（rss_sources.json 的 pub_date_offset_min）。 */
function snapshotOffsets(sources) {
  const off = {};
  for (const s of (sources || [])) {
    if (s && s.key && s.pub_date_offset_min) off[s.key] = s.pub_date_offset_min;
  }
  return off;
}

/** 唯一的出口闸门调用：任何失败都降级为"不过闸"，绝不打断响应。
 *  注释承诺过"宁可放过不可 500"，所以 require 之外的计算异常也必须兜住
 *  （2026-09-20 对抗审查 P1-2：只兜 require 时，lib 抛异常会把 ?source 打成 500）。
 *  降级必须留痕：X-RSS-Retention: unavailable，别让它变成静默失效。 */
function gateSources(sources, sourcesMeta, knownDates) {
  if (!RETENTION) return sources;
  try {
    const res = RETENTION.applyRetention(sources, {
      nowMs: Date.now(),
      offsets: snapshotOffsets(sourcesMeta || []),
      knownDates: knownDates || null,
    });
    console.log(`[rss] 留存闸门: 进 ${res.stats.before} → 出 ${res.stats.after}`
      + `（判不了龄 ${res.stats.undatable}）`);
    return res.sources;
  } catch (e) {
    console.error('[rss] 留存闸门执行失败，本条响应未过闸:', e && e.message);
    RETENTION_FAILED = true;
    return sources;
  }
}

// 滚动缓存：每个源保留上次成功抓取的数据
let rollingCache = new Map();  // key → { items, lastModified }
let fullCache = { t: 0, v: null };  // 完整响应缓存

// ── 标题翻译（调用同项目 /api/translate，降级链：GTX → MyMemory → Agnes → Zen） ──
let transCache = new Map();  // text → translated（进程内缓存，避免重复调用）

function isChinese(text) {
  if (!text) return true;
  let cn = 0;
  for (const c of text) { if (c >= '\u4e00' && c <= '\u9fff') cn++; }
  return cn > text.length * 0.3;
}

function getTransBaseUrl() {
  // 优先用 VERCEL_URL 环境变量，回退到已知生产域名
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return 'https://starhub-refresh.vercel.app';
}

async function translateBatchViaApi(texts) {
  // 过滤已翻译和中文
  const pending = [];
  const results = new Array(texts.length);
  for (let i = 0; i < texts.length; i++) {
    const t = texts[i];
    if (!t || isChinese(t)) { results[i] = t; continue; }
    if (transCache.has(t)) { results[i] = transCache.get(t); continue; }
    pending.push(i);
  }
  if (pending.length === 0) return results;

  // 分批调用 /api/translate（MAX_TEXTS=20）
  const baseUrl = getTransBaseUrl();
  const MAX_BATCH = 20;
  for (let i = 0; i < pending.length; i += MAX_BATCH) {
    const chunk = pending.slice(i, i + MAX_BATCH);
    const chunkTexts = chunk.map(idx => texts[idx]);
    try {
      const r = await fetch(`${baseUrl}/api/translate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Origin': 'https://starhub-refresh.vercel.app' },
        body: JSON.stringify({ texts: chunkTexts, mode: 'bulk' }),
        signal: AbortSignal.timeout(30000),
      });
      if (r.ok) {
        const j = await r.json();
        if (j.translations) {
          for (let k = 0; k < chunk.length; k++) {
            const zh = j.translations[k] || texts[chunk[k]];
            results[chunk[k]] = zh;
            transCache.set(texts[chunk[k]], zh);
          }
          continue;
        }
      }
    } catch (e) {
      console.error('[rss] translate API call failed:', e.message);
    }
    // 翻译失败，保留原文
    for (const idx of chunk) { results[idx] = texts[idx]; }
  }
  return results;
}

async function translateTitlesForSources(formattedSources, snapshotTrans) {
  // 收集所有英文标题（去重），跳过快照中已有翻译的条目
  const titleSet = new Map();  // title → [items]
  let skipped = 0;
  for (const src of formattedSources) {
    for (const it of src.items) {
      const t = it.t || '';
      if (!t || isChinese(t)) continue;
      // 查快照翻译：同 URL 的条目在构建时已翻译 → 直接复用
      if (snapshotTrans) {
        const cached = snapshotTrans.get(it.u);
        if (cached && cached !== t) {
          it.t_zh = cached;
          skipped++;
          continue;
        }
      }
      if (!titleSet.has(t)) titleSet.set(t, []);
      titleSet.get(t).push(it);
    }
  }
  if (skipped > 0) console.log(`[rss] Snapshot reuse: ${skipped} titles already translated`);
  const uniqueTitles = [...titleSet.keys()];
  if (uniqueTitles.length === 0) return;
  console.log(`[rss] Translating ${uniqueTitles.length} new English titles via /api/translate`);

  const translated = await translateBatchViaApi(uniqueTitles);
  let count = 0;
  for (let i = 0; i < uniqueTitles.length; i++) {
    const zh = translated[i];
    if (zh && zh !== uniqueTitles[i]) {
      for (const it of titleSet.get(uniqueTitles[i])) {
        it.t_zh = zh;
      }
      count++;
    }
  }
  console.log(`[rss] Translation done: ${count}/${uniqueTitles.length} new titles translated`);
}

// ── 加载 API 快照（构建时生成的 72h 累积数据） ──

function loadSnapshot() {
  try {
    const p = join(process.cwd(), 'rss_api_snapshot.json');
    const snap = JSON.parse(readFileSync(p, 'utf-8'));
    const totalChunks = snap._total_chunks || 1;

    // 合并分块快照（rss_api_snapshot.json + rss_api_snapshot_1.json ...）
    if (totalChunks > 1) {
      for (let i = 1; i < totalChunks; i++) {
        try {
          const cp = join(process.cwd(), `rss_api_snapshot_${i}.json`);
          const cs = JSON.parse(readFileSync(cp, 'utf-8'));
          if (cs.sources && cs.sources.length) {
            snap.sources = snap.sources.concat(cs.sources);
          }
        } catch (e) {
          console.warn(`[rss] Failed to load snapshot chunk ${i}:`, e.message);
        }
      }
    }

    const total = (snap.sources || []).reduce((n, s) => n + (s.items || []).length, 0);
    console.log(`[rss] Loaded snapshot: ${(snap.sources || []).length} sources, ${total} items (${totalChunks} chunks)`);
    return snap;
  } catch (err) {
    console.log('[rss] Snapshot not found, falling back to live fetch');
    return null;
  }
}

// ── 加载源列表 ──

function loadSources() {
  const p = join(process.cwd(), 'rss_sources.json');
  return JSON.parse(readFileSync(p, 'utf-8'));
}

// ── 简易 XML 文本提取 ──

function extractTag(xml, tag) {
  const m = xml.match(new RegExp('<' + tag + '[^>]*>([\\s\\S]*?)</' + tag + '>', 'i'));
  return m ? m[1].trim() : '';
}

function extractAttr(xml, tag, attr) {
  const m = xml.match(new RegExp('<' + tag + '[^>]*\\s' + attr + '="([^"]*)"', 'i'));
  return m ? m[1] : '';
}

/** RSS <link> 缺失时认 <guid>；Atom 没有 guid，用 <id>。
 *  与 Python 侧 _parse_rss_item 同口径（台账 §20）：只接受 http(s) 且未显式
 *  isPermaLink="false" 的值。否则宁可为空 —— 一个看起来能点、点开 404 的链接
 *  比空链接更坏。 */
/** link 值归一：剥 CDATA 包装 + 解 HTML 实体 + 去首尾空白。
 *  Python 侧 `_parse_rss_item` 一直做这三步（html.unescape），JS 侧不做的后果是
 *  同一条链接在两条通道长得不一样 —— 线上实测 bbc_top_stories_592 / times_of_india_world_769 /
 *  der_spiegel_783 三个源 82 条 link 100% 畸形，而构建期产物 9,067 条零畸形。
 *  链接既决定卡片跳哪儿，也决定抽屉能不能认出"同一篇文章"。
 *  判据：tests/rss_history/test_parse_parity_js.py 的双跑对照。 */
function cleanLink(raw) {
  let s = String(raw == null ? '' : raw).trim();
  const cdata = s.match(/^<!\[CDATA\[([\s\S]*?)\]\]>$/);
  if (cdata) s = cdata[1].trim();
  // &amp; 放最后解，否则 `&amp;lt;` 会被二次解成 `<`（与 html.unescape 的单趟语义一致）
  s = s.replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
       .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
       .replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#39;/g, "'")
       .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
       .replace(/&amp;/g, '&');
  return s.trim();
}

function linkOrPermaId(block, linkTag, idTag) {
  const direct = cleanLink(extractTag(block, linkTag));
  if (direct && /^https?:\/\//i.test(direct)) return direct;
  const idTag2 = idTag || 'guid';
  const open = block.match(new RegExp('<' + idTag2 + '([^>]*)>', 'i'));
  if (!open) return direct || '';
  if (/\bisPermaLink\s*=\s*"false"/i.test(open[1])) return direct || '';
  const v = cleanLink(extractTag(block, idTag2));
  return /^https?:\/\//i.test(v) ? v : (direct || '');
}

/** 上游没给发布日期时的降级值 = 本次抓取时刻，并打 date_fallback 标记。
 *  前端据此显示「收录 …」，不冒充发布时间；缺了这个标记，卡片上的时间就是假的。 */
function datedOrCapture(pubDate) {
  if (pubDate && String(pubDate).trim()) return { pub_date: String(pubDate).trim(), date_fallback: false };
  return { pub_date: new Date().toISOString(), date_fallback: true };
}

function stripHtml(text) {
  if (!text) return '';
  return text
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/<!\[CDATA\[/g, '')
    .replace(/\]\]>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/&#\d+;/g, '')
    .replace(/&[a-z]+;/gi, '')
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/<[^>]*$/, '')   // 移除末尾未闭合的标签片段（如 <video src="..." controls="controls" webkit-playsin…）
    .replace(/\s+/g, ' ')
    .trim();
}

const SAFE_TAGS = new Set(['p','br','img','a','b','i','em','strong','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','pre','code','figure','figcaption','table','tr','td','th','thead','tbody','span','div','hr','sup','sub','dl','dt','dd','audio','video','source','iframe']);

// 允许的 iframe 域名（YouTube / Vimeo embed）
const SAFE_IFRAME_HOSTS = /youtube\.com|youtu\.be|vimeo\.com/i;

function sanitizeHtml(text) {
  if (!text) return '';
  text = text
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/<!\[CDATA\[/g, '')
    .replace(/\]\]>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  text = text.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  text = text.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  // 提取安全 iframe（YouTube / Vimeo），替换为占位符，清洗后还原
  const safeIframes = [];
  const safeIframeRe = /<iframe\s[^>]*src\s*=\s*"([^"]*(?:youtube\.com|youtu\.be|vimeo\.com)[^"]*)"[^>]*>\s*<\/iframe>/gi;
  text = text.replace(safeIframeRe, (match) => {
    safeIframes.push(match);
    return '\x00IFRAME' + (safeIframes.length - 1) + '\x00';
  });
  // 移除剩余非安全 iframe
  text = text.replace(/<iframe[^>]*>[\s\S]*?<\/iframe>/gi, '');
  text = text.replace(/<form[^>]*>[\s\S]*?<\/form>/gi, '');
  text = text.replace(/<[^>]+>/g, (match) => {
    const m = match.match(/^<\/?(\w[\w-]*)/);
    if (!m) return '';
    const tag = m[1].toLowerCase();
    if (!SAFE_TAGS.has(tag)) return '';
    // iframe 二次校验：仅放行 YouTube / Vimeo
    if (tag === 'iframe') {
      const srcMatch = match.match(/src\s*=\s*"([^"]*)"/i);
      if (!srcMatch || !SAFE_IFRAME_HOSTS.test(srcMatch[1])) return '';
    }
    const ALLOWED_ATTRS = {
      img: new Set(['src', 'alt']),
      a: new Set(['href']),
      iframe: new Set(['src', 'width', 'height', 'frameborder', 'allowfullscreen']),
      audio: new Set(['src', 'controls', 'preload']),
      video: new Set(['src', 'controls', 'preload', 'poster', 'width', 'height']),
      source: new Set(['src', 'type']),
    };
    const allowed = ALLOWED_ATTRS[tag] || null;
    const attrs = [];
    const attrRe = /([\w-]+)\s*=\s*"([^"]*)"/g;
    let am;
    while ((am = attrRe.exec(match)) !== null) {
      if (/^on/i.test(am[1])) continue;
      if (am[1].toLowerCase() === 'href' && am[2].trim().toLowerCase().startsWith('javascript:')) continue;
      if (allowed && !allowed.has(am[1].toLowerCase())) continue;
      attrs.push(am[1] + '="' + am[2] + '"');
    }
    // 布尔属性（如 controls）无 ="value"，单独检测
    if (tag === 'audio' || tag === 'video') {
      if (/\bcontrols(?:\s|>|\/)/i.test(match) && (!allowed || allowed.has('controls'))) {
        attrs.push('controls');
      }
    }
    const isClose = match.startsWith('</');
    if (attrs.length) return '<' + (isClose ? '/' : '') + tag + ' ' + attrs.join(' ') + '>';
    return isClose ? '</' + tag + '>' : '<' + tag + '>';
  });
  // 还原安全 iframe
  for (let i = 0; i < safeIframes.length; i++) {
    text = text.replace('\x00IFRAME' + i + '\x00', safeIframes[i]);
  }
  return text.trim();
}

// ── 深度清洗：移除 RSS 正文中的广告、推广、引导关注等噪音 ──

function deepCleanHtml(text) {
  if (!text) return '';
  // 1. 移除广告/推广/订阅/评论相关 class 或 id 的整个元素
  text = text.replace(/<(\w+)[^>]*\b(?:class|id)\s*=\s*"[^"]*\b(?:ad[s_-]?|advert|banner|sponsor|promo|newsletter|subscribe|social-share|share-buttons?|related-posts|recommend|widget|comments?|disqus|pagination|footer-links|follow-us|qrcode|qr-code)[^"]*"[^>]*>[\s\S]*?<\/\1>/gi, '');
  // 1.5 移除 wechat2rss / link-proxy 跳转链接（"跳转微信打开"等）
  text = text.replace(/<a[^>]*href="[^"]*(?:link-proxy|wechat2rss|mp\.weixin\.qq\.com)[^"]*"[^>]*>[^<]*<\/a>/gi, '');
  text = text.replace(/<a[^>]*>[^<]*\u8df3\u8f6c\u5fae\u4fe1[^<]*<\/a>/gi, '');
  // 2. 逐块检测：剥离内联标签后匹配推广模式
  const promoRe = /\u4ee3\u5f00\u5173\u6ce8|\u957f\u6309\u4e8c\u7ef4\u7801|\u626b\u7801\u5173\u6ce8|\u626b\u4e00\u626b\u5173\u6ce8|\u5fae\u4fe1\u641c\u7d22.*\u5173\u6ce8|\u5173\u6ce8\u516c\u4f17\u53f7|\u5173\u6ce8\u6211\u4eec|\u7acb\u5373\u8d2d\u4e70|\u70b9\u51fb\u9886\u53d6|\u70b9\u51fb\u6ce8\u518c|\u9650\u65f6\u4f18\u60e0|\u79d2\u6740\u6d3b\u52a8|\u52a0\u5165\u793e\u7fa4|\u52a0\u5165\u6211\u4eec|\u52fe\u9009\u5173\u6ce8|\u957f\u6309\u5173\u6ce8|\u8bc6\u522b\u4e8c\u7ef4\u7801|\u4e8c\u7ef4\u7801|\u957f\u6309\u8bc6\u522b|\u5173\u6ce8.*\u516c\u4f17\u53f7|\u5173\u6ce8.*\u5fae\u4fe1|\u70b9\u51fb.*\u8ba2\u9605|\u8ba2\u9605.*\u9891\u9053|\u8ba2\u9605.*\u90ae\u4ef6|\u52a0\u5165.*\u90ae\u4ef6\u5217\u8868|\u5fae\u535a.*\u5173\u6ce8|\u5173\u6ce8.*\u5fae\u535a|\u5206\u4eab.*\u597d\u53cb|\u8f6c\u53d1.*\u670b\u53cb|\u8f6c\u53d1.*\u5173\u6ce8|\u5173\u6ce8.*\u8f6c\u53d1|\u70b9\u8d5e.*\u5173\u6ce8|\u5173\u6ce8.*\u70b9\u8d5e|\u70b9\u8d5e.*\u5728\u770b|\u559c\u6b22.*\u5173\u6ce8|\u559c\u6b22.*\u70b9\u8d5e|\u89c9\u5f97.*\u5173\u6ce8|\u89c9\u5f97.*\u6709\u7528|\u7cbe\u5f69.*\u4e0d\u9519\u8fc7|\u8bf7\u957f\u6309|\u8bf7\u626b\u7801|\u70b9\u51fb\u539f\u6587|\u70b9\u51fb.*\u539f\u6587|\u70b9\u51fb.*\u67e5\u770b\u539f\u6587|buy now|subscribe\s+(?:now|today)|limited.?time|click here to|sign up (?:now|today)|special offer|discount code|use code|free trial|donate (?:now|today)|support us|follow us (?:on|for)|join our|share this (?:article|post)/i;
  text = text.replace(/<(p|div)\b[^>]*>[\s\S]*?<\/\1>/gi, (block) => {
    const plain = block.replace(/<[^>]+>/g, '');
    return promoRe.test(plain) ? '' : block;
  });
  // 3. 移除清洗后残留的空块元素
  text = text.replace(/<(?:p|div|span)\b[^>]*>\s*(?:<br\s*\/?>\s*)*<\/(?:p|div|span)>/gi, '');
  // 4. 压缩连续空行（保留段落间距）
  text = text.replace(/(?:\s*\n){3,}/g, '\n\n');
  return text.trim();
}

function truncate(text, maxLen) {
  if (!text) return '';
  text = text.trim();
  if (text.length <= maxLen) return text;
  const cut = text.slice(0, maxLen).lastIndexOf('。');
  return (cut > maxLen * 0.5 ? text.slice(0, cut + 1) : text.slice(0, maxLen)) + '…';
}

// ── Feed 解析 ──

function extractMediaFromEntry(entry) {
  // enclosure
  const encMatch = entry.match(/<enclosure[^>]*>/i);
  if (encMatch) {
    const typeM = encMatch[0].match(/type\s*=\s*"([^"]*)"/i);
    const urlM = encMatch[0].match(/url\s*=\s*"([^"]*)"/i);
    if (urlM && typeM) {
      const type = typeM[1].toLowerCase();
      if (type.startsWith('audio') || type.startsWith('video')) {
        return { media_url: urlM[1], media_type: type };
      }
    }
  }
  // media:content
  const mcMatch = entry.match(/<media:content[^>]*>/i);
  if (mcMatch) {
    const urlM = mcMatch[0].match(/url\s*=\s*"([^"]*)"/i);
    const medM = mcMatch[0].match(/medium\s*=\s*"([^"]*)"/i);
    if (urlM && medM && (medM[1] === 'audio' || medM[1] === 'video')) {
      return { media_url: urlM[1], media_type: medM[1] };
    }
  }
  return {};
}

function parseFeed(xml, sourceKey, maxItems) {
  const items = [];
  // Atom
  const atomEntries = xml.match(/<entry[^>]*>[\s\S]*?<\/entry>/gi) || [];
  if (atomEntries.length > 0) {
    for (const entry of atomEntries.slice(0, maxItems)) {
      const title = extractTag(entry, 'title');
      const link = cleanLink(extractAttr(entry, 'link', 'href')) || linkOrPermaId(entry, 'link', 'id');
      const summary = extractTag(entry, 'summary') || extractTag(entry, 'content');
      const pubDate = extractTag(entry, 'published') || extractTag(entry, 'updated');
      if (title) {
        const _dt = datedOrCapture(pubDate);
        const item = {
          title: stripHtml(title),
          link: link || '#',
          summary: truncate(stripHtml(summary), 200),
          pub_date: _dt.pub_date,
        };
        if (_dt.date_fallback) item.date_fallback = true;
        const media = extractMediaFromEntry(entry);
        if (media.media_url) { item.media_url = media.media_url; item.media_type = media.media_type; }
        items.push(item);
      }
    }
    return items;
  }
  // RSS
  const rssItems = xml.match(/<item[^>]*>[\s\S]*?<\/item>/gi) || [];
  for (const item of rssItems.slice(0, maxItems)) {
    const title = extractTag(item, 'title');
    const link = linkOrPermaId(item, 'link', 'guid');
    const desc = extractTag(item, 'description') || '';
    const contentEncoded = extractTag(item, 'content:encoded') || '';
    const fullContent = contentEncoded.length > desc.length ? contentEncoded : '';
    const pubDate = extractTag(item, 'pubDate') || extractTag(item, 'dc:date');
    if (title) {
      const _dt = datedOrCapture(pubDate);
      const result = {
        title: stripHtml(title),
        link: link || '#',
        summary: truncate(stripHtml(desc || contentEncoded), 200),
        pub_date: _dt.pub_date,
      };
      if (_dt.date_fallback) result.date_fallback = true;
      if (fullContent) {
        result.fullContent = deepCleanHtml(sanitizeHtml(fullContent)).slice(0, 50000);
      }
      // 提取 enclosure / media:content 中的音频视频
      const encMatch = item.match(/<enclosure[^>]*>/i);
      if (encMatch) {
        const typeM = encMatch[0].match(/type\s*=\s*"([^"]*)"/i);
        const urlM = encMatch[0].match(/url\s*=\s*"([^"]*)"/i);
        if (urlM && typeM) {
          const t = typeM[1].toLowerCase();
          if (t.startsWith('audio') || t.startsWith('video')) {
            result.media_url = urlM[1]; result.media_type = t;
          }
        }
      }
      items.push(result);
    }
  }
  return items;
}

// ── 单源内去重 ──

function dedupSourceItems(items, sourceKey) {
  if (!items || items.length < 2) return items;

  // Pass 1: URL 归一化
  for (const it of items) {
    let link = it.link || '';
    // V2EX: 剥离 #replyN
    if (sourceKey && sourceKey.includes('v2ex')) {
      link = link.replace(/#reply\d+$/, '');
    }
    // 通用: 剥离 tracking 参数
    link = link.replace(/[?&](utm_source|utm_medium|utm_campaign|utm_content|at_medium|at_campaign)=[^&]*/g, '');
    // 通用: 剥尾部 fragment（Python 侧同一条规则，负向前瞻保住 v2ex 的 #replyN 锚点）。
    // 漏它的线上代价：der_spiegel_783 的 30/30 条带 `#ref=rss`，与构建期产物里同一篇
    // 文章的链接不相等 ⇒ 抽屉按 link 认不出旧条目，"无损合并"退化成整条替换。
    link = link.replace(/#(?!reply\d+$)[^#]*$/, '');
    link = link.replace(/[?&]$/, '');
    it.link = link;
  }

  // Pass 2: 相同 URL 去重
  const seenUrls = new Set();
  items = items.filter(it => {
    const link = it.link || '';
    if (!link || seenUrls.has(link)) return false;
    seenUrls.add(link);
    return true;
  });

  // Pass 3: 内容去重
  const isWechat = items.slice(0, 5).some(it => (it.link || '').includes('mp.weixin.qq.com'));
  const normText = (t) => (t || '').replace(/\s+/g, '').toLowerCase().replace(/[^\w\u4e00-\u9fff]/g, '').slice(0, 80);
  const wechatBiz = (link) => {
    const m = (link || '').match(/__biz=([A-Za-z0-9=]+)/);
    return m ? m[1] : '';
  };

  if (isWechat) {
    // 微信策略：标题+摘要都相同才视为重复
    const seenContent = new Set();
    return items.filter(it => {
      const title = (it.title || '').trim();
      if (!title) return true;
      const summary = (it.summary || '').trim();
      const link = it.link || '';
      const dedupKey = wechatBiz(link) + '|' + normText(title) + '|' + normText(summary);
      if (seenContent.has(dedupKey)) return false;
      seenContent.add(dedupKey);
      return true;
    });
  } else {
    // 其他源：标题归一化去重（48h 窗口保护）
    const normTitle = (t) => (t || '').replace(/\s+/g, '').toLowerCase().replace(/[^\w\u4e00-\u9fff]/g, '').slice(0, 50);
    const seenTitles = new Map(); // key → pub_date
    return items.filter(it => {
      const title = (it.title || '').trim();
      if (!title) return true;
      const link = it.link || '';
      const pubDate = it.pub_date || '';
      const dedupKey = normTitle(title);

      if (seenTitles.has(dedupKey)) {
        const prevDate = seenTitles.get(dedupKey);
        if (pubDate && prevDate) {
          const pdCur = new Date(pubDate).getTime();
          const pdPrev = new Date(prevDate).getTime();
          if (!isNaN(pdCur) && !isNaN(pdPrev) && Math.abs(pdCur - pdPrev) > 48 * 3600 * 1000) {
            seenTitles.set(dedupKey, pubDate);
            return true;
          }
        }
        return false;
      }
      seenTitles.set(dedupKey, pubDate);
      return true;
    });
  }
}

// ── 单源抓取 ──

async function fetchOne(source) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT);
  
  try {
    const res = await fetch(source.url, {
      signal: ctrl.signal,
      headers: { 'User-Agent': UA, 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml' },
    });
    clearTimeout(timer);
    
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const xml = await res.text();
    let items = parseFeed(xml, source.key, 30);

    // 单源内去重：URL 归一化 + 标题重复检测
    items = dedupSourceItems(items, source.key);
    
    // 成功：更新滚动缓存
    const cached = {
      items: items.map(it => {
        const obj = {
          t: it.title,
          u: it.link,
          s: it.summary,
          d: it.pub_date,
        };
        // 无 pubDate 时 d 是抓取时刻（datedOrCapture 给的），必须带出降级标记，
        // 否则实时路径的卡片会把抓取时间当发布时间显示。键名沿用构建期快照的长名
        // date_fallback（前端 buildArt/_mergeRemoteSources 读的就是它），且只在真值时写。
        if (it.date_fallback) obj.date_fallback = 1;
        if (it.fullContent) obj.fc = it.fullContent;
        if (it.media_url) { obj.mu = it.media_url; obj.mt = it.media_type; }
        return obj;
      }),
      lastModified: new Date().toUTCString(),
    };
    rollingCache.set(source.key, cached);
    
    return {
      key: source.key,
      name: source.name,
      cat: source.cat,
      color: source.color,
      url: source.url,
      ...cached,
    };
  } catch (err) {
    clearTimeout(timer);
    console.error(`[rss] ${source.key} failed:`, err.message);
    
    // 失败：返回滚动缓存中的旧数据
    const cached = rollingCache.get(source.key);
    if (cached) {
      return {
        key: source.key,
        name: source.name,
        cat: source.cat,
        color: source.color,
        url: source.url,
        ...cached,
        _stale: true,  // 标记为旧数据
      };
    }
    
    // 无缓存：返回空
    return {
      key: source.key,
      name: source.name,
      cat: source.cat,
      color: source.color,
      url: source.url,
      items: [],
      lastModified: new Date().toUTCString(),
      _error: err.message,
    };
  }
}

// ── 并发控制 ──

async function fetchAllBatched(sources) {
  const results = [];
  for (let i = 0; i < sources.length; i += CONCURRENCY) {
    const batch = sources.slice(i, i + CONCURRENCY);
    const batchResults = await Promise.all(batch.map(fetchOne));
    results.push(...batchResults);
  }
  return results;
}

// ── Handler ──

export default async function handler(req, res) {
  // CORS 头：允许 GitHub Pages 跨域访问
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  // 处理 OPTIONS 预检请求
  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  // 轻量探测端点：仅返回快照总条数，供前端轮询检测新构建（避免整包拉取 15MB）
  if (req.query && req.query.meta === '1') {
    let metaTotal = 0;
    try {
      const snapMeta = loadSnapshot();
      if (snapMeta && snapMeta.sources) {
        metaTotal = snapMeta.sources.reduce((n, s) => n + (s.items || []).length, 0);
      }
    } catch (e) { /* 快照不可用时返回 0，前端不会触发合并 */ }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json({ total: metaTotal });
  }

  // ── 分批实时抓取端点：前端 refresh 时逐批拉取 T2/T3/T4 源 ──
  // GET /api/rss?batch=0  → 第 0 批（源 0-199）
  // GET /api/rss?batch=1  → 第 1 批（源 200-399）
  // GET /api/rss?batch_info=1 → 返回批次元信息（总批次数、源总数）
  if (req.query && req.query.batch_info === '1') {
    try {
      const sources = loadSources();
      const nonT1 = sources.filter(s => s.tier !== 1);
      const totalBatches = Math.ceil(nonT1.length / BATCH_SIZE);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      return res.status(200).json({
        totalSources: nonT1.length,
        batchSize: BATCH_SIZE,
        totalBatches: totalBatches,
      });
    } catch (err) {
      console.error('[rss] batch_info error:', err);
      return res.status(500).json({ error: 'Internal server error' });
    }
  }

  if (req.query && req.query.batch !== undefined) {
    try {
      const batchIdx = parseInt(req.query.batch, 10);
      if (isNaN(batchIdx) || batchIdx < 0) {
        return res.status(400).json({ error: 'invalid batch index' });
      }
      const sources = loadSources();
      const nonT1 = sources.filter(s => s.tier !== 1);
      const start = batchIdx * BATCH_SIZE;
      const end = Math.min(start + BATCH_SIZE, nonT1.length);
      if (start >= nonT1.length) {
        return res.status(404).json({ error: 'batch out of range' });
      }
      const batchSources = nonT1.slice(start, end);
      const totalBatches = Math.ceil(nonT1.length / BATCH_SIZE);
      console.log(`[rss] Batch ${batchIdx}/${totalBatches}: fetching ${batchSources.length} sources (${start}-${end - 1})`);

      const results = await fetchAllBatched(batchSources);

      // 快照只加载一次：既给闸门当"我方已见过该 URL"的时间索引（等价 Python 侧的 first_seen），
      // 也给标题翻译复用已译结果。loadSnapshot() 解析的是几十 MB 的分块快照，
      // 在同一次请求里加载两遍会在 serverless 内存上限下把端点自己打挂。
      let snapObj = null;
      try { snapObj = loadSnapshot(); } catch (e) { /* 快照不可用：闸门按"没有可核时间"处理 */ }
      const knownDates = buildDateIndex(snapObj);

      // 出口闸门：本端点完全不吃构建产物，不过闸就等于把 72h 契约绕过去了
      const gated = gateSources(results, batchSources, knownDates);

      // 快照翻译索引（URL → 已翻译标题），避免重复翻译构建时已翻译的条目
      let snapshotTrans = null;
      if (snapObj && snapObj.sources) {
        snapshotTrans = new Map();
        for (const src of snapObj.sources) {
          for (const it of (src.items || [])) {
            if (it.u && it.t) snapshotTrans.set(it.u, it.t);
          }
        }
      }

      // 格式化返回（与快照格式对齐）
      const formattedSources = gated.map(src => ({
        key: src.key,
        name: src.name,
        cat: src.cat,
        color: src.color,
        tier: nonT1.find(s => s.key === src.key)?.tier || 3,
        items: (src.items || []).map(it => ({
          t: stripHtml(it.t || ''),
          u: it.u || '#',
          s: truncate(stripHtml(it.s || ''), 200),
          d: it.d || '',
          // 与构建期快照同一键名、同一只在真值时写的形状；每源每条目都固定写 0 会白涨 payload。
          ...(it.date_fallback ? { date_fallback: 1 } : {}),
          fc: it.fc || '',
          img: it.img || '',
          mu: it.mu || '',
          mt: it.mt || '',
        })),
      }));

      const totalItems = formattedSources.reduce((n, s) => n + s.items.length, 0);
      console.log(`[rss] Batch ${batchIdx} done: ${formattedSources.length} sources, ${totalItems} items`);

      // 标题翻译：复用快照已有翻译，仅翻译构建后新发布的条目
      try {
        await translateTitlesForSources(formattedSources, snapshotTrans);
      } catch (e) {
        console.error('[rss] Title translation failed (non-fatal):', e.message);
      }

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      res.setHeader('X-RSS-Batch', `${batchIdx}/${totalBatches}`);
      res.setHeader('X-RSS-Retention', retentionHeader());
      return res.status(200).json({
        batch: batchIdx,
        totalBatches: totalBatches,
        sources: formattedSources,
      });
    } catch (err) {
      console.error('[rss] Batch fetch error:', err);
      return res.status(500).json({ error: 'Internal server error' });
    }
  }

  // 单源实时抓取端点：前端点开某个信源时调用，返回该源最新内容
  if (req.query && req.query.source) {
    try {
      const sources = loadSources();
      const src = sources.find(s => s.key === req.query.source);
      if (!src) {
        return res.status(404).json({ error: 'source not found' });
      }
      const result = await fetchOne(src);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      // 源键必须转义后再进响应头：Node 的 ServerResponse 只收 latin1，中文源键会抛
      // ERR_INVALID_CHAR，被外层 catch 变成 500 —— 生产实测 542/968 个源（键含中文）
      // 的抽屉实时刷新全部失效，而页面 fetch 的 .catch 把它静默吞成"刷新没反应"。
      res.setHeader('X-RSS-Single', encodeURIComponent(src.key));
      // 单源抽屉也是实时抓取出口：不过闸的话，点开一个停更源就能看到几年前的旧文。
      // knownDates 传 null：这里没有已加载的快照，为一次点击去解析几十 MB 不值得，
      // 代价是"上游没给日期且快照没见过"的条目在单源视图里会被判不了龄丢掉（墙侧仍按快照续命）。
      const [gatedOne] = result && result.items ? gateSources([result], [src], null) : [result];
      res.setHeader('X-RSS-Retention', retentionHeader());
      return res.status(200).json(gatedOne || result);
    } catch (err) {
      console.error('[rss] Single source error:', err);
      return res.status(500).json({ error: 'Internal server error' });
    }
  }

  const now = Date.now();
  const isRefresh = req.query && req.query.refresh === '1';
  
  // 检查完整响应缓存（refresh 时跳过缓存）
  if (fullCache.v && now - fullCache.t < CACHE_TTL && !isRefresh) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=300');
    res.setHeader('X-RSS-Cache', 'hit');
    return res.status(200).json(fullCache.v);
  }
  
  try {
    // 优先返回构建时生成的 API 快照（包含 72h 累积历史数据）
    if (!isRefresh) {
      const snapshot = loadSnapshot();
      if (snapshot && snapshot.sources && snapshot.sources.length > 0) {
        // 对快照数据做 HTML 清理（防御性）
        snapshot.sources = snapshot.sources.map(src => ({
          ...src,
          items: (src.items || []).map(item => ({
            ...item,
            t: stripHtml(item.t || ''),
            s: truncate(stripHtml(item.s || ''), 200),
          })),
        }));
        // 兜底翻译：构建时翻译失败（熔断/限流/超时）的英文标题，在快照服务时补翻
        // 已翻译的标题 t 已是中文 → isChinese 判定跳过；仅英文标题走 /api/translate
        try {
          await translateTitlesForSources(snapshot.sources, null);
        } catch (e) {
          console.error('[rss] Snapshot title translation failed (non-fatal):', e.message);
        }
        const total = snapshot.sources.reduce((n, s) => n + s.items.length, 0);
        console.log(`[rss] Serving snapshot: ${snapshot.sources.length} sources, ${total} items`);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.setHeader('Cache-Control', 'public, max-age=300');
        res.setHeader('X-RSS-Source', 'snapshot');
        return res.status(200).json(snapshot);
      }
    }
    
    // Fallback: 实时抓取 RSS（仅当快照不存在或 refresh=1 时）
    const sources = loadSources();
    const snapshot = loadSnapshot();
    const snapshotMap = {};
    if (snapshot && snapshot.sources) {
      for (const s of snapshot.sources) {
        snapshotMap[s.key] = s;
      }
    }

    // 分层：T1 实时抓取，T2/T3 从快照读取
    const t1Sources = sources.filter(s => s.tier === 1);
    const otherSources = sources.filter(s => s.tier !== 1);
    console.log(`[rss] T1 live fetch: ${t1Sources.length} sources, T2/T3 from snapshot: ${otherSources.length} sources`);

    const t1Results = await fetchAllBatched(t1Sources);

    // T1 英文源标题翻译（复用 batch 同一逻辑：/api/translate 降级链，只翻译标题）
    try {
      await translateTitlesForSources(t1Results);
    } catch (e) {
      console.error('[rss] T1 title translation failed (non-fatal):', e.message);
    }

    // 合并 T1 实时 + T2/T3 快照
    // （原先这里有个 filterItems 只做"72h + 无日期一律保留"，两道口子都补在闸门里：
    //   无日期不再无条件保留，超龄不再靠源自动放宽到永久）
    const mergedSources = t1Results.map(src => ({
      key: src.key, name: src.name, cat: src.cat, color: src.color,
      tier: 1,
      items: (src.items || []).map(item => ({
        ...item,
        t: stripHtml(item.t || ''),
        t_zh: item.t_zh || '',
        s: truncate(stripHtml(item.s || ''), 200),
      })),
    })).concat(otherSources.map(src => {
      const snap = snapshotMap[src.key];
      return {
        key: src.key, name: src.name, cat: src.cat, color: src.color,
        tier: src.tier || 3,
        items: (snap ? snap.items : []).map(item => ({
          ...item,
          t: stripHtml(item.t || ''),
          s: truncate(stripHtml(item.s || ''), 200),
        })),
      };
    }));

    // 出口闸门：refresh 走的是"实时 T1 + 快照 T2/T3"合并结果，同样必须过同一套规则
    const gatedMerged = gateSources(mergedSources, sources, buildDateIndex(snapshot));
    res.setHeader('X-RSS-Retention', retentionHeader());

    const response = {
      t: new Date().toISOString(),
      sources: gatedMerged,
    };

    // 更新完整响应缓存
    fullCache = { t: now, v: response };

    const liveItemCount = t1Results.reduce((n, s) => n + (s.items || []).length, 0);
    const snapItemCount = gatedMerged.reduce((n, s) => n + (s.items || []).length, 0);
    console.log(`[rss] Refresh merge: T1 live=${liveItemCount} items from ${t1Sources.length} sources, total merged=${snapItemCount} items`);

    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if(isRefresh) {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
      res.setHeader('X-RSS-Refresh', '1');
    } else {
      res.setHeader('Cache-Control', 'public, max-age=300');
    }
    res.setHeader('X-RSS-Cache', 'miss');
    return res.status(200).json(response);
  } catch (err) {
    console.error('[rss] Handler error:', err);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
