# Ponte OAuth da Vercel

Publique esta pasta no projeto Vercel `bigorg-rmanager`.

A URL de retorno que deve ser cadastrada na Meta e em `META_REDIRECT_URI` e:

`https://bigorg-rmanager.vercel.app/api/meta/callback`

Ela somente encaminha o retorno OAuth, no mesmo navegador, para o Reels Manager
local em `http://127.0.0.1:8000`. Nenhum segredo e armazenado na Vercel.
