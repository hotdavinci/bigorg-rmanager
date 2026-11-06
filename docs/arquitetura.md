# Arquitetura e interface

## Resumo

Visão do backend, frontend, banco, serviços, disponibilidade e atualização dos formulários. Consulte para localizar responsabilidades e entender o fluxo completo.

## Componentes

app/main.py expõe a API e coordena biblioteca, contas, campanhas, agenda, processamento, publicação e métricas. app/models.py define entidades SQLAlchemy; app/services.py prepara mídias e executa scripts. app/meta.py encapsula OAuth, chamadas oficiais e publicação. Gateway de mídia e túnel dão acesso temporário aos arquivos necessários à publicação.

frontend/src.tsx implementa a interface React: painel, contas, biblioteca, campanhas, agenda, métricas e atividade. O frontend chama a API; a existência de um botão não demonstra que credenciais, permissões ou rede estejam disponíveis.

## Rascunhos de Configurações

O painel atualiza dados de acompanhamento a cada cinco segundos, mas carrega os valores editáveis de Configurações uma vez após autenticar. Enquanto a leitura inicial não termina, o formulário não aparece; uma falha oferece nova tentativa. Alterações de limite total de Reels por conta, prazo, janelas, estratégia, scripts, capa e legendas permanecem no estado local até o respectivo botão Salvar; somente a resposta desse salvamento substitui o rascunho. A atualização periódica não reaplica os valores persistidos durante a edição.

## Disponibilidade e atualização — 05/11/2026

A verificação de autenticação exibe estado de conexão e, após dez segundos sem resposta, oferece nova tentativa. Uma falha de rede não é tratada como logout. Consultas GET têm timeout de trinta segundos; escritas mantêm seu comportamento anterior. O acompanhamento periódico só começa após autenticar e aguarda terminar uma rodada antes de iniciar outra, evitando acumular consultas quando o backend demora.

`run_account_health_check` executa a rotina completa em uma thread dedicada por `asyncio.to_thread`: sessão SQLite e clientes HTTP são criados/usados/fechados dentro desse trabalho. Esperas por commit e retries dessa rotina deixam de bloquear o event loop HTTP e de mídia. A classificação de saúde, locks e cadência permanecem iguais; isso não migra todas as operações síncronas da aplicação nem elimina a possibilidade de contenção SQLite.

Agenda e Atividade usam `post_history_rows`, uma consulta com joins e a tentativa de maior ID por post. Preservam campos, posts sem conta encontrada, ordenação e o limite final de cem itens da Atividade, substituindo consultas individuais por post. Não há alteração de contrato, paginação ou descarte de histórico.

O diagnóstico por SSH encontrou a thread principal no commit inicial de `run_account_health_check` em três amostras e reproduziu timeout de autenticação no loopback. Também encontrou consultas concorrentes por post na agenda. Serviços ativos e HTTP 200 de HTML/OpenAPI não comprovam funcionamento do painel. Três testes sintéticos verificam responsividade durante commit bloqueado, consulta única da agenda e ordenação/tentativa do histórico; build aprovado. A suíte de 85 testes teve 84 aprovados e uma falha anterior em fixture de mídia sem campo `status`. Backend implantado com backup e reinício controlado: autenticação local em ~2 ms, agenda em ~98 ms e autenticação pública em ~0,60 s. Mídia voltou a responder 404 esperado na raiz. Frontend ainda aguarda publicação nesta etapa; nenhuma publicação Meta/OAuth foi executada para validar.

## Caminho funcional

Importar mídia → conectar contas → criar campanha e seus vínculos/regras/scripts → processar saídas → gerar agenda → ativar execução → acompanhar tentativas e publicações → sincronizar resultados. Os estados persistidos permitem retomar e distinguir geração, execução e resultado.

## Limites

Vídeos ficam no sistema de arquivos; o banco guarda metadados e referências. A interface, API, processos de geração, scheduler e serviço público de mídia têm ciclos diferentes. Falha de um serviço não deve ser tratada como prova de perda do arquivo ou cancelamento remoto.

## Fontes e limites

- [`app/main.py`](<../app/main.py>)
- [`app/models.py`](<../app/models.py>)
- [`frontend/src.tsx`](<../frontend/src.tsx>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.
