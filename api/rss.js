// Vercel Serverless Function：API-First 实时 RSS 聚合
// GET /api/rss → 返回 JSON（服务端缓存 5 分钟）
// 页面加载时立即调用，获取全部源的最新内容
// 失败时回退到滚动缓存（上次成功抓取的数据）

import { readFileSync } from 'fs';
import { join } from 'path';

const FETCH_TIMEOUT = 8000;     // 单源超时 8s
const CONCURRENCY = 10;         // 10 路并发
const CACHE_TTL = 5 * 60 * 1000;  // 服务端缓存 5 分钟
const UA = 'starhub-rss-aggregator/1.0';

// 滚动缓存：每个源保留上次成功抓取的数据
let rollingCache = new Map();  // key → { items, lastModified }
let fullCache = { t: 0, v: null };  // 完整响应缓存

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
  return text
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .trim();
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
    const desc = extractTag(item, 'description') || extractTag(item, 'content:encoded');
    const pubDate = extractTag(item, 'pubDate') || extractTag(item, 'dc:date');
    if (title) {
      items.push({
        title: stripHtml(title),
        link: link || '#',
        summary: truncate(stripHtml(desc), 200),
        pub_date: pubDate || new Date().toISOString(),
      });
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
      items: items.map(it => ({
        t: it.title,
        u: it.link,
        s: it.summary,
        d: it.pub_date,
      })),
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
  const now = Date.now();
  
  // 检查完整响应缓存
  if (fullCache.v && now - fullCache.t < CACHE_TTL) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=300');
    res.setHeader('X-RSS-Cache', 'hit');
    return res.status(200).json(fullCache.v);
  }
  
  try {
    const sources = loadSources();
    console.log(`[rss] Fetching ${sources.length} sources...`);
    
    const results = await fetchAllBatched(sources);
    
    const response = {
      t: new Date().toISOString(),
      sources: results,
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
