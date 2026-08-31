// Vercel Serverless Function：实时抓取 Top 10 RSS 源
// GET /api/rss → 返回 JSON（CDN 缓存 5 分钟）
// cron-job.org 每 5 分钟调用以预热缓存
// 前端页面加载时 fetch 此接口，用返回数据更新 Top 10 源内容

// Top 10 源选择标准：更新频率高、内容质量好、响应速度快、国内可访问
const TOP_SOURCES = [
  { key: "ithome",   "name": "IT\u4e4b\u5bb6",     "url": "https://www.ithome.com/rss/",                                              "color": "#0055ff", "cat": "cn_tech" },
  { key: "huxiu",    "name": "\u864e\u55c5",         "url": "https://rss.huxiu.com/",                                                   "color": "#1a1a1a", "cat": "cn_tech" },
  { key: "sspai",    "name": "\u5c11\u6570\u6d3e",   "url": "https://sspai.com/feed",                                                    "color": "#d7434e", "cat": "cn_tech" },
  { key: "cnbeta",   "name": "cnBeta",              "url": "https://plink.anyfeeder.com/cnbeta",                                         "color": "#d32f2f", "cat": "cn_tech" },
  { key: "kr36",     "name": "36\u6c2a",             "url": "https://rsshub.ktachibana.party/36kr/information/AI",                       "color": "#0066ff", "cat": "cn_tech" },
  { key: "verge",    "name": "The Verge AI",         "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",         "color": "#e31937", "cat": "tech" },
  { key: "tc",       "name": "TechCrunch AI",        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",             "color": "#0a9e01", "cat": "tech" },
  { key: "ifanr",    "name": "\u7231\u8303\u513f",   "url": "https://www.ifanr.com/feed",                                                "color": "#00bc74", "cat": "cn_tech" },
  { key: "bbc",      "name": "BBC \u4e2d\u6587",     "url": "https://plink.anyfeeder.com/bbc/cn",                                       "color": "#bb1919", "cat": "news" },
  { key: "thepaper", "name": "\u6f8e\u6e43\u65b0\u95fb", "url": "https://plink.anyfeeder.com/thepaper",                                 "color": "#d32f2f", "cat": "news" },
];

const ITEMS_PER_SOURCE = 30;
const FETCH_TIMEOUT = 6000; // 单源超时 6s
const UA = 'starhub-rss-aggregator/1.0';

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
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1') // 先提取 CDATA 内容
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .trim();
}

function truncate(text, maxLen) {
  if (!text) return '';
  text = text.trim();
  if (text.length <= maxLen) return text;
  // 尝试在句子边界截断
  const cut = text.slice(0, maxLen).lastIndexOf('\u3002');
  if (cut > 30) return text.slice(0, cut + 1);
  return text.slice(0, maxLen) + '\u2026';
}

// ── RSS 解析 ──

function parseRSS20(xml) {
  const items = [];
  // 提取所有 <item>...</item>
  const itemRegex = /<item[^>]*>([\s\S]*?)<\/item>/gi;
  let match;
  while ((match = itemRegex.exec(xml)) !== null && items.length < ITEMS_PER_SOURCE) {
    const block = match[1];
    const title = stripHtml(extractTag(block, 'title'));
    const link = stripHtml(extractTag(block, 'link'));
    const desc = truncate(stripHtml(extractTag(block, 'description')), 300);
    const pubDate = extractTag(block, 'pubDate');
    if (!title || !link) continue;
    items.push({ title, link, summary: desc, pub_date: pubDate });
  }
  return items;
}

function parseAtom(xml) {
  const items = [];
  const entryRegex = /<entry[^>]*>([\s\S]*?)<\/entry>/gi;
  let match;
  while ((match = entryRegex.exec(xml)) !== null && items.length < ITEMS_PER_SOURCE) {
    const block = match[1];
    const title = stripHtml(extractTag(block, 'title'));
    // Atom link: <link href="..." /> 或 <link>...</link>
    let link = extractAttr(block, 'link', 'href');
    if (!link) link = stripHtml(extractTag(block, 'link'));
    if (!link) {
      const id = extractTag(block, 'id');
      link = id;
    }
    const desc = truncate(stripHtml(extractTag(block, 'summary') || extractTag(block, 'content')), 300);
    const pubDate = extractTag(block, 'updated') || extractTag(block, 'published');
    if (!title || !link) continue;
    items.push({ title, link, summary: desc, pub_date: pubDate });
  }
  return items;
}

function parseRSS(xml) {
  // 检测格式
  if (xml.includes('<feed') || xml.includes('<atom:feed')) {
    return parseAtom(xml);
  }
  return parseRSS20(xml);
}

// ── 时间格式化 ──

function fmtRelTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 0) return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  if (diff < 60) return diff + '\u79d2\u524d';
  const min = Math.floor(diff / 60);
  if (min < 60) return min + '\u5206\u949f\u524d';
  const hr = Math.floor(min / 60);
  if (hr < 24) return hr + '\u5c0f\u65f6\u524d';
  const day = Math.floor(hr / 24);
  if (day < 30) return day + '\u5929\u524d';
  return d.toLocaleDateString('zh-CN');
}

// ── 抓取单个源 ──

async function fetchOne(source) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT);
  try {
    const res = await fetch(source.url, {
      signal: controller.signal,
      headers: {
        'User-Agent': UA,
        'Accept': 'application/rss+xml, application/xml, text/xml, application/atom+xml',
      },
    });
    if (!res.ok) return [];
    const text = await res.text();
    const items = parseRSS(text);
    return items.map(it => ({
      ...it,
      time_str: fmtRelTime(it.pub_date),
    }));
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

// ── Handler ──

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'Method Not Allowed' });
    return;
  }

  // 并行抓取 Top 10 源
  const results = await Promise.allSettled(
    TOP_SOURCES.map(src => fetchOne(src).then(items => ({ ...src, items })))
  );

  const sources = results.map(r => r.status === 'fulfilled' ? r.value : { ...r.reason || {}, items: [] });

  const totalItems = sources.reduce((sum, s) => sum + s.items.length, 0);

  // CDN 缓存 5 分钟，过期后后台重新验证
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Access-Control-Allow-Origin', '*');

  res.status(200).json({
    updated_at: new Date().toISOString(),
    total_sources: sources.length,
    total_items: totalItems,
    sources,
  });
}
