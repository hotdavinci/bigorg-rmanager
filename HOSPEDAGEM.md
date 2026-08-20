# Publicar o Reels Manager

O painel pode ficar na Vercel, mas a VPS precisa continuar ligada: ela guarda as m\u00eddias, executa os scripts Python e publica os Reels na hora certa. A Vercel sozinha n\u00e3o executa esse agendador continuamente.

## Dom\u00ednios recomendados

- `app.seudominio.com`: painel na Vercel;
- `api.seudominio.com`: API da VPS, publicada por um Cloudflare Tunnel nomeado;
- `media.seudominio.com`: entrega tempor\u00e1ria dos v\u00eddeos \u00e0 Meta.

## GitHub e Vercel

1. Crie um reposit\u00f3rio vazio no GitHub e envie a pasta inteira deste projeto. O `.gitignore` j\u00e1 exclui tokens, banco e v\u00eddeos.
2. Na Vercel, importe esse reposit\u00f3rio com a pasta raiz como diret\u00f3rio do projeto. O build e a pasta de sa\u00edda j\u00e1 est\u00e3o em `vercel.json`.
3. Em **Settings > Environment Variables** da Vercel, crie:

   - `VITE_API_BASE_URL` = `https://api.seudominio.com`
   - `OAUTH_CALLBACK_TARGET` = `https://api.seudominio.com/api/meta/oauth/callback`

4. Na configura\u00e7\u00e3o da Meta, use exatamente `https://app.seudominio.com/api/meta/callback` como Redirect URI e tamb\u00e9m em `META_REDIRECT_URI` da VPS.

## Vari\u00e1veis da VPS

No `.env` da VPS, mantenha todas as vari\u00e1veis `META_*`, `APP_ENCRYPTION_KEY`, `ADMIN_EMAIL` e `ADMIN_PASSWORD`. Adicione:

```env
CORS_ALLOWED_ORIGINS=https://app.seudominio.com
SESSION_HTTPS_ONLY=true
META_REDIRECT_URI=https://app.seudominio.com/api/meta/callback
```

N\u00e3o coloque `META_APP_SECRET`, `META_INSTAGRAM_APP_SECRET`, `APP_ENCRYPTION_KEY`, senha ou tokens na Vercel/GitHub. A Vercel s\u00f3 recebe as duas vari\u00e1veis acima.
