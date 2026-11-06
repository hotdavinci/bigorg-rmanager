# Scheduler, tentativas e publicação

## Resumo

Concorrência, limite total de Reels por conta, estados, protocolo Meta por conexão direta, retries e limpeza. Consulte para diagnosticar posts atrasados, repetidos ou falhos.

## Limite total por conta — 04/11/2026

Configurações permite definir um máximo global de Reels publicados com sucesso **por conta**, somando todas as campanhas e sem reinício diário. Zero desativa o limite. A contagem inclui publicações `PUBLISHED` anteriores ainda presentes no Rmanager; não consulta o total do perfil Instagram nem recupera histórico apagado antes desta implementação.

`app/reel_limits.py` lê `account_reel_limit` em `ApplicationSetting`. O total por conta usa `account-published-total-<id>`; sem esse registro, utiliza a quantidade local de posts `PUBLISHED`. No próximo sucesso, grava o total anterior mais um na mesma transação do post e da tentativa confirmados, antes da limpeza de arquivos. Limpeza de Atividade, exclusão de campanha e reinicialização de geração preservam o total antes de apagar posts. Reset de Insights não interfere. Falhas, tentativas e posts pendentes não contam.

O scheduler exclui contas no limite antes de reivindicar posts e o executor reconfere antes de iniciar o envio. A serialização existente por conta impede que duas tarefas do mesmo scheduler consumam a última vaga simultaneamente. Um envio que já começou pode concluir se o limite for reduzido durante sua execução; não se promete cancelamento de operações Meta em andamento. Persistem os limites anteriores do controle entre múltiplos processos e da reconciliação de respostas perdidas.

A conta mantém saúde, token, vínculos e fila existente; limite não é falha de autenticação. Os posts ficam pendentes e podem voltar a sair se o limite aumentar ou for desativado, respeitando as demais regras. A inclusão em campanhas, estimativa, geração e reposição também conferem o limite; veja [Campanhas](campanhas_agenda.md#limite-total-de-reels-por-conta--04112026). O contador não é zerado ao reconectar.

Validação local: 12 testes novos sintéticos aprovados; build TypeScript/Vite aprovado. A suíte ampliada executou 82 testes: 81 passaram e um teste anterior de conexão de mídia falhou por fixture sem `status` (`test_media_connections.py`), em trecho não alterado nesta entrega. Sem publicação real, sincronização externa, deploy ou leitura de dados/configuração reais.


Implantação em 05/11/2026: backend ativo na VPS e rota confirmada no OpenAPI (HTTP 200), com backup protegido de código. Entrada de novos trabalhos pausada temporariamente para drenar os envios em andamento e estados de campanha restaurados após a atualização. Build e 12 testes do candidato remoto aprovados; 81 testes passaram excluindo o teste anterior de mídia com fixture incompleta. Envio ao Git e confirmação do bundle público em acompanhamento; nenhum limite real alterado nem publicação manual de teste.

## Reivindicação

O scheduler recupera claims, busca posts elegíveis pelo horário e próxima tentativa e usa atualização condicional para reivindicar trabalho. Limita paralelismo global e mantém conjunto de contas em execução para evitar duas publicações simultâneas na mesma conta. Locks e estados persistidos não equivalem a uma transação distribuída com a Meta.

## Pipeline

Desde 15/10/2026, campanha com capa configurada exige vínculo e arquivo de capa processada para gerar `cover_url`; ausência interrompe a tentativa antes de criar o container Meta. A sincronização de novas contas passou a executar os scripts sobre vídeo/capa originais, em vez de clonar somente vídeo anterior. Ver [Biblioteca e processamento](biblioteca_processamento.md).

O post percorre estados como PENDING, CLAIMED, UPLOADING, WAITING_META, PUBLISHING e PUBLISHED. O executor verifica conta e mídia, registra PublicationAttempt, prepara URLs públicas, cria/aguarda/publica o conteúdo pela camada Meta e registra resultado. FAILED, SKIPPED, PAUSED e CANCELLED representam outros destinos.

## Erros

### Conexões diretas — 24/10/2026

Criação do container, consulta de status e publicação usam o mesmo cliente HTTPX sem proxy e com `trust_env=False`, inclusive quando existem variáveis de proxy no ambiente. OAuth, perfil, métricas Meta e cache de vídeos/capas também usam clientes diretos. A verificação TLS permanece ativa. A Meta continua buscando os arquivos pelas URLs públicas do gateway de mídia.

As antigas opções `META_PUBLISH_PROXY_URL`, `META_PUBLISH_PROXY_URLS` e `META_PUBLISH_PROXY_POSTS_PER_PROXY` não são lidas pelo backend. O arquivo histórico `data/proxy_assignments.sqlite3` foi preservado, mas não participa das publicações. Os helpers antigos de proxy foram removidos; o banco histórico de vínculos permanece guardado. Nenhuma publicação real foi disparada para testar a mudança.

### Protocolo de publicação conferido em 10/10/2026

`publish_claimed_post` seleciona `processed_media_id`, registra vídeo e capa opcional no gateway e chama `meta.publish_reel`. As URLs seguem `{public_media_base_url}/media/{token}` (ou o domínio Quick Tunnel), com tokens independentes gerados por `secrets.token_urlsafe(32)` e validade padrão de 120 minutos. O gateway entrega o arquivo via `FileResponse`, sem transcodificação; reiniciar perde os registros em memória.

A base padrão no código é `https://graph.instagram.com`; a versão vem da configuração. O protocolo implementado é por URL, sem upload retomável por blocos:

1. `POST /v{version}/{account_id}/media`, multipart/form-data com campos textuais `media_type=REELS`, `video_url`, `caption`, `share_to_feed=true`, `access_token` e `cover_url` opcional. Também envia `Authorization: Bearer {token}`. Não envia bytes de vídeo nessa chamada.
2. Lê `id` do container e faz até 40 consultas `GET /v{version}/{container}?fields=status_code,status&access_token=...`, com espera de 5 segundos enquanto não concluir. `FINISHED` libera publicação; `ERROR` e `EXPIRED` geram falha. HTTP malsucedido nesta consulta vira estado vazio e consome uma iteração. O cliente HTTP usa timeout de 120 segundos; as esperas de polling não são um limite total de duração.
3. `POST /v{version}/{account_id}/media_publish`, corpo application/x-www-form-urlencoded com `creation_id` e `access_token`. Retorna o `id` publicado ou, se ausente, o ID do container como fallback local.

O fluxo não persiste o ID do container antes da publicação, não retoma upload por blocos e não reconcilia uma resposta perdida antes de recriar container em nova tentativa. O padrão de configuração é três tentativas totais; o atraso implementado é 30, 60 e depois no máximo 120 segundos, conforme o número da tentativa. Classificação definitiva usa substrings da mensagem (incluindo `expired`, `oauth`, `401` e `403`); não é classificação estruturada dos códigos Meta. Após sucesso, tenta arquivar uma cópia exata do processado para métricas e limpa o processado sem outros usos pendentes e a capa.

Descrição do protocolo por leitura estática do código; não estabelece equivalência entre o arquivo entregue e as versões processadas pela Meta. A descrição é baseada em leitura do código; testes sintéticos de transporte não equivalem a uma publicação real.

Falhas transitórias podem reagendar conforme limite de tentativas e atraso. Falhas definitivas da conta podem excluir/cancelar seus vínculos. Erros de bloqueio SQLite são tratados para não encerrar todo o loop. Consultar tentativa, estado e auditoria antes de concluir que uma repetição é segura.

## Arquivos

Após sucesso, a implementação pode arquivar material de métricas e limpar vídeo processado quando não houver outro uso pendente, além da capa. A limpeza deve conferir referências e estados não terminais. Uma resposta local perdida pode coexistir com publicação remota concluída.

## Fontes e limites

- [`app/main.py`](<../app/main.py>)
- [`app/meta.py`](<../app/meta.py>)
- [`app/config.py`](<../app/config.py>)
- [`app/models.py`](<../app/models.py>)

Referência inicial por leitura estática em 09/10/2026, atualizada em 24/10/2026 para conexões diretas. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Testes simulados e verificação do serviço não equivalem a teste de publicação real.

## Falha do post versus falha de acesso da conta — 16/10/2026

`app/account_errors.py` interpreta código, subcódigo e `is_transient` do erro Meta, consumido por `is_definitive_publish_error` e `is_definitive_account_error`. O nome OAuthException, HTTP 401/403 isolado, permissão genérica, container EXPIRED e Unsupported post request não comprovam perda de acesso da conta. Erro de mídia 2207032 e erros transitórios não desativam a conta; ficam na política de tentativas do post. Cada tentativa recria o container conforme fluxo existente. Quando esgotadas, falha somente o post.

Códigos de autenticação 190/102 não transitórios e mensagens específicas de token/sessão inválida ou checkpoint podem tornar conta inapta. Códigos 10/200 só são tratados como falha de permissão da conta na verificação de perfil, não em uma publicação isolada. Erros estruturados desconhecidos são conservadoramente tratados como falha do post/verificação adiada. Isso distingue indisponibilidade operacional de uma prova de exclusão do perfil Instagram.

Quarenta e cinco testes sintéticos aprovados em staging isolado, incluindo erro realista 2207032: post volta a pendente com retry, conta permanece ativa, vínculo e próximo agendamento ficam intactos. Backend implantado com backup protegido em `/root/rmanager-account-errors-20261016/original`, HTTP 200 validado. Sem publicação manual de teste. Recuperação autorizada de conta afetada confirmou perfil/identidade via GET Meta antes de reativar e restaurar vínculo; 64 posts cancelados estavam no passado e permaneceram no histórico, sem replay automático.
