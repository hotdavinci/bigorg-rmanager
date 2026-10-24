# Persistência, inicialização e validação

## Resumo

Dados, dependências, lançadores e limites da verificação. Consulte antes de manutenção local.

## Dados

SQLAlchemy/SQLite armazenam entidades e relacionamentos; vídeos e capas ficam em arquivos. Backup precisa manter coerência entre banco, referências, arquivos e chave de criptografia. .env e bancos reais não são fontes de exemplos.

## Inicialização

Na VPS, desde 10/10/2026 o serviço Rmanager tem override systemd `Environment=TZ=America/Sao_Paulo` em `/etc/systemd/system/reels-manager.service.d/timezone.conf`. O host permanece UTC. Geração/scheduler usam `datetime.now()`/`date.today()` sem timezone, portanto dependem do fuso do processo; registros explicitamente UTC continuam usando `datetime.utcnow()`. Correção validada pelo ambiente do processo reiniciado e HTTP 200, sem alterar datas no banco ou regenerar campanhas. Preservar override em reinstalações. Campanhas de outros fusos não foram validadas.

Use os lançadores Windows do projeto para preparar/iniciar/reiniciar conforme README. O backend usa Python e dependências declaradas; frontend possui instalação/build próprios. Deploy inclui configurações de serviço e callback hospedado. Não confundir frontend compilado com API executando.

## Mudanças

Preservar restrições de unicidade, estados legados e referências antes de migração. Mudança em horários, retries ou elegibilidade exige conferir geração e scheduler. Não regenerar agenda ativa incidentalmente.

## Validação

Existem testes de recuperação de geração, sincronização de contas de campanha e conexões de mídia. Não foram executados nesta rodada. Também não houve OAuth, upload, publicação, túnel ou deploy. Validar funcionalmente com dados sintéticos e serviços simulados quando a tarefa exigir; ações externas dependem do escopo autorizado.

## Fontes e limites

- [`app/config.py`](<../app/config.py>)
- [`app/db.py`](<../app/db.py>)
- [`app/launcher.py`](<../app/launcher.py>)
- [`app/models.py`](<../app/models.py>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.
