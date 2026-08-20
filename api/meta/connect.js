/**
 * Link público de início do OAuth. A API cria um state de uso único e então
 * redireciona diretamente para o login oficial do Instagram.
 */
export default function handler(_request, response) {
  const apiBaseUrl = (process.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  if (!apiBaseUrl) {
    return response.status(500).json({ detail: "VITE_API_BASE_URL não configurada." });
  }

  response.setHeader("Cache-Control", "no-store");
  return response.redirect(302, `${apiBaseUrl}/api/meta/oauth/start`);
}
