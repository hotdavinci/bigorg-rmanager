# Campanhas e geração de agenda

## Resumo

Estados, contas vinculadas, prazo de liberação específico/global, seleção de mídia e campanhas recorrentes com horizonte móvel de 24 horas. Consulte para alterar planejamento, reposição e recuperação; regras anteriores permanecem legíveis.

## Configuração

A campanha reúne mídias, contas, scripts ordenados, legendas e regras de horários. Estratégias de seleção e distribuição determinam a sequência de posts; regras usam a configuração de fuso/intervalos. Uma alteração de estratégia precisa preservar posições e vínculos existentes.

## Janelas de publicação — 21/10/2026

### Campanha recorrente — 21/10/2026

Desde 23/10/2026, a interface permite adicionar/remover janelas diárias e ajustar mínimo e máximo de Reels por conta em cada uma. O contrato novo grava cada janela em `intervals` como `recurring:window:HH:MM-HH:MM:min-max`; a lista é ordenada por início, não admite sobreposição ou travessia da meia-noite, exige ao menos uma janela e limita a quantidade máxima aos minutos disponíveis. Mínimo igual ao máximo configura quantidade fixa. Os padrões de novas campanhas usam a mesma configuração; campanhas existentes preservam a regra salva. O marcador anterior `recurring:windows:12-18` segue legível e mantém suas três janelas originais. A geração, a recuperação, a reposição e a sincronização de novas contas aplicam a lista salva com horizonte móvel de 24 horas, reduzindo proporcionalmente as faixas que já passaram.

Nesta entrega, o backend foi atualizado na VPS com backup do código anterior em `/root/rmanager-configurable-windows-20261023`; serviço ativo e HTTP 200 após reiniciar. A interface foi enviada ao `main` em `c146d06` e o novo controle foi confirmado no bundle público. Build e 34 testes sintéticos em cópia isolada aprovados; nenhuma publicação real foi usada como teste.

Novas campanhas não pedem data inicial nem duração. O contrato usa `intervals` com uma ou mais janelas recorrentes; `start_date` e `days` são preenchidos internamente como âncora de posições e compatibilidade com a tabela existente, mas a resposta pública os apresenta como nulos e marca `recurring=true`. A geração inicial considera o período de agora até agora + 24 horas, incluindo as faixas ainda disponíveis no próprio dia. A cada cinco minutos, um worker avança esse horizonte e prepara os novos slots que entraram nele. Por exemplo, às 12:00 o período termina às 12:00 do dia seguinte: entram as faixas restantes das janelas de hoje e as de amanhã que couberem antes de 12:00. A margem de cinco minutos para preparação ainda se aplica. Uma faixa já registrada, mesmo publicada/cancelada/falha, não é recriada. Pausar ou cancelar a campanha interrompe a reposição; contas inaptas não recebem novos slots.

As três janelas e o sorteio estável de 12–18 Reels por janela/conta continuam iguais. O fim de cada faixa, combinado com a data relativa à criação, fornece a posição estável no banco para geração inicial, sincronização de conta e reposição. A margem de cinco minutos e a liberação da conta continuam válidas; preparação lenta pode deixar um slot vencer sem publicação. A reposição usa os scripts e mídias originais já configurados, sem executar trabalho dentro do loop assíncrono de publicação. Falha de uma reposição é auditada e tentada novamente na rodada seguinte. O modelo `windows:12-18` finito e os formatos `daily:N`/faixas antigas seguem aceitos e não são convertidos automaticamente.

Cópia local do modelo anterior: `backups-local/recurring-pre-20261021`, apenas código e documentação, sem banco, mídia ou segredos. Validação sintética em cópia sem `.env`/banco real: 31 testes de distribuição, contrato, recuperação e sincronização, além do build TypeScript/Vite. Não houve publicação real de teste.

Implantado na VPS em 21/10/2026 com backup do código anterior em `/root/rmanager-recurring-20261021/original`; serviço ativo e HTTP 200 em `/api/auth/status`. Commit `d80db4c` enviado ao `main` para a Vercel, cuja conclusão de build não pôde ser confirmada sem login no painel. Nenhuma campanha existente foi convertida ou reagendada por esta implantação.

O padrão inicial para novas campanhas é 08:30–09:30, 11:30–12:30 e 17:30–18:30 no fuso local do serviço (São Paulo), com 12 a 18 Reels por conta em cada janela completa. O sorteio depende de campanha, conta, data e janela; divide cada intervalo em faixas sem sobreposição e escolhe um minuto em cada uma. O limite final é exclusivo: 09:30 pertence ao período seguinte, não à primeira janela.

Uma conta nova recebe prazo explícito de zero dia na primeira conexão OAuth. Reconexões preservam o prazo específico que já existia; contas sem prazo específico continuam herdando a configuração global. Ao entrar durante uma janela, somente as faixas ainda disponíveis após a liberação e a margem de cinco minutos são materializadas. Por exemplo, entrada às 12:00 conserva aproximadamente metade das faixas de 11:30–12:30; as janelas posteriores recebem a quantidade integral. A mesma regra vale na geração inicial e na sincronização de conta. Se a preparação do vídeo ultrapassar uma faixa, o slot vencido pode ser descartado; a quantidade é uma meta de agendamento, não garantia de publicação pela Meta.

O marcador finito anterior é `windows:12-18` em `intervals`, sem migração do banco. Campanhas gravadas com esse marcador, `daily:N` ou faixas legadas conservam o contrato e a agenda existente. A recuperação lê o marcador do checkpoint ou da regra, e o índice de cada slot da sincronização deriva do fim da faixa para evitar duplicação em retomadas. O backup do modelo anterior à mudança para janelas está em `backups-local/schedule-model-20261021`; ele não inclui dados nem credenciais.

Implantação em 21/10/2026: `app/main.py` e `app/daily_schedule.py` instalados na VPS, com cópia anterior em `/root/rmanager-window-20261021/original`; serviço reiniciado, ativo e HTTP 200 em `/api/auth/status`. Commit `6cce6c9` enviado ao `main` para publicação da interface pela Vercel; a conclusão do build público não foi confirmada nesta rodada porque o painel Vercel exige login. Em cópia temporária sem `.env` e sem banco real, passaram 11 testes de distribuição/contrato, 5 de recuperação e 11 de sincronização, além do build TypeScript/Vite. Nenhuma publicação, conexão OAuth ou sincronização real foi usada como teste. A implantação não regenerou nem alterou campanhas e posts já existentes.

## Quantidade diária — 14/10/2026

O modelo anterior usava “Reels por dia e por conta”, distribuídos nas 24 horas de São Paulo. Essa regra continua aceita para campanhas já gravadas e clientes legados; a interface atual cria e edita pelo modelo de janelas descrito acima. A quantidade `daily:N` vale para cada conta e cada dia da campanha; a estratégia sequencial/aleatória continua escolhendo as mídias, não a quantidade. O sistema divide o período disponível em faixas sem sobreposição e sorteia um minuto em cada faixa.

Para hoje, distribui a quantidade no tempo restante após agora + cinco minutos e a liberação da conta. Dias anteriores e dias inteiros antes da liberação não são preenchidos retroativamente. Se faltarem minutos distintos para a quantidade pedida, informa erro; preparação que ultrapasse o horário de uma faixa pode reduzir os slots materializados. Após processar, a verificação final evita criar horários passados, inclusive se virar a meia-noite. Novos horários não antecipam a liberação da conta; prazos UTC são convertidos para São Paulo antes de comparar com a agenda local.

O contrato legado aceita `reels_per_day` inteiro entre 1 e 1440. Internamente a regra é persistida como `daily:N` no campo `intervals`, preservando o esquema do banco. As rotas retornam também `schedule.reels_per_day`; setup, geração, defaults, estimativa/sincronização de contas e recuperação entendem o mesmo formato. `intervals` antigos continuam aceitos e mantêm sua distribuição; nenhuma campanha/fila existente é convertida automaticamente. Editar uma campanha antiga pela interface atual transforma sua regra em campanha recorrente ao salvar.

Os testes de distribuição usam dados sintéticos e cobrem quantidade, limite do dia, prazo UTC, compatibilidade, contratos e retomada sem duplicação. Na entrega inicial de quantidade, a correção de capas foi adiada; ela foi implementada em 15/10/2026 e está descrita em Biblioteca e processamento.

Entrega confirmada: backend implantado na VPS, HTTP 200 e contrato de quantidade carregado; commit `25ae0f4` enviado ao Git e bundle público da Vercel confirmado com a nova interface. Build TypeScript/Vite e 19 testes sintéticos de staging aprovados; não houve geração/publicação real de teste. O diagnóstico posterior de capas está em [Biblioteca e processamento](biblioteca_processamento.md).

## Estados

O modelo distingue DRAFT, PROCESSING, PROCESSING_FAILED, READY_TO_SCHEDULE, SCHEDULE_GENERATED, ACTIVE, PAUSED, COMPLETED, CANCELLED e ERROR. São estados de campanha, diferentes dos estados de cada post e de cada tentativa de publicação.

## Geração

### Ordem de preparação — 15/10/2026

Trabalhos da geração da campanha são ordenados pelo horário planejado real, do mais cedo ao mais tarde, entre todas as contas. O minuto é definido antes dos lotes (`planned_minute`) e usado ao materializar o post; se o processamento ultrapassar esse horário, mantém a verificação de futuro e ajusta somente dentro da faixa permitida ou descarta o slot vencido. Lotes, scripts, seleção de mídia, quantidade diária e capa permanecem com a mesma política. A sincronização individual de contas também ordena seus trabalhos por horário; não existe uma fila global única entre campanhas/threads distintas.

Checkpoint registra `processing_order=chronological-v1` e o minuto planejado. Ao retomar, o prefixo até `completed` fica intacto e só a cauda não processada é ordenada; o novo checkpoint é salvo antes de processar. Checkpoints antigos recebem minuto estável por slot, preservando os posts concluídos. Agendas já materializadas não são reescritas.

Trinta testes sintéticos aprovados, incluindo duas contas intercaladas, horários noturnos, estabilidade/repetição e retomada sem duplicação. Implantado na VPS, serviço reiniciado sem geração/envio em andamento na consulta prévia e HTTP 200 validado. Código enviado ao Git. Não houve benchmark com vídeos reais: número de trabalhos e tamanho dos lotes preservados; ordenação adiciona custo pequeno em comparação ao processamento, sem promessa de tempo idêntico.

A geração prepara slots, associa conta/mídia/capa/legenda e persiste ScheduledPost. A combinação campanha, conta e posição possui restrição de unicidade. O código mantém progresso e recuperação de geração interrompida; não duplicar registros ao retomar.

## Contas

CampaignAccount vincula contas à campanha. CampaignAccountExclusion registra contas removidas por falhas definitivas e impede reinserção automática inadequada; a reconexão por OAuth participa da recuperação. Sincronizar contas recém-conectadas não significa permitir publicação em conta inelegível.

Uma campanha pode ter escopo opcional de grupo salvo em `ApplicationSetting` com chave `campaign-account-group-<id>`. Quando existe, o setup e a sincronização automática de contas só vinculam membros aptos daquele grupo, comparando o nome sem diferença de maiúsculas/minúsculas. Sem essa chave, o comportamento anterior de incluir todas as contas aptas continua. A estimativa de sincronização também respeita o escopo. A regra de horários finitos permite campanhas pontuais com intervalos próprios; a preparação pode descartar faixas que vencerem antes de processar todos os vídeos.

## Pausa e cancelamento

A elegibilidade depende do estado da campanha e do post. Antes de alterar ações de pausa/cancelamento, verificar jobs já reivindicados e efeitos externos que podem ter ocorrido.

## Fontes e limites

- [`app/main.py`](<../app/main.py>)
- [`app/models.py`](<../app/models.py>)
- [`app/daily_schedule.py`](<../app/daily_schedule.py>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.

## Liberação por conta

O prazo específico de Conta tem prioridade sobre o global, sempre contado desde a vinculação. A agenda usa `campaign_sync_due_at`; o scheduler filtra prazos futuros em UTC antes de reservar e reconfere antes de iniciar upload. Alterar prazo preserva horários salvos/publicados; pendentes anteriores à liberação aguardam. A alteração não cria retroativamente slots que foram omitidos na geração. Consulte [Contas](contas_oauth.md#prazo-e-grupos-por-conta).

Desde 17/10/2026, liberação global/por conta admite dias fracionados sem truncamento (0.5 = 12h). Prazo continua em UTC e é convertido para o horário local nos consumidores já existentes. Não muda a quantidade diária inteira de Reels. Consulte prazos fracionados em Contas.
