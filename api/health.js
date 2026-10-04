// Vercel Serverless Function：管线健康探活（T5）
// GET /api/health（无需认证，只读）→
//   { ok, last_build_age_minutes, star_fast_age_minutes,
//     secrets: { agnes, gh_token, refresh_key }, pages_ok }
//
// 口径（v7 计划：最近【成功】构建年龄 + 触发链状态 + Secret 配置布尔）：
//   last_build_age_minutes = update.yml 最近一场 conclusion=success 的 run 距今分钟数（查不到 = null）
//   star_fast_age_minutes  = star-fast.yml 同口径
//   pages_ok               = Pages 首页 200 且体积 ≥ MIN_INDEX_BYTES——限流占位页 ~698B
//                            曾假绿（HANDOFF §8.20），只认 200 不够
//   secrets.*              = Boolean 包装，只报"配没配"，原始值绝不进响应
//   ok                     = pages_ok 且成功构建年龄 ≤ STALE_BUILD_MINUTES
//
// 不健康时 HTTP 503（body 仍是同结构 JSON）：外部探活（UptimeRobot 类）按
// 「30 分钟 GET，非 2xx 告警」配置即可同时抓住端点死亡与静默退化——
// 这是本端点存在的理由：本仓最高频的事故模式是静默退化（快照出仓、增量退化、
// Pages 被拖慢都曾安静数天才被发现）。
// 响应缓存 60s：本函数自己会打 GitHub API 与 Pages，不缓存会被轮询烧穿配额。

const ALLOWED_ORIGINS = new Set([
  'https://starhub-refresh.vercel.app',
  'https://kwei168.github.io',
]);

const REPO = 'Kwei168/starhub';
const PAGES_INDEX = 'https://kwei168.github.io/starhub/index.html';
const MIN_INDEX_BYTES = 5000;   // 真首页 ≥250KB；698B 是限流占位页
const STALE_BUILD_MINUTES = 120; // 小时场连续 2 场缺席视为管线不健康
const TTL_MS = 60 * 1000;
const GH_TIMEOUT = 8000;
const PAGES_TIMEOUT = 6000;

const cache = { t: 0, ok: true, body: null };

function ageMinutes(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  return Number.isFinite(ms) ? Math.max(0, Math.round(ms / 60000)) : null;
}

// 最近【成功】构建的年龄：status=success 过滤由 GitHub API 侧完成，
// 失败/进行中的场不算"活"——否则一场连红会把健康读数冻结在红场之前。
async function lastSuccessAgeMinutes(workflow) {
  const u = new URL('https://api.github.com/repos/' + REPO + '/actions/workflows/' + workflow + '/runs');
  u.searchParams.set('status', 'success');
  u.searchParams.set('per_page', '1');
  const headers = {
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'starhub-refresh',
  };
  if (process.env.GH_TOKEN) headers.Authorization = 'Bearer ' + process.env.GH_TOKEN;
  const r = await fetch(u, { headers, signal: AbortSignal.timeout(GH_TIMEOUT) });
  if (!r.ok) return null;
  const j = await r.json();
  return ageMinutes(j.workflow_runs && j.workflow_runs[0] && j.workflow_runs[0].created_at);
}

async function pagesProbeOk() {
  try {
    const r = await fetch(PAGES_INDEX, {
      headers: { 'User-Agent': 'starhub-refresh' },
      signal: AbortSignal.timeout(PAGES_TIMEOUT),
    });
    if (!r.ok) return false;
    const len = Number(r.headers.get('content-length') || 0);
    if (len) return len >= MIN_INDEX_BYTES;
    const body = await r.text();
    return body.length >= MIN_INDEX_BYTES;
  } catch (e) {
    return false;
  }
}

export default async function handler(req, res) {
  const origin = (req.headers['origin'] || '').toLowerCase();
  const allowed = ALLOWED_ORIGINS.has(origin);
  if (allowed) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Vary', 'Origin');
  }
  if (req.method === 'OPTIONS') { res.status(204).end(); return; }
  if (req.method !== 'GET') { res.status(405).json({ error: 'Method Not Allowed' }); return; }

  if (cache.body && Date.now() - cache.t < TTL_MS) {
    res.status(cache.ok ? 200 : 503).json(cache.body);
    return;
  }

  try {
    const [buildAge, starAge, pagesOk] = await Promise.all([
      lastSuccessAgeMinutes('update.yml'),
      lastSuccessAgeMinutes('star-fast.yml'),
      pagesProbeOk(),
    ]);
    const ok = pagesOk && buildAge !== null && buildAge <= STALE_BUILD_MINUTES;
    const payload = {
      ok,
      last_build_age_minutes: buildAge,
      star_fast_age_minutes: starAge,
      secrets: {
        agnes: Boolean(process.env.AGNES_API_KEY || process.env.AGNES_API_KEYS),
        gh_token: Boolean(process.env.GH_TOKEN),
        refresh_key: Boolean(process.env.REFRESH_KEY),
      },
      pages_ok: pagesOk,
    };
    cache.t = Date.now();
    cache.ok = ok;
    cache.body = payload;
    res.status(ok ? 200 : 503).json(payload);
  } catch (e) {
    // 探活自身故障也不能报健康；但不写缓存（下一请求重试）
    res.status(503).json({ ok: false, error: 'health probe failed' });
  }
}
