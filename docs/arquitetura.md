# Arquitetura e interface

## Resumo

Visão do backend, frontend, banco e serviços. Consulte para localizar responsabilidades e entender o fluxo completo.

## Componentes

app/main.py expõe a API e coordena biblioteca, contas, campanhas, agenda, processamento, publicação e métricas. app/models.py define entidades SQLAlchemy; app/services.py prepara mídias e executa scripts. app/meta.py encapsula OAuth, chamadas oficiais e publicação. Gateway de mídia e túnel dão acesso temporário aos arquivos necessários à publicação.

frontend/src.tsx implementa a interface React: painel, contas, biblioteca, campanhas, agenda, métricas e atividade. O frontend chama a API; a existência de um botão não demonstra que credenciais, permissões ou rede estejam disponíveis.

## Caminho funcional

Importar mídia → conectar contas → criar campanha e seus vínculos/regras/scripts → processar saídas → gerar agenda → ativar execução → acompanhar tentativas e publicações → sincronizar resultados. Os estados persistidos permitem retomar e distinguir geração, execução e resultado.

## Limites

Vídeos ficam no sistema de arquivos; o banco guarda metadados e referências. A interface, API, processos de geração, scheduler e serviço público de mídia têm ciclos diferentes. Falha de um serviço não deve ser tratada como prova de perda do arquivo ou cancelamento remoto.

## Fontes e limites

- [`app/main.py`](<../app/main.py>)
- [`app/models.py`](<../app/models.py>)
- [`frontend/src.tsx`](<../frontend/src.tsx>)

Referência por leitura estática em 09/10/2026. O [mapa do código](mapa_codigo.md) localiza símbolos e linhas. Nenhuma integração real foi operada nesta rodada; a documentação não comprova disponibilidade de configuração, dispositivo, login ou serviço.
