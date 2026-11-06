/** Resolve the API hop on Vercel; keep the browser on its configured proxy. */
export default async function handler(_request, response) {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Referrer-Policy", "no-referrer");
  const base = (process.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  if (!base) return response.status(500).json({ detail: "API não configurada." });
  try {
    const upstream = await fetch(`${base}/api/meta/oauth/start`, {
      redirect: "manual", signal: AbortSignal.timeout(15000),
    });
    const location = upstream.headers.get("location");
    if (![302, 303, 307, 308].includes(upstream.status) || !location) throw new Error("Invalid OAuth redirect");
    const target = new URL(location);
    if (target.protocol !== "https:" || !["instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com"].includes(target.hostname)) throw new Error("Invalid OAuth destination");
    return response.redirect(302, target.toString());
  } catch {
    return response.status(502).json({ detail: "Não foi possível iniciar a conexão. Tente novamente em instantes." });
  }
}
