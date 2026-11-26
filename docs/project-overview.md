# Project Overview — CostGuard

## 1. Visão geral

O CostGuard é um sistema de gestão e responsabilização de custos de computação em nuvem.

Seu objetivo é permitir que uma organização identifique não apenas quanto está sendo gasto em serviços cloud, mas também a qual projeto e equipe cada custo pertence.

O sistema utiliza informações de custo e tags existentes nos recursos da nuvem para realizar automaticamente a classificação dos gastos, consolidá-los por projeto, compará-los com orçamentos mensais e gerar alertas quando situações que exigem atenção forem identificadas.

O projeto é voltado principalmente para AWS. Há também suporte à leitura do custo mensal do Azure, ainda não validado com valores reais.

## 2. Problema

Ambientes de computação em nuvem podem possuir grande quantidade de recursos criados por diferentes equipes e projetos.

Embora os provedores disponibilizem informações sobre custos, identificar de forma clara quem é responsável por cada gasto pode ser difícil quando os recursos não estão adequadamente organizados.

Isso pode resultar em:

- dificuldade para identificar responsáveis pelos custos;
- recursos sem classificação;
- ausência de controle por projeto;
- estouro de orçamento percebido somente após o gasto ocorrer;
- necessidade de processos manuais para consolidar informações.

O CostGuard busca resolver esse problema associando automaticamente os custos aos projetos e equipes responsáveis.

## 3. Objetivos

O projeto possui como objetivos principais:

- importar informações de recursos e custos do provedor cloud;
- identificar o projeto responsável por cada recurso através de tags;
- identificar a equipe responsável pelo recurso através de tags;
- consolidar os custos por projeto;
- permitir definição de orçamento mensal para projetos;
- comparar automaticamente o consumo com o orçamento;
- alertar quando determinados limites de orçamento forem alcançados;
- identificar recursos sem classificação adequada;
- reduzir a necessidade de classificação manual recorrente.

## 4. Público-alvo e usuários

O sistema é destinado a organizações que utilizam infraestrutura em nuvem e precisam acompanhar a responsabilidade pelos custos gerados.

Existem dois papéis de usuário no sistema:

### Administrador

Possui permissão para:

- gerenciar usuários;
- criar e administrar projetos;
- definir orçamentos;
- conectar provedores cloud;
- visualizar todas as informações disponíveis no sistema.

### Leitura

Possui acesso exclusivamente para consulta.

Usuários com papel de leitura não podem criar, alterar ou excluir informações.

Os usuários do sistema não são vinculados diretamente a projetos ou equipes. A responsabilidade pelos recursos é determinada através das tags existentes nos recursos cloud.

## 5. Escopo inicial

O escopo do CostGuard contempla:

- autenticação de usuários;
- recuperação e redefinição de senha (não implementado na versão atual);
- gerenciamento de usuários;
- gerenciamento de projetos;
- definição de orçamento mensal por projeto;
- gerenciamento das equipes relacionadas aos projetos;
- conexão com um provedor cloud;
- importação automática de recursos e custos;
- classificação automática dos recursos através de tags;
- identificação de recursos sem projeto;
- identificação de recursos sem equipe;
- acompanhamento de consumo por projeto;
- geração de alertas;
- visualização das informações em dashboard.

O provedor cloud principal é a AWS; o Azure tem apenas suporte à leitura do custo mensal, ainda não validado com valores reais.

## 6. Principais funcionalidades

### Autenticação e acesso

O sistema deverá possuir autenticação por nome de usuário e senha.

Não haverá autocadastro. Usuários serão criados por um administrador.

O e-mail é previsto como canal para recuperação de acesso, mas a recuperação de senha não está implementada na versão atual: um administrador define uma nova senha em **Usuários**.

### Projetos

Um projeto representa uma iniciativa da organização que possui um orçamento mensal.

Cada projeto possui um código utilizado para relacionar os recursos cloud ao projeto correspondente.

### Equipes

Um projeto pode possuir equipes.

As equipes permitem identificar qual grupo, dentro de um projeto, é responsável pelo consumo de determinado recurso.

Equipes não possuem orçamento próprio.

### Classificação de recursos

Os recursos cloud serão classificados automaticamente através de uma convenção de tags.

O projeto deverá ser identificado antes da equipe.

Um recurso que possua projeto válido, mas não possua equipe, permanecerá associado ao projeto como "Sem responsável" e continuará contando para o orçamento.

Um recurso que não possua projeto válido será considerado "Não classificado" e permanecerá fora dos orçamentos até que sua classificação seja corrigida na origem.

### Reatribuição

A correção da responsabilidade por um recurso deverá ocorrer alterando suas tags no provedor cloud.

O CostGuard não deverá possuir uma classificação manual paralela para substituir as tags da nuvem.

Na importação seguinte, o recurso deverá ser automaticamente reavaliado.

### Orçamento

Cada projeto possuirá um orçamento mensal em USD.

O consumo do projeto será calculado considerando os custos dos recursos atribuídos ao projeto, incluindo os recursos classificados como "Sem responsável".

### Alertas

O sistema deverá gerar alertas para situações relevantes, incluindo:

- consumo de orçamento;
- recursos sem classificação;
- falhas de importação.

Os níveis de consumo previstos para alerta de orçamento são:

- 70% — atenção;
- 90% — aviso;
- 100% ou mais — orçamento excedido.

## 7. Requisitos e restrições importantes

As seguintes regras devem ser preservadas durante o desenvolvimento:

- senha nunca deve ser armazenada em texto puro;
- login deve utilizar nome de usuário;
- autorização deve ser aplicada no backend;
- usuários de leitura não podem realizar operações de escrita;
- o sistema deve preservar pelo menos um administrador ativo;
- usuários devem ser desativados em vez de excluídos;
- credenciais de provedores cloud devem possuir somente as permissões necessárias;
- segredos não devem ser armazenados no código-fonte ou frontend;
- falhas de importação não devem ocorrer silenciosamente;
- custos não devem ser descartados por problemas de classificação;
- a reatribuição de recursos deve ocorrer através das tags do provedor;
- mensagens de autenticação (e, quando existir, de recuperação de acesso) não devem permitir enumeração de usuários.

## 8. Arquitetura tecnológica

A arquitetura definida para o projeto utiliza:

### Frontend

Reflex, utilizando Python.

O Reflex será a tecnologia exclusiva utilizada para implementação das interfaces do projeto.

### Backend

Xano.

O backend será responsável pelas APIs, persistência, regras de negócio e validações que não podem depender do cliente.

### Banco de dados

O armazenamento utilizado pelo backend será o banco disponibilizado pelo Xano.

### Integração cloud

A integração principal é com a AWS.

Há também suporte à leitura do custo mensal do Azure, ainda não validado com valores reais. Outros provedores poderão ser considerados futuramente.

## 9. Princípios de desenvolvimento

O projeto segue os seguintes princípios:

- mudanças pequenas e verificáveis;
- evitar duplicação desnecessária;
- manter separação clara entre frontend e backend;
- utilizar a documentação oficial das tecnologias.

## 10. Segurança e integridade

O CostGuard manipulará informações de infraestrutura e credenciais de integração com provedores cloud.

Por esse motivo:

- credenciais cloud deverão possuir somente permissões de leitura necessárias;
- segredos não deverão ser armazenados no frontend;
- segredos não deverão ser versionados no Git;
- controles visuais não serão considerados mecanismos de autorização;
- verificações de autorização deverão ocorrer no backend;
- erros de importação deverão ser informados;
- dados de custo não deverão ser silenciosamente descartados.

## 11. Fora do escopo inicial

Não fazem parte do escopo:

- múltiplos provedores cloud com o mesmo nível de suporte da AWS (do Azure há apenas a leitura do custo mensal, ainda não validada com valores reais);
- orçamento trimestral ou anual;
- orçamento individual por equipe;
- rateio de custos entre equipes;
- previsão de gastos futuros;
- detecção automática de anomalias;
- recomendações automáticas de economia;
- conversão entre moedas;
- auditoria completa das alterações realizadas no sistema.

O orçamento é mensal e expresso em USD.

## 12. Documentação

A documentação do projeto é dividida por responsabilidade:

- `docs/project-overview.md` apresenta a visão global do CostGuard;
- `docs/domain-model.md` descreve os conceitos e relacionamentos do domínio.

Nem toda funcionalidade descrita na visão global está implementada; os limites atuais constam no `README.md` (seção Limitações).