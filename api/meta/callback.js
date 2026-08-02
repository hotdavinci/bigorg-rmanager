/**
 * Ponte HTTPS do OAuth. A Vercel recebe o retorno da Meta e devolve o
 * navegador para a API privada da aplica\u00e7\u00e3o, sem guardar tokens ou segredos.
 */
export default function handler(request, response) {
  const target = process.env.OAUTH_CALLBACK_TARGET || "http://127.0.0.1:8000/api/meta/oauth/callback";
  const allowed = ["code", "state", "error", "error_reason", "error_description"];
  const query = new URLSearchParams();

  for (const key of allowed) {
    const value = request.query[key];
    if (typeof value === "string") query.set(key, value);
  }

  response.setHeader("Cache-Control", "no-store");
  response.redirect(302, `${target}?${query.toString()}`);
}
