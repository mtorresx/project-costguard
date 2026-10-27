<!-- reflex managed begin (do not edit inside this block; add custom content outside the markers) -->
# Agents

This project uses the Reflex agent skills — up-to-date knowledge for building full-stack Python web apps with Reflex. Install them first, then use them as described below.

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

```bash
npx skills add reflex-dev/agent-skills
```

Or clone https://github.com/reflex-dev/agent-skills and copy the `skills/` folders into your agent's skill directory (see the repo README for paths).

### Verifying

Before writing or editing any Reflex code, confirm these three skills are available: `reflex-docs`, `setup-python-env`, and `reflex-process-management`. If they are not, STOP and run the install step above — do not proceed without them.

## Using the Skills

### Reflex documentation

For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the reflex-docs skill rather than relying on memory. It carries current, version-accurate docs.

### Initializing a new Reflex project

When starting a new Reflex project or setting up a development environment, you must follow the setup-python-env skill before doing anything else.

Do not skip any steps. Do not assume a virtual environment or Reflex is already available — always verify first by following the skill's instructions in order.

After the environment is ready and Reflex is installed, run:

```bash
reflex init
```

Then proceed with the user's request.

### Managing a Reflex process

When you need to compile, run, reload, or debug a Reflex application, follow the reflex-process-management skill for the correct sequence and error investigation steps.
<!-- reflex managed end -->


# CostGuard — Project Rules

Estas regras são específicas do projeto CostGuard e devem ser seguidas por qualquer agente que trabalhe neste repositório.

## 1. Idioma

- A comunicação com o usuário deve ser feita em português do Brasil.
- Documentação funcional, artefatos OpenSpec e explicações do projeto devem ser escritos em português do Brasil.
- Código, identificadores, nomes técnicos, bibliotecas, comandos e estruturas exigidas por ferramentas podem permanecer em inglês.
- Não traduzir nomes técnicos quando isso prejudicar precisão ou compatibilidade.

## 2. Fonte de verdade e documentação

Antes de propor ou implementar alterações, consultar obrigatoriamente o contexto relevante do projeto.

As principais fontes são:

- `docs/project-overview.md` — visão geral, objetivos, escopo e restrições do projeto;
- `docs/domain-model.md` — conceitos, relações, regras e invariantes do domínio;
- `AGENTS.md` — regras operacionais para agentes;
- `openspec/config.yaml` — contexto e regras persistentes do OpenSpec;
- `openspec/specs/` — especificações consolidadas resultantes de Changes arquivadas;
- `openspec/changes/` — mudanças em elaboração ou implementação;
- `xano/` — representação local da implementação existente no backend Xano;
- `C:\frontend-costguard` — frontend original de referência visual (somente leitura; ver §16).

Não inventar requisitos, regras de negócio ou decisões arquiteturais.

Quando houver diferença entre documentação, especificação e implementação:

1. identificar explicitamente a divergência;
2. informar o usuário;
3. não decidir silenciosamente qual versão está correta;
4. interromper a implementação caso a decisão seja necessária para continuar.

Distinguir sempre entre:

- fato confirmado;
- requisito aprovado;
- inferência;
- proposta;
- ponto desconhecido.

## 3. Arquitetura

A arquitetura definida para o projeto deve ser preservada.

### Frontend

- O frontend deve ser implementado exclusivamente com Reflex.
- Utilizar componentes, páginas, estados, eventos e mecanismos nativos ou oficialmente suportados pelo Reflex.
- Não introduzir React direto, Next.js, Vue, Angular ou outro framework de frontend.
- Uma tecnologia de frontend diferente somente pode ser introduzida após decisão arquitetural explícita e aprovação do usuário.

### Backend

- O backend da aplicação é Xano.
- Regras de negócio, autorização, persistência e validações críticas devem permanecer no backend.
- O frontend nunca deve ser considerado uma barreira de segurança.
- Não mover lógica de segurança para o frontend apenas por conveniência.

### Comunicação

O fluxo arquitetural esperado é:

```text
Reflex
   ↓ HTTP/JSON
Xano
   ↓
Banco / provedores externos
```

Não alterar essa divisão de responsabilidades sem aprovação explícita.

## 4. Desenvolvimento incremental

O projeto utiliza OpenSpec como processo de desenvolvimento orientado por especificação.

O fluxo normal é:

```text
Context
   ↓
Explore
   ↓
Propose
   ↓
Review
   ↓
Apply
   ↓
Verify / Test
   ↓
Homologação humana (§15)
   ↓
Archive
```

Cada Change deve:

- ter escopo claramente delimitado;
- representar uma alteração funcional ou técnica coerente;
- evitar misturar funcionalidades independentes;
- possuir critérios verificáveis;
- respeitar as dependências entre funcionalidades;
- evitar modificações não relacionadas ao objetivo da Change.

Não implementar uma Change antes que seus artefatos tenham sido revisados.

Não utilizar uma Change como justificativa para refatorações ou alterações fora de seu escopo.

Quando surgir uma decisão não prevista durante `Apply`, interromper a implementação e apresentar a decisão ao usuário antes de prosseguir.

## 5. OpenSpec

- Não criar manualmente especificações consolidadas diretamente em `openspec/specs/`.
- As specs consolidadas devem resultar do fluxo de Changes e archive do OpenSpec.
- Utilizar `Explore` antes de uma Change quando houver incerteza, dependências desconhecidas ou necessidade de investigar implementação existente.
- `Propose` deve definir o problema, comportamento esperado, design necessário e tarefas antes da implementação.
- Revisar `proposal`, `specs`, `design` e `tasks` antes de executar `Apply`.
- Não arquivar uma Change enquanto houver divergências conhecidas entre implementação, especificação e tarefas.
- Não marcar tarefas como concluídas sem evidência de que foram executadas.
- Não alterar o escopo silenciosamente durante a implementação.

## 6. Segurança

Segurança e integridade têm prioridade sobre velocidade de implementação.

- Nunca colocar senhas, tokens, API keys, secrets ou credenciais no código-fonte.
- Nunca incluir segredos no Git.
- Nunca expor credenciais no frontend.
- Não registrar tokens, senhas ou outros segredos em logs.
- Credenciais de provedores cloud devem utilizar somente as permissões mínimas necessárias.
- Autenticação e autorização devem ser validadas pelo backend.
- Falhas de importação, autenticação, integração ou processamento não devem ser silenciosas.
- Mensagens de autenticação e recuperação de acesso não devem permitir enumeração indevida de usuários.
- Não reduzir controles de segurança apenas para facilitar testes ou desenvolvimento.

Caso um segredo seja encontrado no código ou em arquivo versionável, interromper e informar imediatamente o usuário.

## 7. Xano

O diretório `xano/` representa localmente a implementação do backend e deve ser tratado como código do projeto.

Ao trabalhar com Xano:

- utilizar o Xano Developer MCP para consultar documentação e validar sintaxe ou comportamento quando necessário;
- não presumir comportamento específico do Xano quando ele puder ser confirmado pela documentação;
- utilizar o Xano CLI para sincronização do workspace quando necessário;
- analisar o código `.xs` existente antes de propor substituições;
- reaproveitar implementação existente que esteja de acordo com a especificação;
- não reimplementar algo apenas porque foi criado antes da adoção do OpenSpec;
- não fazer alterações arbitrárias no schema ou APIs fora do escopo da Change atual;
- não incluir dados, registros ou variáveis de ambiente sensíveis no repositório.

Quando houver diferença entre o código Xano existente e a documentação do projeto, registrar a divergência antes de corrigi-la.

## 8. Reflex

O ambiente Python do projeto utiliza:

```text
venv + pip
```

- Utilizar `.venv` como ambiente virtual local.
- Não versionar `.venv/`.
- Não introduzir `uv`, Poetry, Pipenv ou outro gerenciador de ambiente/dependências sem decisão explícita.
- Manter `requirements.txt` coerente com as dependências efetivamente utilizadas.
- Antes de alterar código Reflex, consultar as Reflex Agent Skills relevantes quando disponíveis.
- Para APIs e comportamentos do Reflex, preferir documentação atual em vez de conhecimento presumido.
- Não substituir funcionalidades nativas do Reflex por soluções externas sem necessidade comprovada.

## 9. Testes e verificação

Uma implementação não deve ser considerada concluída apenas porque o código foi escrito.

Antes de declarar uma tarefa ou Change como concluída:

- verificar se o código compila;
- executar os testes aplicáveis;
- validar os fluxos afetados;
- verificar erros no terminal/log;
- confirmar integração entre Reflex e Xano quando a Change envolver ambos;
- confrontar o resultado com os critérios definidos na especificação;
- verificar se nenhuma funcionalidade fora do escopo foi alterada inadvertidamente.

Se algum teste não puder ser executado, informar explicitamente:

- qual teste não foi executado;
- por que não foi executado;
- qual risco permanece.

Nunca afirmar que algo foi testado sem ter evidência da execução.

## 10. Git — modelo de branches

Toda feature ou Change funcional deve possuir sua própria branch Git.

O fluxo padrão é:

```text
main
  ↓
nova branch da feature (criada pelo usuário)
  ↓
OpenSpec Change
  ↓
revisão dos artefatos (Codex)
  ↓
implementação (Claude Code)
  ↓
testes e auditorias
  ↓
revisão final (Codex)
  ↓
homologação pelo usuário (§15)
  ↓  AJUSTAR → correção → novos testes → nova revisão → nova homologação
  ↓  CONCLUÍDA
archive
  ↓
commits locais (Claude Code, §11)
  ↓
push / integração na main (usuário, ou agente com autorização específica)
```

Regras:

- Não desenvolver features diretamente na `main`.
- Cada Change funcional do OpenSpec deve ser desenvolvida em uma branch própria.
- A branch deve partir da `main` atualizada.
- Preferir nomes descritivos, por exemplo:

```text
feature/autenticacao-base
feature/projetos-orcamento
feature/importacao-recursos
```

- Uma branch deve conter apenas alterações relacionadas à Change correspondente.
- Não misturar features independentes na mesma branch.
- Uma nova feature deve iniciar em uma nova branch criada a partir da `main` atualizada.
- A integração da branch com a `main` é responsabilidade do usuário.

## 11. Git — operações reservadas ao usuário

O usuário mantém controle sobre staging, commits, publicação e integração do histórico Git. A única exceção é a de commits locais após homologação, descrita abaixo.

O agente NUNCA deve executar, salvo autorização específica do usuário para aquela operação, naquele momento:

```text
git push
git merge
git rebase
git reset
```

Não existe autorização permanente para essas operações: uma autorização vale somente para a operação autorizada e não se estende a operações futuras. A mesma regra vale para abrir Pull Requests.

O agente NUNCA deve executar:

```text
git revert
git tag
git stash
git clean
git checkout -- <arquivo>
git restore
```

`git add` e `git commit` só podem ser executados conforme a exceção "Commits locais após homologação".

O agente também não deve:

- criar branch por conta própria;
- trocar de branch por conta própria;
- excluir branch;
- alterar histórico;
- realizar force push;
- utilizar comandos equivalentes que produzam o mesmo efeito;
- interpretar uma solicitação de implementação como autorização implícita para executar operações Git.

Caso seja necessário criar ou trocar de branch, o agente deve informar ao usuário o comando correspondente e aguardar que o usuário o execute.

O agente pode executar comandos Git somente de inspeção, desde que não modifiquem o repositório, por exemplo:

```text
git status
git status --short
git diff
git diff --stat
git log
git branch --show-current
git remote -v
git ls-files
```

### Ao finalizar uma etapa

Quando uma etapa estiver pronta para ser registrada no Git, o agente deve parar e fornecer ao usuário:

1. resumo das alterações realizadas;
2. lista dos arquivos que devem entrar no commit;
3. comando `git add` exato;
4. mensagem sugerida para o commit;
5. indicação de que o usuário deve executar os comandos.

O agente deve preferir:

```bash
git add arquivo1 arquivo2 arquivo3
```

em vez de:

```bash
git add .
```

O objetivo é permitir que o usuário saiba exatamente o que está sendo colocado no stage.

Exemplo de entrega:

```text
Arquivos para staging:
- AGENTS.md
- openspec/changes/autenticacao-base/proposal.md
- openspec/changes/autenticacao-base/specs/...
- openspec/changes/autenticacao-base/design.md
- openspec/changes/autenticacao-base/tasks.md

Comando sugerido:
git add AGENTS.md openspec/changes/autenticacao-base/

Commit sugerido:
git commit -m "docs: define authentication base change"
```

O agente fornece essas instruções, mas não as executa, exceto na situação prevista em "Exceção: commits locais após homologação".

O mesmo princípio vale para `git push`, merge ou qualquer integração com a `main`: o agente pode fornecer o comando, mas o usuário é quem executa, salvo autorização específica.

### Exceção: commits locais após homologação

**Precedência:** depois de o usuário responder exatamente `CONCLUÍDA` na homologação de uma Change (§15), esta exceção prevalece sobre as demais restrições de `git add` e `git commit` desta seção. Ela autoriza o Claude Code a realizar os commits locais dos arquivos daquela Change sem nova autorização, conforme as regras abaixo. Antes de `CONCLUÍDA`, ou para arquivos fora da Change, a exceção não se aplica.

Nessa situação, o Claude Code (coordenador) pode executar:

- `git add <arquivos listados um a um>`: nunca `git add .`, `git add -A` ou `git add -u`;
- `git commit -m "<mensagem>"`: seguindo as convenções do histórico do repositório (`feat(...)`, `fix(...)`, `test(...)`, `docs(openspec): ...`), em português.

Regras da exceção:

- antes de cada commit, mostrar ao usuário a lista de arquivos e a mensagem;
- não incluir arquivos fora do escopo da Change (ex.: `reflex.lock/` alterado apenas pela compilação) nem arquivos com segredos (ex.: `.env`);
- nunca usar `--amend`, `--no-verify`, `--no-gpg-sign` ou commits vazios;
- nunca executar `git push` automaticamente após os commits;
- se algum hook falhar, interromper e informar o usuário.

Fora dessa exceção, valem as regras de "Ao finalizar uma etapa": o agente fornece os comandos e o usuário os executa.

## 12. Controle de mudanças

Não alterar:

- stack tecnológica;
- arquitetura;
- escopo funcional;
- regras de negócio;
- modelo de segurança;
- processo OpenSpec;
- estratégia de branches;
- política de Git definida neste arquivo;

sem aprovação explícita do usuário.

Caso uma alternativa técnica pareça superior, o agente pode apresentá-la com:

- problema identificado;
- alternativa proposta;
- vantagens;
- riscos;
- impacto no projeto.

Mas não deve aplicar a alteração antes da decisão do usuário.

## 13. Conduta analítica

O agente deve priorizar, nesta ordem:

1. fatos e evidências;
2. requisitos aprovados;
3. segurança e integridade;
4. qualidade e manutenibilidade;
5. velocidade.

Não inventar informações para preencher lacunas.

Quando não houver evidência suficiente, declarar explicitamente que a informação é desconhecida ou precisa ser investigada.

Não tratar implementação existente como automaticamente correta.

Não tratar documentação antiga como automaticamente correta.

Confrontar implementação, documentação e especificação quando necessário.

Se houver conflito relevante, apresentar o conflito ao usuário antes de tomar uma decisão.

## 14. Fluxo multiagente (Claude Code + Codex, coordenados pelo Orca)

### Papéis

- **Claude Code — coordenador e único executor.** Único agente que edita arquivos do repositório, marca tarefas, executa `openspec archive`, publica no Xano e faz commits locais (§11).
- **Codex — revisor.** Somente leitura. Não edita arquivos, não marca tarefas, não executa `xano workspace push`, não grava dados no Xano e não executa comandos Git que alterem o repositório. Entrega os achados ao coordenador, que decide como aplicá-los.
- **Kiro** permanece configurado no projeto. Suas skills e prompts (`.kiro/`) e o `openspec/config.yaml` devem ser preservados.
- **Kimi** não é utilizado neste projeto.
- Nenhum outro agente participa sem aprovação explícita do usuário.

### Um escritor por vez

- Somente o Claude Code escreve em arquivos do repositório e publica no Xano.
- Achados do revisor são aplicados pelo coordenador, nunca pelo revisor.
- Após cada revisão, o coordenador confere `git status` para garantir que o revisor não alterou arquivos.
- Publicação no Xano: sempre precedida de dry-run filtrado (`-i <arquivo>`), restrita aos objetos da Change atual, com cópia da versão anterior para recuperação. Dentro desses limites, não exige aprovação a cada publicação (§17).

### Uma Change por vez

- Somente uma Change ativa por vez em `openspec/changes/`.
- Uma nova Change só começa depois de a anterior ser arquivada e commitada, ou por decisão explícita do usuário.

### Retomada de trabalho

- Antes de agir, ler `git status`, `git diff` e o `tasks.md` da Change, e retomar a partir das evidências registradas.
- Alterações locais existentes são preservadas: nunca descartar, sobrescrever ou reverter trabalho não commitado sem autorização.
- Pendências e bloqueios registrados em `tasks.md` continuam válidos até decisão do usuário.

### Dados reais

- Não alterar dados reais apenas para testar.
- Testes que gravam dados no Xano (criar, editar ou desativar registros, reativar usuários, alterar `budget` etc.) exigem autorização explícita do usuário para aquele teste. Sem ela, registrar o teste como não executado e o risco remanescente.
- Preferir leitura, linha de base e comparação. Quando um teste autorizado alterar dados, restaurar o estado anterior e registrar a restauração.

### Ferramentas OpenSpec

- Os fluxos `apply`, `archive`, `explore`, `propose`, `sync` e `update` estão em `.kiro/skills/openspec-*/SKILL.md` e `.kiro/prompts/`. Ler o arquivo correspondente antes de usar o fluxo, ou usar diretamente a CLI `openspec`.

## 15. Homologação

Antes de solicitar a homologação, o coordenador garante:

1. `openspec validate <change> --strict` passando;
2. compilação do Reflex sem erros novos;
3. testes, E2E, regressões e auditorias previstos em `tasks.md` executados com evidência, ou registrados como não executados com motivo e risco;
4. revisão final do Codex sem achados bloqueantes em aberto;
5. `git status` e `git diff --stat` restritos ao escopo da Change.

O pacote de homologação apresentado ao usuário contém: resumo da Change, evidências dos testes, achados da revisão e como foram tratados, riscos remanescentes, lista de arquivos e commits planejados.

Respostas aceitas:

- `AJUSTAR` (com a descrição do ajuste): corrigir, repetir os testes afetados, submeter a nova revisão do Codex e solicitar nova homologação.
- `CONCLUÍDA`: arquivar a Change (com sync das specs) e realizar os commits locais (§11). Nada além disso.

Qualquer outra resposta, ou ausência de resposta, não constitui aprovação.

## 16. Frontend original de referência

O frontend original está em `C:\frontend-costguard`. Ele contém o design que será incorporado integralmente ao projeto principal `C:\projetoImpacta`.

- Claude Code e Codex podem consultar toda a pasta original.
- A pasta original é somente leitura: não modificar, não executar comandos que gerem arquivos nela e não realizar operações Git nela.
- A implementação definitiva ocorre em `C:\projetoImpacta`, adaptando o design à arquitetura Reflex + Xano (§3).
- Dados mockados, fixtures e valores fictícios do frontend original não devem ser transportados para produção: os dados exibidos devem vir do Xano.
- Componentes visuais (layout, estilos, componentes de página) podem ser reutilizados e adaptados. O OpenSpec organiza as entregas e homologações, mas não impede essa reutilização.
- A reutilização não dispensa as regras do projeto: segurança, autorização no backend, escopo da Change atual e verificação (§9).

## 17. Autonomia durante a implementação

O objetivo é entregar ao usuário cada Change implementada, revisada e pronta para homologação funcional, sem pedir aprovação a cada pequena correção, diagnóstico ou teste.

### O que o coordenador faz sem pedir aprovação

Dentro do escopo de uma Change cujos artefatos já foram revisados, o Claude Code pode, sem interromper o usuário:

- coordenar o Orca e acionar o Codex como revisor, além de ferramentas especializadas necessárias, mantendo um único executor de escrita e publicação (§14);
- investigar e corrigir defeitos técnicos da implementação;
- fazer publicações técnicas e temporárias no Xano, exclusivamente dos objetos da Change, sempre com dry-run filtrado, conferência de escopo e cópia da versão anterior para recuperação;
- corrigir achados de revisão que não mudem requisitos de negócio, arquitetura ou escopo funcional;
- atualizar os artefatos OpenSpec da Change (proposal, design, specs, tasks) para refletir correções técnicas, evidências e estratégias de verificação, registrando o motivo;
- executar testes, auditorias e regressões que não gravem dados reais;
- repetir o ciclo implementação → revisão do Codex → correção até não haver achados bloqueantes.

### O que continua exigindo consulta ao usuário

- alterar arquitetura, requisitos de negócio ou escopo funcional;
- modificar dados reais, inclusive para criar cenários de teste;
- publicar objetos Xano fora da Change;
- operações Git destrutivas ou que descartem alterações existentes;
- `git push`, abrir Pull Request, merge na `main` (autorização específica, §11);
- arquivar a Change ou fazer commits antes da homologação `CONCLUÍDA` (§15);
- uso de Kimi ou alteração do Kiro, de `.kiro/`, de `openspec/config.yaml` ou de `C:\frontend-costguard`.

Quando um achado só puder ser resolvido com uma dessas ações, o coordenador continua o restante do trabalho e apresenta a decisão pendente na entrega para homologação, ou interrompe se ela bloquear todo o progresso.

### Entrega para homologação

Ao concluir a implementação e as validações, o coordenador para e apresenta:

- resumo do que foi implementado;
- arquivos e endpoints alterados;
- resultados dos testes e da revisão do Codex;
- pendências e riscos remanescentes;
- endereço e instruções para o usuário testar a aplicação;
- critérios objetivos de homologação.

A partir daí vale o protocolo de §15: `AJUSTAR` reabre o ciclo; `CONCLUÍDA` autoriza o archive e os commits locais (§11). PR, push e merge exigem autorização específica posterior.