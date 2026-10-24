# Biblioteca e processamento

## Resumo

Importação, cópias, capas, scripts e isolamento de trabalho. Consulte ao mudar preparação de conteúdo ou diagnosticar geração.

## Importação

A biblioteca copia vídeos aceitos, atribui identificadores e registra hash e localização. O arquivo importado serve de origem; a campanha relaciona fontes e configura processamento, capas e legendas.

## Scripts

Scripts associados à campanha são ordenados por posição. Cada execução trabalha em diretório próprio com cópias da mídia, capa e script, executando Python em subprocesso com timeout. Saídas e erros são registrados com limite de tamanho. Esses scripts possuem os privilégios do processo; isolamento de pasta não é isolamento de segurança.

Em 24/10/2026, o script exibido como `cleanM.py` foi substituído pelo arquivo local `D:\• scripts\• clean\• cleanM.py`. Na execução pelo Rmanager, a opção `--no-rename` preserva os nomes temporários que vinculam saídas, capas e posts nos lotes. A opção fica registrada em `ApplicationSetting` como lista JSON para esse script; outros scripts conservam seus argumentos anteriores. O script não foi executado durante a troca.

## Detecção e resultados

Desde 15/10/2026, os lotes da geração de campanha são preenchidos por horário planejado, intercalando contas; a execução dos scripts dentro de cada lote permanece igual. Ver [ordem e recuperação da agenda](campanhas_agenda.md).

O serviço identifica arquivos criados ou alterados usando nomes/hashes e registra resultados no banco. process_slot prepara a saída de um post; process_slots_batch atende lotes. Evite compartilhar diretórios de trabalho que misturem resultados de campanhas.

## Exclusão da biblioteca — 24/10/2026

A exclusão individual e em lote usam a mesma regra. Uma mídia original selecionada sai da Biblioteca e é desvinculada das campanhas; posts processados já agendados continuam preservados. Se cópias processadas ou capas ainda apontam para o original, o registro fica marcado como excluído para manter essas chaves históricas, mas o arquivo original é removido do disco. Mídias sem dependências têm registro e arquivo removidos. Durante processamento em andamento, o arquivo é conservado para não interromper o lote e removido pela limpeza periódica quando não houver geração em curso; a interface informa essa exceção. Novas configurações de campanha não aceitam mídias excluídas.

Testes sintéticos com SQLite e chaves estrangeiras cobrem exclusão vinculada a campanha/post, exclusão livre, seleção duplicada e processamento em andamento. Nenhuma mídia real foi apagada para validar a alteração.

## Recuperação

### Vídeo e capa na sincronização — corrigido em 15/10/2026

Antes da correção, a entrada de uma conta numa campanha ativa copiava um vídeo processado anterior (sem restringir a campanha de origem), sem rodar novamente os scripts e sem criar os vínculos da capa. Isso podia reutilizar uma transformação antiga e levar `cover_url` vazio, mesmo com capa configurada. O helper legado `_clone_processed_for_schedule` permanece definido, mas não é chamado pela sincronização atual.

`materialize_missing_schedule_for_account` agora monta slots futuros ausentes e chama `process_slots_batch` em lotes, partindo do vídeo original e da capa original da campanha. Executa os scripts associados em ordem, respeitando o tamanho de lote. Cada resultado recebe sua própria mídia processada e, se configurada, sua própria `ProcessedCover`/`ScheduledPostCover`. Sem saída de capa processada, a geração falha explicitamente; não copia silenciosamente a capa original nem publica sem ela. Post existente não é recriado; processamento que ultrapasse o limite de horário do slot não cria post passado.

`publish_claimed_post` também exige URL de capa disponível quando a campanha possui capa configurada, interrompendo antes de chamar a Meta se o vínculo/arquivo estiver ausente. A limpeza após sucesso continua removendo apenas as saídas descartáveis; original permanece. Não altera Reels já publicados no Instagram. Na verificação prévia à implantação, não havia posts pendentes afetados para recuperar.

Implantação na VPS e código enviado ao Git, com backup de código `/root/rmanager-covers-20261015/original`. Vinte e três testes sintéticos aprovados, incluindo execução real de script sintético em arquivos temporários, vídeo/capa resultantes por post, falha quando a capa não é processada, encaminhamento da URL e bloqueio de envio sem capa. Serviço reiniciado e HTTP 200 confirmado. Nenhum script de usuário foi executado como teste, nenhuma publicação real foi disparada e a aparência dos resultados reais não foi comparada nesta validação.

Geração usa progresso persistido e trata interrupções. Antes de repetir, distinguir execução incompleta, arquivo já criado e registro já confirmado. Capas processadas e vínculos de capa por post têm entidades próprias. Não remover originais para limpar saídas temporárias.

## Fontes e limites

- [`app/services.py`](<../app/services.py>)
- [`app/main.py`](<../app/main.py>)
- [`app/models.py`](<../app/models.py>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.
