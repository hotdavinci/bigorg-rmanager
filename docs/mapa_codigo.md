# Mapa do código — Rmanager

## Resumo

Índice extraído da árvore sintática, sem importar ou executar módulos. Lista classes, funções e parâmetros com linha de origem. Use para localizar implementação; nomes não comprovam caminhos ativos. Defaults e valores de configuração não são copiados.

## app/main.py

Fonte: [app/main.py](<../app/main.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `db` | `—` | 33 |
| `account_is_eligible` | `account, now` | 38 |
| `is_definitive_account_error` | `error` | 43 |
| `audit` | `session, event_type, message, campaign_id, account_id` | 47 |
| `cancel_account_from_active_campaigns` | `session, account, reason` | 50 |
| `parse_intervals` | `values` | 76 |
| `_clone_processed_for_schedule` | `session, campaign_id, original_media_id, seed_media, account_id, position` | 87 |
| `materialize_missing_schedule_for_account` | `session, campaign, account, not_before` | 99 |
| `account_campaign_sync_delay_days` | `session` | 142 |
| `schedule_account_campaign_sync` | `session, account` | 147 |
| `sync_account_to_active_campaigns` | `session, account, not_before, on_campaign` | 155 |
| `account_sync_progress_path` | `account_id` | 175 |
| `save_account_sync_progress` | `account_id, **values` | 178 |
| `load_account_sync_progress` | `account_id` | 185 |
| `estimated_account_sync_slots` | `session, account` | 191 |
| `run_account_campaign_sync_background` | `account_id` | 210 |
| `queue_account_campaign_sync` | `account_id` | 237 |
| `sync_due_connected_accounts` | `session` | 244 |
| `as_local_datetime` | `value` | 260 |
| `cache_reel_thumbnail` | `reel, source_url` | 274 |
| `cache_reel_video` | `reel, source_url` | 283 |
| `archive_published_reel_video` | `session, account_id, meta_media_id, source` | 332 |
| `sync_reel_insights` | `session` | 357 |
| `run_insights_sync_if_due` | `force` | 388 |
| `insights_scheduler` | `—` | 407 |
| `run_account_health_check` | `force` | 412 |
| `account_health_scheduler` | `—` | 456 |
| `is_definitive_publish_error` | `error` | 461 |
| `retry_delay` | `attempt_number` | 465 |
| `recover_stalled_claims` | `session, now` | 469 |
| `claim_due_posts` | `session, account_ids_in_flight, now, limit` | 481 |
| `publish_claimed_post` | `post_id, account_ids_in_flight, semaphore` | 503 |
| `scheduler` | `—` | 554 |
| `life` | `app` | 579 |
| `CampaignIn` | classe | 649 |
| `CampaignSetupIn` | classe | 650 |
| `ProcessIn` | classe | 651 |
| `ScheduleIn` | classe | 652 |
| `GenerateScheduleIn` | classe | 653 |
| `CampaignDefaultsIn` | classe | 654 |
| `LoginIn` | classe | 655 |
| `progress_file` | `campaign_id` | 657 |
| `save_generation_progress` | `campaign_id, **values` | 660 |
| `load_generation_progress` | `campaign_id` | 673 |
| `generation_cancelled` | `session, campaign_id` | 678 |
| `discard_processed_files_for_terminal_posts` | `session, campaign_id` | 684 |
| `purge_campaign` | `session, campaign_id` | 706 |
| `auth_status` | `request` | 745 |
| `auth_login` | `body, request` | 747 |
| `auth_logout` | `request` | 751 |
| `health` | `s` | 753 |
| `tunnel_status` | `—` | 755 |
| `restart_app` | `—` | 757 |
| `accounts` | `s` | 762 |
| `refresh_accounts_health` | `—` | 767 |
| `account_campaign_sync_settings` | `s` | 772 |
| `save_account_campaign_sync_settings` | `delay_days, s` | 776 |
| `oauth_start` | `s` | 782 |
| `oauth_url` | `s` | 788 |
| `oauth_callback` | `code, state, error, s` | 794 |
| `delete_account_safely` | `s, item` | 812 |
| `remove_cached_insight_files` | `paths` | 831 |
| `remove_accounts_bulk` | `account_ids, s` | 840 |
| `remove_account` | `account_id, s` | 851 |
| `dashboard` | `period, s` | 858 |
| `insight_views_chart` | `period, start, end, s` | 895 |
| `scheduled_posts` | `s` | 944 |
| `activity` | `s` | 959 |
| `activity_summary` | `s` | 987 |
| `saved_insight_winner_settings` | `session` | 995 |
| `InsightWinnerSettingsIn` | classe | 1002 |
| `get_insight_winner_settings` | `s` | 1007 |
| `update_insight_winner_settings` | `payload, s` | 1011 |
| `cached_insight_thumbnail` | `reel_id, s` | 1021 |
| `cached_insight_video` | `reel_id, s` | 1030 |
| `insight_reels` | `period, s` | 1041 |
| `request_insight_sync` | `—` | 1077 |
| `insight_status` | `s` | 1081 |
| `audit_log` | `limit, s` | 1085 |
| `clear_history` | `s` | 1089 |
| `retry_post_now` | `post_id, s` | 1110 |
| `media` | `kind, s` | 1118 |
| `refresh_media_thumbnails` | `s` | 1122 |
| `media_thumbnail` | `media_id, s` | 1129 |
| `stream_original_media` | `media_id, s` | 1139 |
| `remove_media` | `media_id, s` | 1149 |
| `remove_media_bulk` | `media_ids, s` | 1160 |
| `import_media` | `files, s` | 1178 |
| `import_campaign_cover` | `file` | 1188 |
| `caption_lists` | `s` | 1194 |
| `remove_caption_list` | `list_id, s` | 1196 |
| `import_caption_list` | `file, s` | 1202 |
| `scripts` | `s` | 1214 |
| `remove_script` | `script_id, s` | 1216 |
| `campaign_defaults` | `s` | 1229 |
| `save_campaign_defaults` | `body, s` | 1238 |
| `import_script` | `file, s` | 1245 |
| `campaigns` | `s` | 1249 |
| `campaign_progress` | `campaign_id, s` | 1256 |
| `create_campaign` | `body, s` | 1261 |
| `delete_campaign` | `campaign_id, s` | 1264 |
| `cancel_campaign` | `campaign_id, s` | 1280 |
| `setup_campaign` | `campaign_id, body, s` | 1288 |
| `run_processing` | `campaign_id, body, s` | 1307 |
| `campaign_executions` | `campaign_id, s` | 1311 |
| `schedule` | `campaign_id, body, s` | 1314 |
| `generate_schedule` | `campaign_id, body, s, background_claim` | 1320 |
| `run_schedule_background` | `campaign_id, body` | 1479 |
| `resume_interrupted_campaign_generations` | `—` | 1499 |
| `start_generation` | `campaign_id, body, s` | 1522 |
| `activate` | `campaign_id, s` | 1534 |

## app/models.py

Fonte: [app/models.py](<../app/models.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `CampaignStatus` | classe | 7 |
| `PostStatus` | classe | 9 |
| `Media` | classe | 11 |
| `InstagramAccount` | classe | 16 |
| `OAuthState` | classe | 21 |
| `Script` | classe | 24 |
| `Campaign` | classe | 27 |
| `CaptionList` | classe | 30 |
| `ApplicationSetting` | classe | 33 |
| `CampaignAccount` | classe | 36 |
| `CampaignAccountExclusion` | classe | 39 |
| `SchedulerLock` | classe | 43 |
| `AuditLog` | classe | 46 |
| `InstagramReel` | classe | 51 |
| `InstagramReelSnapshot` | classe | 54 |
| `CampaignSourceMedia` | classe | 57 |
| `CampaignScript` | classe | 60 |
| `CampaignScheduleRule` | classe | 63 |
| `ProcessedCover` | classe | 66 |
| `ScheduledPostCover` | classe | 69 |
| `PublicationAttempt` | classe | 72 |
| `ProcessingExecution` | classe | 75 |
| `ScheduledPost` | classe | 78 |

## app/services.py

Fonte: [app/services.py](<../app/services.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `commit_with_retry` | `session, attempts` | 15 |
| `sha` | `path` | 26 |
| `dirs` | `—` | 31 |
| `thumbnail` | `media, force` | 33 |
| `copy_media` | `src, original_name` | 45 |
| `process` | `session, campaign_id, source_ids` | 49 |
| `process_slot` | `session, campaign_id, source_id, slot_key` | 86 |
| `process_slots_batch` | `session, campaign_id, slots` | 127 |

## app/meta.py

Fonte: [app/meta.py](<../app/meta.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `safe_meta_error` | `response` | 18 |
| `require_config` | `—` | 32 |
| `cipher` | `—` | 38 |
| `encrypt` | `value` | 43 |
| `decrypt` | `value` | 44 |
| `authorization_url` | `state` | 48 |
| `exchange_code` | `code` | 55 |
| `profile` | `token` | 78 |
| `reels_with_views` | `account_id, token, limit` | 89 |
| `publish_reel` | `account_id, token, video_url, caption, cover_url` | 109 |
| `_publish_reel` | `account_id, token, video_url, caption, cover_url` | 118 |

## app/media_gateway.py

Fonte: [app/media_gateway.py](<../app/media_gateway.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `register_media` | `path, lifetime_minutes` | 14 |
| `download_media` | `token` | 24 |

## app/tunnel.py

Fonte: [app/tunnel.py](<../app/tunnel.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `QuickTunnel` | classe | 13 |
| `QuickTunnel.__init__` | `self` | 14 |
| `QuickTunnel.executable` | `self` | 22 |
| `QuickTunnel.start` | `self` | 25 |
| `QuickTunnel._read_output` | `self` | 49 |
| `QuickTunnel.public_url_for` | `self, path` | 61 |
| `QuickTunnel.stop` | `self` | 72 |
| `QuickTunnel.status` | `self` | 82 |

## app/config.py

Fonte: [app/config.py](<../app/config.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `Settings` | classe | 8 |
| `Settings.data_dir` | `self` | 52 |
| `Settings.cors_origins` | `self` | 55 |
| `data_path` | `relative_path` | 59 |
| `reload_runtime_settings` | `—` | 63 |

## app/db.py

Fonte: [app/db.py](<../app/db.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `Base` | classe | 6 |
| `sqlite_wal` | `conn, _` | 14 |

## app/launcher.py

Fonte: [app/launcher.py](<../app/launcher.py>).

| Símbolo | Parâmetros sem defaults | Linha |
|---|---|---|
| `already_running` | `—` | 7 |
| `main` | `—` | 14 |

## frontend/src.tsx

Fonte: [frontend/src.tsx](<../frontend/src.tsx>).

Arquivo não Python: consulte a fonte para detalhes de contrato/build.

## api/meta/connect.js

Fonte: [api/meta/connect.js](<../api/meta/connect.js>).

Arquivo não Python: consulte a fonte para detalhes de contrato/build.

## api/meta/callback.js

Fonte: [api/meta/callback.js](<../api/meta/callback.js>).

Arquivo não Python: consulte a fonte para detalhes de contrato/build.
