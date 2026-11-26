## ADDED Requirements

### Requirement: Acesso público à landing

O frontend SHALL exibir em `/` uma landing page pública, sem exigir sessão e sem chamadas ao backend, com navbar, hero, "Quem somos", "O que fazemos", chamada final e rodapé, adaptando o design do frontend de referência.

#### Scenario: Visitante sem sessão

- **WHEN** um visitante sem sessão abre `/`
- **THEN** a landing é exibida, sem redirecionamento para `/login`

### Requirement: Usuário autenticado é levado ao painel

Quando houver sessão no navegador, a landing SHALL encaminhar o usuário para `/inicio`, onde a sessão é validada no backend.

#### Scenario: Usuário com sessão abre a landing

- **WHEN** um usuário com sessão abre `/`
- **THEN** ele é levado a `/inicio`

### Requirement: Entrada pela landing sem autocadastro

Os botões "Entrar", "Começar agora" e "Acessar o CostGuard" SHALL levar a `/login`. A landing MUST NOT oferecer formulário ou botão de criação de conta.

#### Scenario: Entrar

- **WHEN** o visitante clica em "Entrar"
- **THEN** ele é levado a `/login`

### Requirement: Conteúdo fiel ao produto

O conteúdo da landing SHALL descrever apenas funcionalidades existentes (AWS, atribuição por tags de projeto e equipe, orçamento mensal, alertas de 70%, 90% e 100%, recursos sem classificação, falhas de importação, acesso somente leitura, papéis admin e leitura). A ilustração do painel MUST NOT exibir valores numéricos fictícios. O rodapé MUST NOT conter links para páginas inexistentes.

#### Scenario: Sem números fictícios

- **WHEN** a landing é exibida
- **THEN** a ilustração do painel não mostra valores monetários nem contagens

### Requirement: Navegação por âncoras e layout responsivo

Os links da navbar SHALL rolar suavemente até as seções correspondentes (rolagem instantânea quando o sistema pede menos movimento). Em telas de 375 px, a landing SHALL empilhar as seções em uma coluna, manter "Entrar" visível e não ter rolagem horizontal.

#### Scenario: Tela estreita

- **WHEN** a landing é aberta com 375 px de largura
- **THEN** "Entrar" fica visível e não há rolagem horizontal
