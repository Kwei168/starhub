// Vercel Serverless Function：Agnes AI 翻译代理
// 背景：前端运行时翻译 AI 动态流英文标题。Agnes（agnes-2.5-flash）翻译质量与
//       可用性远优于免费端点，但 API Key 不能暴露在前端代码中，故经服务端代理。
//       本代理失败（未配 key / 上游异常 / 限流）时，前端自行降级 Google GTX 免费端点。
// 用法：POST /api/translate  { "texts": ["...", ...] }
//        → 200 { ok: true, engine: "agnes", translations: ["...", ...] }（与 texts 等长、按序对应；单条失败为空串）
// 防护：CORS 白名单；密钥从环境变量 AGNES_API_KEY 读取；实例内存缓存 + 轻量限流
const ALLOWED_ORIGINS = new Set([
  'https://starhub-refresh.vercel.app',
  'https://kwei168.github.io',
]);

const AGNES_URL = 'https://apihub.agnes-ai.com/v1/chat/completions';
const SYSTEM_PROMPT = '你是翻译引擎。把用户输入翻译成简体中文，只输出译文，不要解释。';
const MAX_TEXTS = 20;        // 与前端分批大小（15）匹配，留余量
const MAX_TEXT_LEN = 1500;   // 与构建侧 _agnes_translate 截断一致
const CACHE_TTL = 24 * 60 * 60 * 1000;
const RATE_LIMIT = 120;      // 每实例每分钟最多请求数。页面首屏卡片墙+AI面板并发补翻需 20~40 次，
                            // 旧值 30 会把自己限流（首屏 ok=2/24 实证）；120 仍可拦截滥用
const UPSTREAM_TIMEOUT = 12000;
const AGNES_CONCURRENCY = 4; // 上游并发上限。实测无限制并发（首屏 100+ 同时调 Agnes）会遭上游批量拒绝（502，
                            // 单发则 200），收敛到 4 同时保留吐量；translateOne 内含 1 次退避重试

const cacheMap = new Map();  // text 前缀 → { t, zh }
const rateMap = new Map();   // ip → [windowStart, count]

function getCache(key) {
  const e = cacheMap.get(key);
  if (e && Date.now() - e.t < CACHE_TTL) return e.zh;
  cacheMap.delete(key);
  return null;
}

function setCache(key, zh) {
  if (cacheMap.size >= 500) {
    const oldest = cacheMap.keys().next().value;
    cacheMap.delete(oldest);
  }
  cacheMap.set(key, { t: Date.now(), zh });
}

function rateLimited(ip) {
  const now = Date.now();
  const e = rateMap.get(ip);
  if (!e || now - e[0] > 60000) { rateMap.set(ip, [now, 1]); return false; }
  e[1] += 1;
  return e[1] > RATE_LIMIT;
}

async function translateOne(text, apiKey) {
  const r = await fetch(AGNES_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
      'User-Agent': 'starhub-auto-update',
    },
    body: JSON.stringify({
      model: 'agnes-2.5-flash',
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: String(text).slice(0, MAX_TEXT_LEN) },
      ],
      max_tokens: 400,
      temperature: 0.2,
      // 思考型模型：关闭思考避免 max_tokens 被推理耗尽，同时加速响应
      chat_template_kwargs: { enable_thinking: false },
    }),
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT),
  });
  if (!r.ok) throw new Error(`agnes ${r.status}`);
  const j = await r.json();
  const out = ((j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || '').trim();
  if (!out) throw new Error('agnes empty');
  return out;
}

// 单条失败退避后重试一次（上游瞬时限流/抖动）
async function translateOneRetry(text, apiKey) {
  try { return await translateOne(text, apiKey); }
  catch (e) {
    await new Promise((r) => setTimeout(r, 400));
    return await translateOne(text, apiKey);
  }
}

// 有限并发池：按序保填充，最多 limit 个 worker 同时执行 fn
async function mapPool(items, limit, fn) {
  const out = new Array(items.length);
  let i = 0;
  async function worker() { while (i < items.length) { const idx = i++; out[idx] = await fn(items[idx], idx); } }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return out;
}

export default async function handler(req, res) {
  const origin = (req.headers['origin'] || '').toLowerCase();
  if (ALLOWED_ORIGINS.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Vary', 'Origin');
  }
  if (req.method === 'OPTIONS') { res.status(ALLOWED_ORIGINS.has(origin) ? 204 : 403).end(); return; }
  if (req.method !== 'POST') { res.status(405).json({ error: 'Method Not Allowed' }); return; }
  if (!ALLOWED_ORIGINS.has(origin) && origin !== '') { res.status(403).json({ error: 'Forbidden' }); return; }

  const apiKey = process.env.AGNES_API_KEY;
  if (!apiKey) { res.status(500).json({ error: 'AGNES_API_KEY not configured' }); return; }

  const ip = (req.headers['x-real-ip'] || req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'local';
  if (rateLimited(ip)) { res.status(429).json({ error: 'Too Many Requests' }); return; }

  const body = req.body || {};
  const texts = Array.isArray(body.texts)
    ? body.texts.filter((t) => typeof t === 'string' && t.trim())
    : [];
  if (!texts.length) { res.status(400).json({ error: 'texts must be a non-empty string array' }); return; }
  if (texts.length > MAX_TEXTS) { res.status(400).json({ error: `texts limited to ${MAX_TEXTS} items per request` }); return; }

  // 缓存命中的直接取用；未命中的走并发池调 Agnes（单条失败返回空串，不阻塞整批）
  const diag = []; // 诊断：记录上游失败原因（仅状态码/错误类，不含密钥），502 时回传便于线上定位
  const pending = [];
  const results = await Promise.all(texts.map(async (t, idx) => {
    const key = t.slice(0, 200);
    const hit = getCache(key);
    if (hit) return hit;
    pending.push(idx);
    return null; // 占位，池完成后再回填
  }));
  const filled = await mapPool(pending, AGNES_CONCURRENCY, async (idx) => {
    const t = texts[idx];
    try {
      const zh = await translateOneRetry(t, apiKey);
      setCache(t.slice(0, 200), zh);
      return zh;
    } catch (e) {
      const reason = (e && e.message) || 'unknown';
      if (!diag.includes(reason)) diag.push(reason);
      return '';
    }
  });
  filled.forEach((zh, k) => { results[pending[k]] = zh; });

  if (!results.some(Boolean)) { res.status(502).json({ error: 'All translations failed', diag: diag.slice(0, 5) }); return; }
  res.status(200).json({ ok: true, engine: 'agnes', translations: results });
}
