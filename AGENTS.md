# Rmanager: instruções do projeto

## Essencial

- Aplicação local de gestão e publicação de Reels; backend Python/FastAPI e interface React/Vite. Use os lançadores do projeto.
- Preserve dados, configurações, filas e formatos legados; evite alterações não relacionadas.
- Nunca leia ou exponha valores de arquivos reais de configuração, .env, bancos, sessões, históricos, identidades, chaves ou tokens para documentar o projeto. Descreva campos e comportamento; use dados sintéticos em testes.
- Tokens Meta são criptografados; preserve a chave de criptografia e os vínculos entre banco e arquivos. Scripts de processamento executam código confiável e não são sandbox.
- Publicação, OAuth, sincronização, túneis e agendamento têm efeitos externos; não execute para validar documentação.

## Documentação e memória

- Ao iniciar ou retomar uma tarefa, consulte [índice](docs/README.md) e [memória](docs/memoria.md). Não leia toda a documentação por padrão.
- Guie-se por títulos e resumos; leia apenas seções relevantes e dependências necessárias. Amplie quando houver dúvida, divergência ou impacto em outras partes.
- Confira informações técnicas no código antes de alterar componentes. Catálogo, nomes de funções e exemplos históricos não comprovam implementação ativa ou validação.
- Mantenha a documentação automaticamente nas tarefas futuras, sem pedido repetido: ao mudar comportamento, arquitetura ou integração, atualize o documento do assunto, seu resumo, índice e links afetados. Atualize a memória para decisões confirmadas, descobertas relevantes e pendências de continuidade.
- Corrija descrições superadas; evite duplicações e transcrições de chats. Propostas não são decisões. Diferencie implementação de testes efetivamente realizados e avise brevemente o que registrou.
- Cada documento deve começar com resumo que identifique assunto, escopo e quando consultar. O mapa de símbolos auxilia localizar fontes e não substitui explicação funcional.
- Mudanças em contratos compartilhados exigem conferir consumidores e suas referências, dentro do escopo autorizado. Discussão de proposta não autoriza implementação.
