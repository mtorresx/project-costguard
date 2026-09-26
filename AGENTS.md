<!-- reflex managed begin (do not edit inside this block; add custom content outside the markers) -->
# Agents

This project uses the **Reflex agent skills** — up-to-date knowledge for building full-stack Python web apps with [Reflex](https://reflex.dev). Install them first, then use them as described below.

## Installing the Skills

Before working on this project, make sure the Reflex skills are available to you.

### Claude Code

If the skills are not already available, install them yourself by running these shell commands:

```bash
claude plugin marketplace add reflex-dev/agent-skills
claude plugin install reflex@reflex-agent-skills
```

Newly installed plugins load on the next session. After installing, tell the user to restart the session so the skills auto-load; until then, read the skill files directly from `~/.claude/plugins/` when you need them.

### Other agents (Cursor, OpenCode, Codex, Pi)

```
npx skills add reflex-dev/agent-skills
```

Or clone https://github.com/reflex-dev/agent-skills and copy the `skills/` folders into your agent's skill directory (see the repo README for paths).

### Verifying

Before writing or editing any Reflex code, confirm these three skills are available: `reflex-docs`, `setup-python-env`, and `reflex-process-management`. If they are not, STOP and run the install step above — do not proceed without them.

## Using the Skills

### Reflex documentation

For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs.

### Initializing a new Reflex project

When starting a new Reflex project or setting up a development environment, you **must** follow the **setup-python-env** skill before doing anything else.

Do not skip any steps. Do not assume a virtual environment or Reflex is already available — always verify first by following the skill's instructions in order.

After the environment is ready and Reflex is installed, run:

```bash
reflex init
```

Then proceed with the user's request.

### Managing a Reflex process

When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps.
<!-- reflex managed end -->


# Regras do Projeto CostGuard

## Idioma

Utilizar português brasileiro na documentação do projeto, nos artefatos OpenSpec e nas explicações destinadas ao grupo.

Nomes técnicos, identificadores, comandos, nomes de bibliotecas, APIs e termos próprios das tecnologias podem permanecer no idioma original quando apropriado.

## Contexto e documentação

Antes de realizar alterações significativas, consultar os documentos de contexto do projeto disponíveis em `docs/` e os artefatos OpenSpec aplicáveis à mudança.

Não inventar requisitos, regras de negócio, entidades ou comportamentos que não estejam definidos na documentação ou na change em execução.

Quando houver ambiguidade, conflito entre documentos ou informação necessária ausente, interromper a implementação e solicitar esclarecimento.

Não alterar decisões de domínio, arquitetura ou escopo sem aprovação explícita.

## Arquitetura

O frontend do projeto deve ser implementado exclusivamente com Reflex.

Utilizar os mecanismos próprios do Reflex para componentes, estado, eventos, páginas, rotas e interação.

Não introduzir React, Vue, Angular ou outra tecnologia de frontend para substituir ou complementar o Reflex sem uma alteração arquitetural explicitamente aprovada.

O backend do projeto utiliza Xano.

Regras de negócio, autorização e validações de segurança que não podem ser confiadas ao cliente devem ser aplicadas no backend.

O frontend não deve ser considerado mecanismo de segurança.

## Desenvolvimento

O projeto deve ser desenvolvido incrementalmente utilizando OpenSpec.

Mudanças funcionais ou técnicas relevantes devem ser especificadas antes da implementação.

Seguir o ciclo de desenvolvimento definido para o projeto:

1. Explore
2. Propose
3. Review
4. Apply
5. Archive

Não implementar funcionalidades fora do escopo da change atual sem justificativa e aprovação.

Reutilizar código existente quando apropriado e evitar duplicação desnecessária.

Não modificar funcionalidades não relacionadas à mudança atual.

Quando uma decisão necessária não estiver prevista na documentação ou na change, interromper a implementação em vez de improvisar uma solução.

## Segurança

Não armazenar senhas, tokens, chaves de API ou outros segredos no código-fonte, documentação versionada ou frontend.

Credenciais utilizadas para integração com provedores cloud devem possuir apenas as permissões necessárias ao funcionamento definido pelo projeto.

Autorização não deve depender exclusivamente de controles visuais ou verificações realizadas no frontend.

Nenhum segredo deve ser incluído em arquivos destinados ao repositório Git.

## Xano

Utilizar o Xano Developer MCP para consultar documentação e validar XanoScript quando necessário.

Não presumir sintaxe ou comportamento específico do Xano quando houver possibilidade de consultar a documentação oficial ou o Developer MCP.

Utilizar o Xano CLI para sincronização entre os arquivos locais e o workspace Xano.

Antes de enviar alterações ao Xano, revisar as modificações e utilizar mecanismos de validação ou `dry-run` quando disponíveis.

Evitar operações destrutivas ou alterações fora do escopo da change atual.

## Reflex

Antes de escrever ou alterar código Reflex, utilizar as Agent Skills do Reflex quando estiverem disponíveis no agente utilizado.

Consultar documentação atualizada do Reflex para componentes, State, eventos, rotas, autenticação e demais recursos específicos do framework.

O projeto utiliza `venv` e `pip` para gerenciamento do ambiente Python e dependências.

Não introduzir `uv`, Poetry, Conda ou outro gerenciador de ambiente ou dependências sem uma decisão explícita do projeto.

## Testes e verificação

Mudanças funcionais devem possuir uma estratégia de verificação.

Antes de considerar uma tarefa concluída:

- executar as verificações relevantes;
- verificar erros de execução;
- confirmar que a implementação corresponde à especificação aprovada;
- verificar se não houve alteração não intencional em funcionalidades relacionadas.

Uma tarefa não deve ser considerada concluída apenas porque o código foi gerado sem erro aparente.

## Git

Não versionar arquivos contendo credenciais, segredos, ambientes virtuais ou artefatos locais gerados.

Não versionar `.venv/`, `.web/`, arquivos `.env` ou outras configurações locais contendo informações sensíveis.

Manter os commits relacionados à mudança em execução.

Evitar incluir no mesmo commit alterações não relacionadas.

Revisar `git diff` antes de realizar commits relevantes.

## OpenSpec

O OpenSpec é a fonte do processo incremental de desenvolvimento do projeto.

Não criar funcionalidades diretamente em `openspec/specs/` apenas porque fazem parte da visão futura do sistema.

As specs consolidadas devem resultar das changes implementadas e arquivadas.

Antes de iniciar uma implementação relevante, verificar se existe uma change correspondente e se seus artefatos foram revisados.

Quando uma implementação contradizer a especificação, a especificação ou a change deve ser revisada antes de prosseguir.