# Contas, OAuth e credenciais

## Resumo

Cadastro de apps Meta, Instagram Login e Unified Login, links e reconexão por app, ponte OAuth para proxies, tokens, seleção e exclusão de contas, grupos, prazos e arquivamento por limite de Reels. Consulte ao alterar as telas de Contas e Apps Meta, a autenticação ou os callbacks.

## Páginas públicas para a Meta

Os campos de Política de Privacidade e Termos de Serviço no painel Meta apontam, respectivamente, para [Privacidade](https://connect.hotvinci.cfd/privacidade) e [Termos](https://connect.hotvinci.cfd/termos). A política inclui o canal para pedidos de exclusão de dados. A Vercel serve as duas páginas estáticas sem sessão do painel.

## Apps Meta e links por app — 09/11/2026

Em **Configurações → Apps Meta**, o administrador cadastra o Instagram App ID e o Instagram App Secret dos apps adicionais, consulta a contagem de contas vinculadas e copia o link de cada app. O cadastro numera os apps a partir de `app-2`. O `app-1` representa o app padrão da configuração legada. O secret de um app adicional pode ser substituído no painel e fica criptografado com a mesma chave Fernet dos tokens. O endereço de retorno exibido no painel deve ser autorizado no Instagram Login de cada app.

O link público `/api/meta/connect?app=app-2` inicia o OAuth pelo segundo app. Sem parâmetro, vale `app-1`. A ponte encaminha o apelido ao backend, que vincula a escolha ao estado de uso único, válido por 15 minutos. O callback resolve as credenciais no servidor com base nesse estado. Para direcionar novas contas quando um app lotar, o operador passa a compartilhar o link do próximo app.

A conta guarda o app que concluiu sua conexão. A ação **Reconectar** abre a autorização pelo app vinculado e exige o mesmo perfil. Contas legadas sem vínculo explícito usam `app-1` na reconexão. Esse padrão de compatibilidade não identifica retroativamente o emissor de tokens antigos. Contas com erro fora de Arquivadas aparecem na seção recolhida **Contas indisponíveis**, com a ação de reconectar. Uma autorização por outro app não substitui o vínculo de uma conta já reconhecida. Se o identificador mudar entre apps, o callback também recusa a criação quando encontra o mesmo nome de usuário em outro app.

O SQLite adiciona a tabela de apps e campos opcionais nas contas e estados OAuth na inicialização. Tokens e registros anteriores são preservados. Links de autorização pendentes emitidos pela versão anterior precisam ser gerados novamente após a atualização.

### Unified Login para apps adicionais

O cadastro e a opção **Editar login** permitem escolher **Unified Login**. Para o `app-2` já cadastrado e ainda sem contas, use o Meta App ID, o Meta App Secret e o Configuration ID da configuração salva no painel da Meta. Cadastre ali o mesmo endereço de retorno exibido pelo Rmanager. O link público continua com `?app=app-2`. O `app-1` usa a configuração legada do servidor.

No Unified Login, o callback troca o código pelo token de usuário do sistema e consulta as contas profissionais compartilhadas. Uma nova conexão exige que seja compartilhada somente a conta desejada. A reconexão procura a conta já vinculada entre as compartilhadas. O tipo de token registrado na conta define o host de perfil, publicação e métricas. Unified Login usa `graph.facebook.com` e Instagram Login usa o host legado. Alterar o tipo de login ou o ID de um app que já tem histórico de contas exige uma migração planejada com nova autorização. O painel permite atualizar somente o secret desses apps.

A configuração Meta deve autorizar leitura de perfil, publicação e insights conforme os recursos utilizados. Consulte [Configuração do Unified Login na Meta](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started).

## Contas com limite atingido — 04/11/2026

A tela Contas separa contas no limite na seção **Arquivadas**, ao final, ordenadas pela vinculação OAuth mais recente. Exibe total local publicado, limite, grupo e aviso `ARQUIVADA · LIMITE ATINGIDO`. Essas contas saem dos grupos disponíveis, da seleção em lote e do botão de abrir todas as aptas. Apelido, abertura individual e exclusão individual permanecem disponíveis. Contas no limite aparecem nessa seção mesmo se deixarem de estar saudáveis.

O arquivamento é uma classificação automática pelo campo `reel_limit_reached`, sem nova flag, migração, exclusão ou alteração de vínculos/filas. Aumentar/desativar o limite pode devolver uma conta saudável à lista disponível. `apta` mantém a semântica legada de saúde/conexão. O bloqueio existente não grava erro nem desativa a conta; reconexão não zera o total. O número de contas aptas no dashboard considera também o limite. Consulte [Publicação](publicacao.md#limite-total-por-conta--04112026) para origem do contador e desbloqueio da fila.

Validação: build frontend aprovado e renderização React com contas sintéticas confirmou partição, exclusão da seleção e arquivamento de conta no limite mesmo inativa. Sem alteração de contas reais.


## Conexão com proxy e DNS — 05/11/2026

O início e o callback de produção usam ponte server-side na Vercel: `api/meta/connect.js` consulta a API com redirect manual e devolve somente o destino HTTPS Instagram/Facebook permitido; `api/meta/callback.js` envia apenas os parâmetros OAuth escalares permitidos e retransmite status/HTML. O navegador deixa de visitar o domínio da API nessas duas etapas e continua usando seu proxy ao acessar Vercel/Instagram. A API conserva a criação/validação de state, troca do código e armazenamento criptografado de tokens. A Vercel recebe o código temporário no callback, como já ocorria; os handlers não o registram nem persistem e não recebem tokens de conta em respostas normais. Cache desativado e Referrer-Policy no-referrer.

Timeout de início de 15 s e callback de 55 s, com duração de função de 20/60 s em `vercel.json`. Não há retry automático do callback: um timeout pode ocorrer após a API consumir o código; conferir o painel antes de reconectar. O alvo do callback é obrigatório no deploy, sem fallback localhost nesta ponte. O pacote legado separado `vercel-oauth-callback/` não foi modificado.

Diagnóstico reproduziu timeout pelo nome da API usando os proxies afetados, enquanto o domínio Vercel respondeu. Forçar os IPv4 atuais da API mantendo SNI/domínio e validação TLS retornou resposta esperada por ambos. Isso isola falha de resolução/seleção de endereço no caminho do proxy; não identifica qual resolvedor originou a falha nem demonstra reputação ruim/bloqueio da VPS. Firewall VPS sem regras ativas e API local responsiva. Seis testes Node com dados sintéticos aprovados. Publicado em `6976da7`, Vercel success. Testes pelos dois proxies originais retornaram 302 direto a `www.instagram.com` em ~2,1–2,3 s, sem seguir o redirecionamento; callback com state sintético inexistente retornou 400 em ~2,1–2,4 s, sem salto à API. Nenhuma conta autorizada ou código real trocado na validação. Conclusão completa da autorização no navegador depende da ação do usuário.

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
