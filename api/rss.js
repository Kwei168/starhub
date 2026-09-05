// Vercel Serverless Function：API-First 实时 RSS 聚合
// GET /api/rss → 返回 JSON（服务端缓存 5 分钟）
// 页面加载时立即调用，获取全部源的最新内容
// 失败时回退到滚动缓存（上次成功抓取的数据）

import { readFileSync } from 'fs';
import { join } from 'path';
import { createHash } from 'crypto';

const FETCH_TIMEOUT = 5000;     // 单源超时 5s（从8s降低以加快失败速度）
const CONCURRENCY = 20;         // 20 路并发（从10提高到20以加快速度）
const CACHE_TTL = 5 * 60 * 1000;  // 服务端缓存 5 分钟
const UA = 'starhub-rss-aggregator/1.0';

// 滚动缓存：每个源保留上次成功抓取的数据
let rollingCache = new Map();  // key → { items, lastModified }
let fullCache = { t: 0, v: null };  // 完整响应缓存

// ── 加载 API 快照（构建时生成的 72h 累积数据） ──

function loadSnapshot() {
  try {
    const p = join(process.cwd(), 'rss_api_snapshot.json');
    const snap = JSON.parse(readFileSync(p, 'utf-8'));
    const total = (snap.sources || []).reduce((n, s) => n + (s.items || []).length, 0);
    console.log(`[rss] Loaded snapshot: ${(snap.sources || []).length} sources, ${total} items`);
    return snap;
  } catch (err) {
    console.log('[rss] Snapshot not found, falling back to live fetch');
    return null;
  }
}

// ── 加载翻译缓存 ──

function loadTransCache() {
  try {
    const p = join(process.cwd(), 'translations.json');
    const cache = JSON.parse(readFileSync(p, 'utf-8'));
    console.log(`[rss] Loaded ${Object.keys(cache).length} translation cache entries`);
    return cache;
  } catch (err) {
    console.log('[rss] Translation cache not found, using empty cache');
    return {};
  }
}

function md5(text) {
  return createHash('md5').update(text, 'utf-8').digest('hex');
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

const SAFE_TAGS = new Set(['p','br','img','a','b','i','em','strong','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','pre','code','figure','figcaption','table','tr','td','th','thead','tbody','span','div','hr','sup','sub','dl','dt','dd']);

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
  text = text.replace(/<iframe[^>]*>[\s\S]*?<\/iframe>/gi, '');
  text = text.replace(/<form[^>]*>[\s\S]*?<\/form>/gi, '');
  text = text.replace(/<[^>]+>/g, (match) => {
    const m = match.match(/^<\/?(\w[\w-]*)/);
    if (!m) return '';
    const tag = m[1].toLowerCase();
    if (!SAFE_TAGS.has(tag)) return '';
    const attrs = [];
    const attrRe = /([\w-]+)\s*=\s*"([^"]*)"/g;
    let am;
    while ((am = attrRe.exec(match)) !== null) {
      if (/^on/i.test(am[1])) continue;
      if (am[1].toLowerCase() === 'href' && am[2].trim().toLowerCase().startsWith('javascript:')) continue;
      attrs.push(am[1] + '="' + am[2] + '"');
    }
    const isClose = match.startsWith('</');
    if (attrs.length) return '<' + (isClose ? '/' : '') + tag + ' ' + attrs.join(' ') + '>';
    return isClose ? '</' + tag + '>' : '<' + tag + '>';
  });
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

function parseFeed(xml, sourceKey, maxItems) {
  const items = [];
  // Atom
  const atomEntries = xml.match(/<entry[^>]*>[\s\S]*?<\/entry>/gi) || [];
  if (atomEntries.length > 0) {
    for (const entry of atomEntries.slice(0, maxItems)) {
      const title = extractTag(entry, 'title');
      const link = extractAttr(entry, 'link', 'href') || extractTag(entry, 'link');
      const summary = extractTag(entry, 'summary') || extractTag(entry, 'content');
      const pubDate = extractTag(entry, 'published') || extractTag(entry, 'updated');
      if (title) {
        items.push({
          title: stripHtml(title),
          link: link || '#',
          summary: truncate(stripHtml(summary), 200),
          pub_date: pubDate || new Date().toISOString(),
        });
      }
    }
    return items;
  }
  // RSS
  const rssItems = xml.match(/<item[^>]*>[\s\S]*?<\/item>/gi) || [];
  for (const item of rssItems.slice(0, maxItems)) {
    const title = extractTag(item, 'title');
    const link = extractTag(item, 'link');
    const desc = extractTag(item, 'description') || '';
    const contentEncoded = extractTag(item, 'content:encoded') || '';
    const fullContent = contentEncoded.length > desc.length ? contentEncoded : '';
    const pubDate = extractTag(item, 'pubDate') || extractTag(item, 'dc:date');
    if (title) {
      const result = {
        title: stripHtml(title),
        link: link || '#',
        summary: truncate(stripHtml(desc || contentEncoded), 200),
        pub_date: pubDate || new Date().toISOString(),
      };
      if (fullContent) {
        result.fullContent = sanitizeHtml(fullContent).slice(0, 50000);
      }
      items.push(result);
    }
  }
  return items;
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
    const items = parseFeed(xml, source.key, 30);
    
    // 成功：更新滚动缓存
    const cached = {
      items: items.map(it => {
        const obj = {
          t: it.title,
          u: it.link,
          s: it.summary,
          d: it.pub_date,
        };
        if (it.fullContent) obj.fc = it.fullContent;
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
    const transCache = loadTransCache();  // 加载翻译缓存
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

    // T1 英文源实时翻译
    const t1EnKeys = new Set([
      'agihunt_0', 'openclaw_commits_14', 'hn_newest_56',
      'hn_ai_7', 'hackernews_6', 'hn_show_58',
      'arxiv_ai_4', 'arxiv_ml_5', 'arxiv_nlp_6',
    ]);
    const translateEndpoints = [
      (text) => `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=${encodeURIComponent(text.substring(0, 500))}`,
      (text) => `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text.substring(0, 500))}&langpair=en|zh-CN`,
      (text) => `https://translate.googleapis.com/translate_a/single?client=dict-chrome&sl=auto&tl=zh-CN&q=${encodeURIComponent(text.substring(0, 500))}`,
    ];

    async function translateText(text) {
      if (!text || !/[a-zA-Z]/.test(text)) return null;
      const hash = md5(text);
      if (transCache[hash]) return transCache[hash];
      for (const makeUrl of translateEndpoints) {
        try {
          const res = await fetch(makeUrl(text), { signal: AbortSignal.timeout(3000) });
          if (!res.ok) continue;
          const data = await res.json();
          let result = null;
          if (Array.isArray(data) && data[0]) {
            result = data[0].map(seg => seg[0]).join('');
          } else if (data && data.responseData) {
            result = data.responseData.translatedText;
          }
          if (result && result !== text) {
            transCache[hash] = result;
            return result;
          }
        } catch { /* try next endpoint */ }
      }
      return null;
    }

    // 翻译 T1 英文源的文章标题和摘要
    const translatePromises = [];
    for (const src of t1Results) {
      if (!t1EnKeys.has(src.key)) continue;
      for (const item of (src.items || [])) {
        if (item.t) translatePromises.push(translateText(item.t).then(r => { if (r) item.t = stripHtml(r); }));
        if (item.s) translatePromises.push(translateText(item.s).then(r => { if (r) item.s = stripHtml(r); }));
      }
    }
    await Promise.all(translatePromises);

    // 日期过滤：只保留最近 72 小时的文章
    const cutoff = new Date(now - 72 * 60 * 60 * 1000);
    const filterItems = (items) => (items || []).filter(item => {
      if (!item.d) return true;  // 无日期保留（快照数据可能缺日期）
      try { return new Date(item.d) >= cutoff; } catch { return false; }
    });

    // 合并 T1 实时 + T2/T3 快照
    const mergedSources = t1Results.map(src => ({
      key: src.key, name: src.name, cat: src.cat, color: src.color,
      tier: 1,
      items: filterItems(src.items).map(item => ({
        ...item,
        t: stripHtml(item.t || ''),
        s: truncate(stripHtml(item.s || ''), 200),
      })),
    })).concat(otherSources.map(src => {
      const snap = snapshotMap[src.key];
      return {
        key: src.key, name: src.name, cat: src.cat, color: src.color,
        tier: src.tier || 3,
        items: filterItems(snap ? snap.items : []).map(item => ({
          ...item,
          t: stripHtml(item.t || ''),
          s: truncate(stripHtml(item.s || ''), 200),
        })),
      };
    }));

    const response = {
      t: new Date().toISOString(),
      sources: mergedSources,
    };

    // 更新完整响应缓存
    fullCache = { t: now, v: response };

    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=300');
    res.setHeader('X-RSS-Cache', 'miss');
    return res.status(200).json(response);
  } catch (err) {
    console.error('[rss] Handler error:', err);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
