# Documentação e memória — Rmanager

## Resumo

Índice por assunto para usuário e agentes. Comece por este mapa e pela memória; escolha referências pelo resumo e leia somente detalhes necessários. Regras essenciais ficam no [AGENTS.md](../AGENTS.md).

## Mapa de consulta

| Documento | Escopo / quando consultar |
|---|---|
| [Arquitetura e interface](arquitetura.md) | Visão do backend, frontend, banco, serviços e atualização dos formulários. Consulte para localizar responsabilidades e entender o fluxo completo. |
| [Biblioteca e processamento](biblioteca_processamento.md) | Importação, exclusão da biblioteca, processamento de vídeo/capa por post, scripts e isolamento de trabalho. Consulte ao mudar preparação de conteúdo ou diagnosticar geração. |
| [Campanhas e geração de agenda](campanhas_agenda.md) | Campanha recorrente de agora até agora + 24 horas com janelas e quantidades configuráveis, campanhas pontuais, escopo opcional por grupo, entrada tardia, regras legadas e recuperação. Consulte para alterar planejamento. |
| [Scheduler, tentativas e publicação](publicacao.md) | Concorrência, distinção entre falha de post/conta, URLs, chamadas à Meta, conexões diretas com a Meta, retries e limpeza. Consulte para configurar publicação ou diagnosticar falhas. |
| [Contas, OAuth e credenciais](contas_oauth.md) | Conexão Meta, tokens, seleção de aptas, data/ordem da vinculação, exclusão, grupos, apelidos individuais, prazo fracionado prioritário por conta e recuperação. Consulte ao alterar a tela de contas, autenticação e callbacks. |
| [Gateway de mídia, túneis e hospedagem](midia_publica.md) | URLs temporárias para vídeos/capas e separação de portas. Consulte ao diagnosticar acesso externo e deploy. |
| [Métricas locais — MVP](../tools/metrics-local/README.md) | Painel web no PC, importação de contas aptas, histórico preservado, horários de vinculação/inativação detectada e coleta pública sem vídeos. Consulte para abrir o programa e diagnosticar disponibilidade dos contadores. |
| [Métricas, atividade e auditoria](metricas_auditoria.md) | Sincronização, snapshots, reset local com corte temporal e auditoria. Consulte ao mudar relatórios ou reiniciar o histórico. |
| [Persistência, inicialização e validação](persistencia_operacao.md) | Dados, dependências, lançadores e limites da verificação. Consulte antes de manutenção local. |
| [Contratos e rotas da API](contratos_api.md) | Campos e tipos sem valores reais, mais rotas ou variantes encontradas estaticamente. Consulte para localizar contratos antes de mudar formato/API. |
| [Mapa do código](mapa_codigo.md) | Módulos, classes, funções, parâmetros e localização no código selecionado |
| [Memória](memoria.md) | Preferências, decisões confirmadas e continuidade |

## Referências anteriores

- [Apresentação original](../README.md)
- [Hospedagem](../HOSPEDAGEM.md)
- [Callback OAuth hospedado](../vercel-oauth-callback/README.md)

## Manutenção automática

Atualize o tópico afetado a cada mudança de comportamento. Revise resumo, índice e links; registre decisões e pendências na memória. Não acumule versões contraditórias. Integrações devem identificar fornecedor, consumidor e dados compartilhados.

## Alcance da rodada — 09/10/2026

Leitura estática de fontes locais; sem ler dados reais, operar dispositivos/VMs, gerar conteúdo externo, enviar mensagens, publicar ou reiniciar serviços. Links e mapas verificados documentalmente. Testes citados são referências, não resultados atuais. Confira o código ao alterar cada componente.
