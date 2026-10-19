## MODIFIED Requirements

### Requirement: Entidade Provedor

O sistema SHALL persistir provedores com os campos conceituais: `id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial`, credencial, `tag_alocacao_projeto` e `status`. O `apelido` SHALL identificar o provedor para o usuário. O `tipo` SHALL indicar o provedor cloud e, nesta fase, SHALL aceitar somente o valor `aws`. O `identificador_conta` SHALL representar a identificação da conta cloud (ex.: o Account ID AWS). O `tipo_credencial` SHALL indicar a forma de autenticação utilizada (nesta fase, chave de acesso AWS). O `tag_alocacao_projeto` SHALL representar a **Key** da tag de alocação de custo (user-defined cost allocation tag) usada para agrupar os custos por projeto no Cost Explorer (ex.: `Projeto`); SHALL ser opcional e, quando ausente, a classificação de custos por projeto MUST NOT ser executada. O `status` SHALL distinguir, no mínimo, provedor com conexão válida (`ok`), com erro de conexão (`erro`), ainda não testado (`pendente`) e desativado logicamente (`inativo`).

#### Scenario: Provedor persistido com os campos do contrato

- **WHEN** um provedor é criado com sucesso
- **THEN** ele passa a existir com `id`, `apelido`, `tipo`, `identificador_conta`, `tipo_credencial` e `status`

#### Scenario: Provedor com Key da tag de alocação definida

- **WHEN** um admin define a Key da tag de alocação de custo (`tag_alocacao_projeto`) de um provedor AWS
- **THEN** o valor é persistido no provedor e passa a ser usado como a Key do agrupamento por tag na classificação de custos por projeto

#### Scenario: Provedor sem Key da tag de alocação

- **WHEN** um provedor AWS não possui `tag_alocacao_projeto` definido
- **THEN** o provedor continua válido para a coleta base de custos, mas a classificação de custos por projeto não pode ser executada até que a Key seja definida
