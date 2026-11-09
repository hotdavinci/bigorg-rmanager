/** Resolve the API hop on Vercel; keep the browser on its configured proxy. */
export default async function handler(request, response) {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Referrer-Policy", "no-referrer");
  const base = (process.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  if (!base) return response.status(500).json({ detail: "API não configurada." });
  const app = request.query?.app;
  if (app !== undefined && (typeof app !== "string" || !/^app-[1-9][0-9]{0,17}$/.test(app))) {
    return response.status(400).json({ detail: "Use um App Meta no formato app-1, app-2, app-3." });
  }
  try {
    const url = `${base}/api/meta/oauth/start${app ? `?app=${encodeURIComponent(app)}` : ""}`;
    const upstream = await fetch(url, {
      redirect: "manual", signal: AbortSignal.timeout(15000),
    });
    if (upstream.status === 404 && app) return response.status(404).json({ detail: "App Meta não encontrado." });
    if (upstream.status === 503) return response.status(503).json({ detail: "App Meta ainda não configurado para conexão." });
    const location = upstream.headers.get("location");
    if (![302, 303, 307, 308].includes(upstream.status) || !location) throw new Error("Invalid OAuth redirect");
    const target = new URL(location);
    if (target.protocol !== "https:" || !["instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com"].includes(target.hostname)) throw new Error("Invalid OAuth destination");
    return response.redirect(302, target.toString());
  } catch {
    return response.status(502).json({ detail: "Não foi possível iniciar a conexão. Tente novamente em instantes." });
  }
}
