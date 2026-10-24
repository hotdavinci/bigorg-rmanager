# Gateway de mídia, túneis e hospedagem

## Resumo

URLs temporárias para vídeos/capas e separação de portas. Consulte ao diagnosticar acesso externo e deploy.

## Gateway

app/media_gateway.py publica arquivos registrados por token opaco, com prazo de validade e tabela em memória. A rota /media/{token} resolve somente registros autorizados; token desconhecido retorna ausência e registro expirado possui tratamento próprio. Não é endpoint para receber caminho arbitrário do cliente.

## Ciclo de vida

Reinício perde o registro em memória. A URL pode expirar antes de um consumidor remoto terminar. Preservar arquivo local não mantém automaticamente uma URL anterior; considerar tempo de processamento ao emitir acessos.

## Túneis

QuickTunnel pode iniciar cloudflared quando o modo local exige exposição. Configuração estável de public_media_base_url permite infraestrutura própria, inclusive serviço gerenciado no VPS. A porta da interface/API e a porta de mídia têm funções distintas.

## Operação

Em 10/10/2026, adicionada na configuração local `/etc/cloudflared/config.yml` da VPS a rota `media.hotvinci.cfd` para `http://127.0.0.1:8001`, preservando rotas anteriores. Validação ingress aprovada; serviço cloudflared reiniciado. HTTPS público com token sintético inexistente retornou o JSON 404 esperado do gateway. `PUBLIC_MEDIA_BASE_URL` atualizado para `https://media.hotvinci.cfd` e backend reiniciado. Sem publicação de teste. A presença de token-file no comando não implica que as rotas sejam gerenciadas remotamente; esta instalação usa ingress local. Não foi necessário migrar o túnel no painel.

HOSPEDAGEM.md e deploy guardam procedimentos anteriores. Conferir paths, serviço, domínio e configuração efetivos antes de aplicar comandos. Não iniciar túnel, publicar arquivo nem instalar serviço apenas para conferir esta documentação.

## Fontes e limites

- [`app/media_gateway.py`](<../app/media_gateway.py>)
- [`app/tunnel.py`](<../app/tunnel.py>)
- [`app/config.py`](<../app/config.py>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.
