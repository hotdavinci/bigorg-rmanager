# Métricas, atividade e auditoria

## Resumo

Sincronização de Reels, snapshots, reset local dos Insights, MVP separado no PC e histórico operacional. Consulte ao mudar relatórios, reiniciar o histórico ou rastrear resultados.

## Sincronização

O backend sincroniza Reels e indicadores como visualizações, curtidas e comentários, registrando InstagramReel e snapshots. Campos de próxima sincronização e elegibilidade controlam trabalho periódico; contas recém-conectadas também entram na lógica de sincronização.

## Reset local — 14/10/2026

Reset solicitado pelo usuário executado na VPS: removidos `InstagramReel` e `InstagramReelSnapshot`, cache de vídeos/miniaturas retirado da pasta ativa e erros de Insights limpos. Banco e cache anteriores preservados em backup protegido `/root/rmanager-insights-reset-20261014/backup`. Contagens de contas, campanhas, posts, biblioteca e tentativas conferidas sem alteração; nenhuma publicação foi excluída na Meta. Serviço interrompido durante a operação para evitar concorrência com a sincronização e iniciado novamente.

`ApplicationSetting.insights_reset_at` registra o corte UTC. `sync_reel_insights` usa `app/insight_reset.py` para ignorar mídia publicada antes desse corte, inclusive em sincronizações manuais, impedindo o retorno automático do histórico apagado. Sem corte, preserva comportamento legado; com corte e timestamp ausente/inválido, não importa o item. Publicações novas continuam sendo arquivadas e sincronizadas normalmente. Cinco testes sintéticos cobrem comparação UTC/offsets, datas antigas/novas e timestamps inválidos. Registros/cache ativos vazios e HTTP 200 verificados após a operação, sem forçar sincronização externa ou publicar conteúdo.

## Apresentação

A interface usa períodos, gráficos e parâmetros de avaliação, incluindo limiar de visualizações. Thumbnail e vídeo podem ter cache local. Snapshot é observação em um instante, não contador autoritativo de todos os eventos da plataforma.

## Auditoria

AuditLog preserva referências textuais/IDs deliberadamente sem depender de todas as entidades continuarem existentes. PublicationAttempt separa tentativas de um mesmo post; ProcessingExecution registra processamento. Excluir conta/campanha não deve tornar o histórico ilegível nem introduzir vazamento de credenciais.

## Diagnóstico

O calendário do painel filtra `conta_apta === false` no frontend, inclusive para posts publicados/cancelados. Assim, contas inaptas podem fazer a agenda parecer totalmente vazia apesar de haver histórico no banco. Confirmar separadamente a existência de posts futuros e os estados das contas. O reset dos Insights não remove `ScheduledPost` ou `PublicationAttempt`.

Correlacionar campanha, post, tentativa, horário e conta. Resultado de publicação e resultado de sincronização são etapas diferentes: atraso de métricas não prova falha de postagem.

## Fontes e limites

- [`app/main.py`](<../app/main.py>)
- [`app/models.py`](<../app/models.py>)
- [`frontend/src.tsx`](<../frontend/src.tsx>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.

## MVP local separado — 15/10/2026

[Instruções e limites](../tools/metrics-local/README.md). Painel HTML/CSS/JS e servidor Python loopback em `tools/metrics-local`, com SQLite independente no PC. Quando ativo, importa automaticamente novas contas aptas do endpoint de contas do sistema e consulta contadores públicos de Reels com Instaloader. Não usa tokens de publicação nem consulta métricas pela VPS; não baixa vídeos/capas. Uma conta por vez, sem sobreposição, desde 17/10/2026 próxima rodada imediatamente após a anterior, com espera em falhas. Inicia pausado e só funciona enquanto processo/PC estão ativos.

Contas inativas/removidas e Reels ausentes permanecem salvos; falhas/contadores nulos não zeram histórico. Lista resume totais históricos por conta e geral; expansão mostra cada Reel, tipo de contador, última leitura e histórico. Plays/views públicos não são presumidos equivalentes aos Insights oficiais. Não integra ou altera o reset dos Insights da VPS.

Onze testes sintéticos aprovados e interface validada no navegador com banco demonstrativo separado. Importação real da lista confirmada; primeira consulta pública anônima de contador foi limitada pelo Instagram. Não afirmar coleta de views reais validada; sessão opcional de consulta deve ser conectada pelo usuário no lançador local. Nenhum deploy/modificação da VPS ou do site principal.

O MVP local também mostra primeira vinculação conhecida (`conectada_em`, UTC) ou primeira detecção como aproximação, sem alegar conhecer a criação do perfil Instagram. Salva transição apta→inapta, instante da detecção e última observação ativa; queda ocorreu nesse intervalo. Repetição não desloca a detecção; reativação preserva última queda. Remoção é separada, falha de métrica não muda estado da conta. Migração aditiva; sem inventar datas históricas. Horários exibidos em São Paulo. Quatorze testes sintéticos aprovados e texto de datas verificado com conta fictícia no navegador.

Diagnóstico posterior da sessão local confirmou `sessionid` ausente/vazio; verificação retornou HTTP 401 com pedido de espera, não evidência de senha incorreta. Corrigidos placeholder de cookie no login, validação antes de salvar, rejeição local de sessão incompleta e distinção entre 401/403/429. Dezenove testes sintéticos aprovados; nova sessão e views reais seguem pendentes de login interativo do usuário pelo lançador corrigido. Consulte diagnóstico no README do MVP.

MVP local em coleta contínua desde 17/10/2026; reimporta contas a cada rodada, preserva RateController entre ciclos. Ativas primeiro; inativas/removidas em vermelho ao fim. 21 testes sintéticos aprovados. Veja README do MVP para pausas operacionais em falhas.

Desde 17/10/2026 o experimento local permite 3 contas e 10 Reels simultâneos no total. Pool global limitado, HTTP por thread e RateController compartilhado; paginação por shortcode evita Post sequencial do get_reels. 23 testes sintéticos aprovados; ganho real não medido, sem prometer fator de aceleração. Ver README do MVP.
