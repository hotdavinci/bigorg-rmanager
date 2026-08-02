/**
 * Ponte pública para o OAuth do Instagram.
 *
 * A Meta retorna para este endereço HTTPS estável. Em seguida, o navegador da
 * própria pessoa é redirecionado ao Reels Manager que está rodando localmente.
 * Nenhum token, segredo ou vídeo passa pela Vercel.
 */
export default function handler(request, response) {
  const allowed = [
    "code",
    "state",
    "error",
    "error_reason",
    "error_description",
  ];
  const query = new URLSearchParams();

  for (const key of allowed) {
    const value = request.query[key];
    if (typeof value === "string") query.set(key, value);
  }

  response.setHeader("Cache-Control", "no-store");
  const target = process.env.OAUTH_CALLBACK_TARGET || "http://127.0.0.1:8000/api/meta/oauth/callback";
  response.redirect(302, `${target}?${query.toString()}`);
}
