/** Relay only the OAuth callback, without sending the browser to the API domain. */
export default async function handler(request, response) {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Referrer-Policy", "no-referrer");
  const target = process.env.OAUTH_CALLBACK_TARGET;
  if (!target) return response.status(500).send("Callback não configurado.");
  try {
    const url = new URL(target);
    for (const key of ["code", "state", "error", "error_reason", "error_description"]) {
      const value = request.query[key];
      if (typeof value === "string") url.searchParams.set(key, value);
    }
    const upstream = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(55000) });
    if (upstream.status >= 300 && upstream.status < 400) throw new Error("Unexpected redirect");
    const body = await upstream.text();
    response.setHeader("Content-Type", upstream.headers.get("content-type") || "text/html; charset=utf-8");
    return response.status(upstream.status).send(body);
  } catch {
    return response.status(502).send("Não foi possível confirmar a resposta do servidor. Confira o painel antes de tentar conectar novamente.");
  }
}
