// Vercel Serverless Function：BestBlogs 早报代理
// 背景：BestBlogs OpenAPI（api.bestblogs.dev/openapi/v2/*）需要 API Key 认证，
//       不能暴露在前端代码中。本函数在服务端持有密钥，前端通过本代理访问。
// 用法：GET /api/bestblogs?type=brief&date=2026-09-09&language=zh&limit=20
//        → { items: [{id, title, summary, tags, url, ...}] }
// 防护：CORS 白名单；密钥从环境变量 BESTBLOGS_API_KEY 读取
// 缓存：结果 30 分钟 TTL（Vercel 实例内存），节省日配额（PRO 500次/天）
const ALLOWED_ORIGINS = new Set([
  'https://starhub-refresh.vercel.app',
  'https://kwei168.github.io',
]);

const BESTBLOGS_BASE = 'https://api.bestblogs.dev/openapi/v2';
const TTL = 30 * 60 * 1000;

// 按 type+params 缓存（最多 30 条缓存项）
const cacheMap = new Map();

function cacheKey(params) {
  return `${params.type}|${params.date || ''}|${params.language || 'zh'}|${params.limit || 20}`;
}

function getCache(key) {
  const entry = cacheMap.get(key);
  if (entry && Date.now() - entry.t < TTL) return entry.v;
  cacheMap.delete(key);
  return null;
}

function setCache(key, value) {
  if (cacheMap.size >= 30) {
    const oldest = cacheMap.keys().next().value;
    cacheMap.delete(oldest);
  }
  cacheMap.set(key, { t: Date.now(), v: value });
}

// 合法 type 白名单
const VALID_TYPES = new Set(['brief', 'resources', 'topics']);

export default async function handler(req, res) {
  const origin = (req.headers['origin'] || '').toLowerCase();
  if (ALLOWED_ORIGINS.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Vary', 'Origin');
  }
  if (req.method === 'OPTIONS') { res.status(ALLOWED_ORIGINS.has(origin) ? 204 : 403).end(); return; }
  if (req.method !== 'GET') { res.status(405).json({ error: 'Method Not Allowed' }); return; }
  if (!ALLOWED_ORIGINS.has(origin) && origin !== '') { res.status(403).json({ error: 'Forbidden' }); return; }

  const apiKey = process.env.BESTBLOGS_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: 'BESTBLOGS_API_KEY not configured' });
    return;
  }

  // 解析参数
  const { type, date, language, limit, qualified } = req.query || {};
  const reqType = type || 'resources';
  if (!VALID_TYPES.has(reqType)) {
    res.status(400).json({ error: 'Invalid type. Valid: ' + [...VALID_TYPES].join(', ') });
    return;
  }

  const reqLang = language === 'en' ? 'en' : 'zh';
  const reqLimit = Math.min(parseInt(limit) || 20, 100);

  // 检查缓存
  const ck = cacheKey({ type: reqType, date, language: reqLang, limit: reqLimit });
  const cached = getCache(ck);
  if (cached) { res.status(200).json(cached); return; }

  // 构建请求 URL
  let url;
  if (reqType === 'brief') {
    // 早报端点（可能未实现，fallback 到 resources）
    const reqDate = date || new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10);
    url = `${BESTBLOGS_BASE}/brief?date=${reqDate}&language=${reqLang}`;
  } else if (reqType === 'topics') {
    url = `${BESTBLOGS_BASE}/topics?limit=${reqLimit}`;
  } else {
    // resources：精选内容列表
    const timeRange = '24h';
    const qualifiedParam = qualified === 'true' ? '&qualified=true' : '';
    url = `${BESTBLOGS_BASE}/resources?type=article&language=${reqLang}&time=${timeRange}&limit=${reqLimit}${qualifiedParam}`;
  }

  try {
    const r = await fetch(url, {
      headers: {
        'X-API-KEY': apiKey,
        'User-Agent': 'StarHub/1.0',
      },
      signal: AbortSignal.timeout(10000),
    });

    if (!r.ok) {
      // brief 端点 404 时 fallback 到 resources
      if (reqType === 'brief' && r.status === 404) {
        const fallbackUrl = `${BESTBLOGS_BASE}/resources?type=article&language=${reqLang}&time=24h&limit=${reqLimit}&qualified=true`;
        const r2 = await fetch(fallbackUrl, {
          headers: {
            'X-API-KEY': apiKey,
            'User-Agent': 'StarHub/1.0',
          },
          signal: AbortSignal.timeout(10000),
        });
        if (!r2.ok) {
          res.status(r2.status).json({ error: `BestBlogs API returned ${r2.status}` });
          return;
        }
        const data2 = await r2.json();
        const items = extractItems(data2);
        const body = { type: 'brief', fallback: true, language: reqLang, updated_at: new Date().toISOString(), items };
        setCache(ck, body);
        res.status(200).json(body);
        return;
      }
      const body = await r.text().catch(() => '');
      res.status(r.status).json({ error: `BestBlogs API returned ${r.status}`, detail: body.slice(0, 200) });
      return;
    }

    const data = await r.json();
    const items = extractItems(data);
    const body = {
      type: reqType,
      language: reqLang,
      updated_at: new Date().toISOString(),
      items,
    };
    setCache(ck, body);
    res.status(200).json(body);
  } catch (e) {
    res.status(502).json({ error: 'Failed to fetch from BestBlogs', detail: e.message });
  }
}

// 从响应中提取统一格式的 items
function extractItems(data) {
  if (!data || !data.success) return [];
  const d = data.data;
  if (!d) return [];

  // resources 响应：{ dataList: [...] }
  if (Array.isArray(d.dataList)) {
    return d.dataList.map(item => ({
      id: item.id,
      title: item.title || item.originalTitle || '',
      summary: item.oneSentenceSummary || '',
      tags: item.tags || [],
      mainPoints: item.mainPoints || [],
      featuredReason: item.featuredReason || '',
      url: item.id ? `https://bestblogs.dev/article/${item.id}` : '',
    }));
  }

  // brief 响应：{ items: [...] }
  if (Array.isArray(d.items)) {
    return d.items;
  }

  // topics 响应：直接数组
  if (Array.isArray(d)) {
    return d;
  }

  return [];
}
