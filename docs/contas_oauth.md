# Contas, OAuth e credenciais

## Resumo

Conexão Meta, armazenamento de tokens, seleção/exclusão, grupos com título, apelidos individuais, prazo prioritário por conta e recuperação. Consulte ao alterar a tela de contas, autenticação e callbacks.

## Conexão

OAuth usa estado persistido, callback, troca de código e obtenção de perfil/token de longa duração. InstagramAccount guarda identificadores, validade, ativação e informações de saúde/sincronização. A configuração local determina versão Graph e credenciais; não registrar valores em documentação.

## Proteção

Tokens são criptografados com Fernet. Preservar a chave usada pelos registros existentes: substituí-la sem migração impede descriptografia. Logs e respostas não devem expor tokens ou segredos.

## Callback hospedado

Em 10/10/2026, `connect.hotvinci.cfd` passou a responder HTTPS: `/api/meta/connect` e `/api/meta/callback` retornaram 302 para as rotas correspondentes do backend existente. Novas credenciais Meta/Instagram fornecidas pelo usuário foram aplicadas somente no `.env` da VPS, preservando a chave de criptografia; callback atualizado para `https://connect.hotvinci.cfd/api/meta/callback` e endpoints mantidos na modalidade Instagram Login. Validação sintética confirmou client_id e redirect_uri sem iniciar OAuth. O início do OAuth recarrega as configurações, dispensando restart para essa troca. Reconexão real das contas e permissões ainda dependem da autorização do usuário; nenhuma conta foi reconectada neste teste. Em desenvolvimento, usar contas testadoras autorizadas. Não existe endpoint de webhook/verificação no projeto.

api/meta/connect.js e callback.js, além das referências de hospedagem, atendem o trecho público do OAuth. Backend local, callback público e aplicação Meta precisam concordar sobre URLs/configuração. O frontend não deve receber segredo de aplicação.

## Recuperação

Contas podem estar desativadas, com token vencido, erro definitivo ou sincronização pendente. Reconectar atualiza credenciais e pode permitir recuperação de vínculos excluídos. Este documento descreve o código local; requisitos e permissões atuais da plataforma precisam ser verificados na tarefa que operar OAuth.

## Seleção e exclusão na interface

A tela permite marcar contas individualmente e usar “Selecionar todas” para incluir somente as contas aptas visíveis (desde 17/10/2026). Quando todas estão marcadas, o controle passa a “Desmarcar todas”. “Excluir selecionadas” mostra a quantidade e abre a confirmação já existente antes de chamar `DELETE /api/meta/accounts` com a lista de IDs. A seleção é local à tela e remove IDs que deixam de aparecer na lista atualizada. A exclusão individual continua disponível; o botão “Apagar todas com erro” está oculto junto das contas inaptas.

A exclusão existente desconecta as contas no Rmanager, limpa suas credenciais, remove vínculos e cancela posts pendentes; preserva histórico de Reels e insights. Não exclui o perfil no Instagram. Em 10/10/2026, a alteração de interface passou por `npm --prefix frontend run build` (TypeScript e Vite); nenhuma conta real foi excluída e não houve validação visual ou implantação na VPS.

## Fontes e limites

- [`app/meta.py`](<../app/meta.py>)
- [`app/models.py`](<../app/models.py>)
- [`app/main.py`](<../app/main.py>)
- [`api/meta/connect.js`](<../api/meta/connect.js>)
- [`api/meta/callback.js`](<../api/meta/callback.js>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.

## Prazo e grupos por conta

Na tela Contas, selecione uma ou várias contas (ou todas/grupo) e aplique um prazo de 0 a 365 dias após `connected_at`. `posting_delay_days` nulo herda o padrão global; zero libera imediatamente; valor explícito tem prioridade. “Usar prazo global” remove a exceção. Alterar o prazo não reinicia a data de vinculação. A reconexão mantém a exceção, contando desde a nova vinculação conforme o OAuth existente.

Desde 21/10/2026, uma conta inédita conectada por OAuth recebe `posting_delay_days=0`, independentemente do padrão global já persistido. Assim ela entra na próxima faixa ainda disponível após validação e preparação. A reconexão de conta existente mantém o prazo específico anterior ou a herança global; nenhum registro anterior é reconfigurado automaticamente.

O título `account_group` organiza as contas, sem alterar autenticação, campanha ou prazo. É possível agrupar selecionadas, mover para um título existente, remover do grupo e renomear todas as integrantes. Títulos iguais formam um único grupo; não existem grupos vazios persistidos. Desde 17/10/2026, a listagem mostra somente integrantes aptas; contas com erro permanecem salvas, mas ocultas. Renomear o grupo mantém a operação sobre todas as integrantes, inclusive ocultas.

Salvar o padrão global recalcula a liberação das contas que o herdam, preservando exceções. Salvar prazo específico recalcula `campaign_sync_due_at` a partir da vinculação. Posts pendentes permanecem na fila e só podem ser reclamados/publicados após a liberação, mesmo se seu horário salvo for anterior. Não há regeneração automática de slots omitidos anteriormente. Publicados e envios já iniciados não são desfeitos.

Validação: build TypeScript/Vite e 36 testes sintéticos em staging isolado, incluindo bulk, fallback, zero, reconexão, validação e fila existente. Sem publicação real de teste.

## Apelido individual

Em Contas, cada conta possui campo Apelido e botão Salvar apelido. O título mostra apelido e @ original; vazio remove o apelido. Texto interno de até 120 caracteres, com espaços das extremidades removidos, persistido em `InstagramAccount.nickname` sem mudar username/display_name, vínculo Meta, grupo ou prazo. OAuth e checagem de saúde preservam o campo. Escopo visual desta entrega: listagem de Contas; outros relatórios continuam usando @. Migração SQLite aditiva com vazio padrão.

`PUT /api/meta/accounts/{account_id}/nickname` recebe `{nickname: string}` e retorna ID/apelido; conta ausente/excluída retorna 404. Trinta e sete testes sintéticos aprovados em staging, incluindo edição individual, remoção, limite e preservação dos demais campos. Build aprovado. Sem editar apelidos reais para teste.

## Classificação de indisponibilidade

Desde 16/10/2026, falhas isoladas de mídia/publicação não desativam uma conta apenas por conter OAuthException. Classificador compartilhado exige evidência de falha de autenticação/acesso, com tratamento de transitórios e contexto de verificação. Permissão de objeto/publicação isolada não equivale à perda de acesso da conta. Detalhes e validação em [Publicação](publicacao.md#falha-do-post-versus-falha-de-acesso-da-conta--16102026). Recuperação operacional deve validar identidade via perfil antes de reativar; não repetir automaticamente posts de horários passados.

## Prazos fracionados — 17/10/2026

Prazo global e exceção por conta aceitam números finitos entre 0 e 365 dias, incluindo frações: 0.25 = 6h, 0.5 = 12h, 1.5 = 36h. Campos HTML usam step any; API e ORM usam float sem truncamento, com NaN/infinito rejeitados. A contagem continua desde connected_at em UTC; exceção explícita tem prioridade e nulo herda global. Valores inteiros anteriores continuam válidos.

Novas colunas posting_delay_days usam REAL/Float. Em bancos SQLite legados, a afinidade INTEGER permite armazenar valores REAL, validado por roundtrip ORM; não há reconstrução ou descarte da tabela existente. A implantação não altera prazos configurados ou datas existentes por si só. Salvar uma nova configuração mantém o recálculo já existente dos consumidores afetados.

Build e 47 testes sintéticos aprovados em staging isolado, incluindo frações global/conta, prioridade, retorno ao global, valores não finitos e coluna INTEGER legada. Backend implantado, HTTP 200 e contrato fracionado confirmados. Sem editar configurações reais para teste ou publicar conteúdo.

## Vinculação visível e ordenação — 17/10/2026

A tela Contas mostra data/hora de `conectada_em`, registrada pelo callback OAuth em UTC e convertida para exibição. O backend atualiza esse campo ao reconectar; portanto representa a vinculação/reconexão atual, não criação do perfil Instagram. Contas aptas aparecem em ordem decrescente de vinculação dentro de cada grupo; os grupos seguem a ordem de sua integrante mais recente. Empates usam ID decrescente e datas ausentes ficam no fim.

Contas com erro/desconectadas ficam temporariamente ocultas, preservadas no banco/API e em relatórios existentes. Selecionar todas/grupo, contagens e operações em selecionadas consideram somente as visíveis. Seleção é podada quando a conta deixa de estar apta. Renomear grupo continua atingindo o grupo inteiro. Build TypeScript/Vite aprovado; alteração somente frontend, sem reinício da VPS ou mudanças de datas/contas reais.
