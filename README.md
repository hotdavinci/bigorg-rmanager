# Reels Automation Manager

Painel local para organizar, processar e agendar Reels de contas profissionais, usando apenas a API oficial da Meta.

## Iniciar no Windows

Depois da preparação inicial, basta dar dois cliques em **`Iniciar Reels Manager.vbs`**. Ele abre o painel no navegador sem exibir terminal.

Para aplicar mudanças ou se o painel travar, dê dois cliques em **`Reiniciar Reels Manager.vbs`**.

Caso tenha copiado o projeto para outro computador, dê dois cliques em **`Preparar Reels Manager.bat`** uma vez. Depois utilize somente o iniciador.

O banco e todos os arquivos ficam em `data/`. Vídeos nunca são armazenados no SQLite.

## Segurança de scripts

Scripts Python importados possuem acesso aos arquivos que o seu usuário do Windows pode acessar. Importe e execute **somente scripts confiáveis**. O sistema copia os scripts para uma área de trabalho isolada por execução, mas isso não é uma sandbox de segurança absoluta.

## Meta

A publicação fica deliberadamente bloqueada até que a conta seja autenticada pelo OAuth oficial e a configuração da Meta esteja preenchida. Dê dois cliques em `Configurar Meta.vbs` para abrir o arquivo `.env` sem precisar usar terminal. A versão da Graph API vem do ambiente, para que possa acompanhar a documentação oficial atual da Meta sem alterar o código.
