# Contratos e rotas da API

## Resumo

Campos e tipos sem valores reais, preferências em lote de contas e rotas da API. Consulte para localizar contratos antes de mudar formato/API.

## Como usar

Checkpoint de geração desde 15/10/2026 inclui `processing_order=chronological-v1` e `planned_minute` inteiro em cada trabalho ainda não processado. Recuperação de formato anterior preenche apenas a cauda após `completed`, sem alterar prefixo ou posts existentes. DTOs públicos de quantidade/intervalos permanecem iguais; detalhes em [Campanhas e agenda](campanhas_agenda.md).

### Agendamento por quantidade — 14/10/2026

`CampaignSetupIn`, `GenerateScheduleIn` e `CampaignDefaultsIn` herdam `QuantityScheduleIn`: `reels_per_day: int | None` (1–1440), `intervals: list[str]`, `start_date: date | None` e `days: int | None`. Novas campanhas enviam uma lista de janelas recorrentes e estratégia/mídias/scripts; a API preenche data/dias internos e retorna `schedule.recurring=true`, `schedule.start_date=null`, `schedule.days=null`. O padrão inicial é 08:30–09:30, 11:30–12:30 e 17:30–18:30 com 12–18 Reels por conta/janela e horizonte móvel de 24 horas. Os marcadores usam o campo legado sem migração. `recurring:windows:12-18`, `windows:12-18` finito, `daily:N` e faixas antigas continuam aceitos; os finitos ainda exigem data/dias. Checkpoint e recuperação conservam a regra. Consumidores conferidos: frontend de campanhas/defaults/modal de agenda, setup/geração, sincronização de contas e recuperação/reposição em `app/main.py`; helpers em `app/daily_schedule.py`.

O escopo opcional por grupo é interno: `ApplicationSetting` usa a chave `campaign-account-group-<id>` e o nome do grupo como valor. Não altera o corpo das rotas; quando presente, `setup` e a sincronização automática limitam vínculos a contas aptas do grupo. Ausente, vale a inclusão legada de todas as contas aptas. Consulte [Campanhas e agenda](campanhas_agenda.md#contas).

Janelas recorrentes configuráveis usam um item `recurring:window:HH:MM-HH:MM:min-max` por faixa em `intervals`, sem novo campo ou migração. A API valida horário, quantidade, limite de 24 faixas e ausência de sobreposição. O marcador fixo anterior continua aceito. Setup, geração, defaults, resposta de campanhas, recuperação e reposição consomem a mesma lista; veja [Campanhas e agenda](campanhas_agenda.md#campanha-recorrente--21102026).

Inventário estático para localizar contratos. Campos e caminhos não demonstram autenticação, semântica completa, execução ativa ou compatibilidade remota. Consulte o tópico funcional e a implementação antes de alterar.

## CampaignIn — linha 649

| Campo | Tipo declarado |
|---|---|
| `name` | `str` |
| `description` | `str` |
| `timezone` | `str` |
| `script_id` | `int \| None` |

## CampaignSetupIn — linha 650

| Campo | Tipo declarado |
|---|---|
| `account_ids` | `list[int]` |
| `source_ids` | `list[int]` |
| `script_ids` | `list[int]` |
| `start_date` | `date` |
| `days` | `int` |
| `intervals` | `list[str]` |
| `strategy` | `str` |
| `cover_path` | `str` |
| `caption_list_id` | `int \| None` |
| `caption_text` | `str` |

## ProcessIn — linha 651

| Campo | Tipo declarado |
|---|---|
| `source_ids` | `list[int]` |

## ScheduleIn — linha 652

| Campo | Tipo declarado |
|---|---|
| `account_id` | `int` |
| `processed_media_id` | `int` |
| `caption` | `str` |
| `scheduled_for` | `datetime` |
| `position` | `int` |

## GenerateScheduleIn — linha 653

| Campo | Tipo declarado |
|---|---|
| `start_date` | `date` |
| `days` | `int` |
| `intervals` | `list[str]` |
| `strategy` | `str` |

## CampaignDefaultsIn — linha 654

| Campo | Tipo declarado |
|---|---|
| `intervals` | `list[str]` |
| `days` | `int` |
| `strategy` | `str` |
| `script_ids` | `list[int]` |
| `cover_path` | `str` |
| `caption_list_id` | `int \| None` |
| `caption_text` | `str` |

## LoginIn — linha 655

| Campo | Tipo declarado |
|---|---|
| `email` | `str` |
| `password` | `str` |

## InsightWinnerSettingsIn — linha 1002

| Campo | Tipo declarado |
|---|---|
| `limit` | `int` |
| `minimum_views` | `int` |

## Rotas declaradas

| Método | Caminho | Handler | Linha |
|---|---|---|---|
| GET | `/api/auth/status` | `auth_status` | 745 |
| POST | `/api/auth/login` | `auth_login` | 747 |
| POST | `/api/auth/logout` | `auth_logout` | 751 |
| GET | `/api/health` | `health` | 753 |
| GET | `/api/tunnel/status` | `tunnel_status` | 755 |
| POST | `/api/app/restart` | `restart_app` | 757 |
| GET | `/api/meta/accounts` | `accounts` | 762 |
| POST | `/api/meta/accounts/refresh-health` | `refresh_accounts_health` | 767 |
| GET | `/api/account-campaign-sync-settings` | `account_campaign_sync_settings` | 772 |
| PUT | `/api/account-campaign-sync-settings` | `save_account_campaign_sync_settings` | 776 |
| GET | `/api/meta/oauth/start` | `oauth_start` | 782 |
| GET | `/api/meta/oauth/url` | `oauth_url` | 788 |
| GET | `/api/meta/oauth/callback` | `oauth_callback` | 794 |
| DELETE | `/api/meta/accounts` | `remove_accounts_bulk` | 840 |
| DELETE | `/api/meta/accounts/{account_id}` | `remove_account` | 851 |
| GET | `/api/dashboard` | `dashboard` | 858 |
| GET | `/api/insights/views-chart` | `insight_views_chart` | 895 |
| GET | `/api/scheduled-posts` | `scheduled_posts` | 944 |
| GET | `/api/activity` | `activity` | 959 |
| GET | `/api/activity/summary` | `activity_summary` | 987 |
| GET | `/api/insights/settings` | `get_insight_winner_settings` | 1007 |
| PUT | `/api/insights/settings` | `update_insight_winner_settings` | 1011 |
| GET | `/api/insights/reels/{reel_id}/thumbnail` | `cached_insight_thumbnail` | 1021 |
| GET | `/api/insights/reels/{reel_id}/video` | `cached_insight_video` | 1030 |
| GET | `/api/insights/reels` | `insight_reels` | 1041 |
| POST | `/api/insights/sync` | `request_insight_sync` | 1077 |
| GET | `/api/insights/status` | `insight_status` | 1081 |
| GET | `/api/audit` | `audit_log` | 1085 |
| DELETE | `/api/activity` | `clear_history` | 1089 |
| POST | `/api/scheduled-posts/{post_id}/retry-now` | `retry_post_now` | 1110 |
| GET | `/api/media` | `media` | 1118 |
| POST | `/api/media/refresh-thumbnails` | `refresh_media_thumbnails` | 1122 |
| GET | `/api/media/{media_id}/thumbnail` | `media_thumbnail` | 1129 |
| GET | `/api/media/{media_id}/stream` | `stream_original_media` | 1139 |
| DELETE | `/api/media/{media_id}` | `remove_media` | 1149 |
| DELETE | `/api/media` | `remove_media_bulk` | 1160 |
| POST | `/api/media/import` | `import_media` | 1178 |
| POST | `/api/campaign-covers/import` | `import_campaign_cover` | 1188 |
| GET | `/api/caption-lists` | `caption_lists` | 1194 |
| DELETE | `/api/caption-lists/{list_id}` | `remove_caption_list` | 1196 |
| POST | `/api/caption-lists/import` | `import_caption_list` | 1202 |
| GET | `/api/scripts` | `scripts` | 1214 |
| DELETE | `/api/scripts/{script_id}` | `remove_script` | 1216 |
| GET | `/api/campaign-defaults` | `campaign_defaults` | 1229 |
| PUT | `/api/campaign-defaults` | `save_campaign_defaults` | 1238 |
| POST | `/api/scripts/import` | `import_script` | 1245 |
| GET | `/api/campaigns` | `campaigns` | 1249 |
| GET | `/api/campaigns/{campaign_id}/progress` | `campaign_progress` | 1256 |
| POST | `/api/campaigns` | `create_campaign` | 1261 |
| DELETE | `/api/campaigns/{campaign_id}` | `delete_campaign` | 1264 |
| POST | `/api/campaigns/{campaign_id}/cancel` | `cancel_campaign` | 1280 |
| PUT | `/api/campaigns/{campaign_id}/setup` | `setup_campaign` | 1288 |
| POST | `/api/campaigns/{campaign_id}/process` | `run_processing` | 1307 |
| GET | `/api/campaigns/{campaign_id}/executions` | `campaign_executions` | 1311 |
| POST | `/api/campaigns/{campaign_id}/schedule` | `schedule` | 1314 |
| POST | `/api/campaigns/{campaign_id}/generate-schedule` | `generate_schedule` | 1320 |
| POST | `/api/campaigns/{campaign_id}/start-generation` | `start_generation` | 1522 |
| POST | `/api/campaigns/{campaign_id}/activate` | `activate` | 1534 |

## Fontes e limites

- [`app/main.py`](<../app/main.py>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.

## Preferências em lote de contas

`PUT /api/meta/accounts/preferences`: `account_ids` (1–10.000 IDs, repetidos deduplicados), `posting_delay_days` opcional (número finito 0–365, aceitando frações, ou nulo para herdar), `account_group` opcional (até 120 caracteres, vazio remove). Campos omitidos são preservados. Todos os IDs precisam existir e não estar excluídos; validação ocorre antes das alterações. Retorna `updated`.

`GET /api/meta/accounts` acrescenta `posting_delay_days`, `effective_delay_days` e `account_group`. A rota global de prazo permanece compatível e recalcula somente contas sem exceção.

## Apelidos individuais de contas

`GET /api/meta/accounts` inclui `nickname` (string, vazio se não configurado). `PUT /api/meta/accounts/{account_id}/nickname` recebe `nickname` obrigatório, máximo 120 caracteres; trim na persistência, vazio remove. Retorna `id` e `nickname`. Não altera contratos de username/nome ou preferência em lote. Contas excluídas/ausentes retornam 404.

## Prazos fracionados — 17/10/2026

Prazo global e exceção por conta aceitam números finitos entre 0 e 365 dias, incluindo frações: 0.25 = 6h, 0.5 = 12h, 1.5 = 36h. Campos HTML usam step any; API e ORM usam float sem truncamento, com NaN/infinito rejeitados. A contagem continua desde connected_at em UTC; exceção explícita tem prioridade e nulo herda global. Valores inteiros anteriores continuam válidos.

Novas colunas posting_delay_days usam REAL/Float. Em bancos SQLite legados, a afinidade INTEGER permite armazenar valores REAL, validado por roundtrip ORM; não há reconstrução ou descarte da tabela existente. A implantação não altera prazos configurados ou datas existentes por si só. Salvar uma nova configuração mantém o recálculo já existente dos consumidores afetados.

Build e 47 testes sintéticos aprovados em staging isolado, incluindo frações global/conta, prioridade, retorno ao global, valores não finitos e coluna INTEGER legada. Backend implantado, HTTP 200 e contrato fracionado confirmados. Sem editar configurações reais para teste ou publicar conteúdo.
