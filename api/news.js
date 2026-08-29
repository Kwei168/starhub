// Vercel Serverless Function：36氪 AI 资讯流代理
// 背景：36氪官方 RSS（36kr.com/feed*）有人机验证反爬墙，浏览器/服务器直连均被拦截；
//       且 RSSHub 公共镜像的 CORS 头不合法（回显固定字符串），前端无法直连。
//       故由本函数在服务端经 RSSHub 公共镜像中转，输出干净 JSON。
// 用法：GET /api/news → { updated_at, source, items: [{title, link, summary, publishedAt}] }
// 防护：CORS 白名单（同 events.js）；GET 无敏感参数，无需密钥
// 缓存：结果 10 分钟 TTL（Vercel 实例内存）
const ALLOWED_ORIGINS = new Set([
  'https://starhub-refresh.vercel.app',
  'https://kwei168.github.io',
]);

// RSSHub 公共镜像链（可用性会波动，依次尝试；路由 /36kr/information/AI 为 36氪 AI 资讯流）
const MIRRORS = [
  'https://rsshub.rssforever.com/36kr/information/AI',
  'https://hub.slarker.me/36kr/information/AI',
  'https://rsshub.app/36kr/information/AI',
];

const TTL = 10 * 60 * 1000;
let cache = { t: 0, v: null };

function stripHtml(s) {
  return (s || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

async function fetchFeed(url) {
  const r = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (starhub-refresh)',
      'Accept': 'application/rss+xml, application/xml, text/xml',
    },
    signal: AbortSignal.timeout(12000),
  });
  if (!r.ok) throw new Error('http ' + r.status);
  return r.text();
}

// RSS 2.0 极简解析（36氪源结构固定，无需完整 XML 解析器）
function parseRss(xml) {
  const items = [];
  const blocks = xml.match(/<item>[\s\S]*?<\/item>/g) || [];
  for (const b of blocks) {
    const get = tag => {
      const m = b.match(new RegExp('<' + tag + '>([\\s\\S]*?)</' + tag + '>'));
      if (!m) return '';
      return m[1].replace(/^<!\[CDATA\[/, '').replace(/\]\]>$/, '').trim();
    };
    const title = stripHtml(get('title'));
    const link = get('link');
    const summary = stripHtml(get('description')).slice(0, 200);
    const pub = get('pubDate');
    const d = pub ? new Date(pub) : null;
    if (title && link) {
      items.push({ title, link, summary, publishedAt: d && !isNaN(d) ? d.toISOString() : '' });
    }
  }
  return items;
}

export default async function handler(req, res) {
  const origin = (req.headers['origin'] || '').toLowerCase();
  const allowed = ALLOWED_ORIGINS.has(origin);
  if (allowed) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Vary', 'Origin');
  }
  if (req.method === 'OPTIONS') { res.status(allowed ? 204 : 403).end(); return; }
  if (req.method !== 'GET') { res.status(405).json({ error: 'Method Not Allowed' }); return; }
  if (!allowed) { res.status(403).json({ error: 'Forbidden' }); return; }

  if (cache.v && Date.now() - cache.t < TTL) { res.status(200).json(cache.v); return; }

  let items = [];
  for (const url of MIRRORS) {
    try {
      const xml = await fetchFeed(url);
      items = parseRss(xml);
      if (items.length) break;
    } catch (e) { /* 静默尝试下一个镜像 */ }
  }
  if (!items.length) {
    res.status(502).json({ error: '上游服务不可用' });
    return;
  }

  const body = {
    updated_at: new Date().toISOString(),
    source: '36氪',
    items: items.slice(0, 30),
  };
  cache = { t: Date.now(), v: body };
  res.status(200).json(body);
}
