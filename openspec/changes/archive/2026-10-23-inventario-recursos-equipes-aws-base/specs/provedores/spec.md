## ADDED Requirements

### Requirement: Tag Key de equipe do provedor

O sistema SHALL persistir no provedor um campo opcional `tag_alocacao_equipe` que representa a
**Tag Key** da tag de equipe (user-defined tag) usada para identificar a equipe dona de um recurso
no inventário (Tag Key recomendada: `EQP`). Esse campo SHALL ser aceito e persistido na criação e
na edição do provedor, e SHALL ser retornado na listagem e no detalhe como metadado (não é
segredo). O valor padrão/recomendado SHALL ser `EQP`: um provedor criado sem informar o campo
SHALL resultar em `tag_alocacao_equipe = "EQP"`; quando o admin informar explicitamente outro
valor válido, este SHALL ser preservado; uma edição (PATCH) que não envie o campo MUST NOT apagar
o valor existente. Para provedores legados cujo valor seja `null`/vazio (ex.: após a adição do
campo), a sincronização SHALL aplicar o fallback `EQP` em tempo de execução, de modo que esses
provedores não transformem silenciosamente todos os recursos em "Sem responsável". O
`tag_alocacao_equipe` MUST NOT ser hardcoded na lógica: o valor efetivo vem do provedor (ou do
fallback padrão `EQP`). A inclusão deste campo MUST NOT expor o segredo da credencial nem
alterar as demais regras do provedor (autorização admin para escrita, leitura por autenticado,
JWE preservado).

#### Scenario: Provedor com Tag Key de equipe definida

- **WHEN** um admin define `tag_alocacao_equipe = EQP` em um provedor AWS
- **THEN** o valor é persistido e passa a ser usado como a Tag Key de equipe na resolução do inventário

#### Scenario: Provedor criado sem informar a Tag Key de equipe usa o default EQP

- **WHEN** um admin cria um provedor AWS sem informar `tag_alocacao_equipe`
- **THEN** o provedor é persistido com `tag_alocacao_equipe = "EQP"`

#### Scenario: Provedor legado com Tag Key de equipe nula usa fallback EQP na sincronização

- **WHEN** um provedor legado tem `tag_alocacao_equipe` nulo/vazio e uma sincronização é executada
- **THEN** o inventário usa a Key `EQP` por fallback, resolvendo equipes normalmente, sem marcar todos os recursos como "Sem responsável" apenas por causa do campo ausente

#### Scenario: Leitura inclui a Tag Key de equipe sem segredo

- **WHEN** um usuário autenticado lista ou consulta o detalhe de provedores
- **THEN** as respostas incluem `tag_alocacao_equipe` (quando definido) e nunca o `secret_access_key`
