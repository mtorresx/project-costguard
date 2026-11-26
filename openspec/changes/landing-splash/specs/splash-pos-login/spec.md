## ADDED Requirements

### Requirement: Animação de entrada após login aceito

Após o login aceito e a identificação do usuário (`/me`), o frontend SHALL cobrir a tela com o overlay da animação, que entra com fade curto, e tocar o vídeo do logotipo do início, uma vez. Com o login recusado, o overlay MUST NOT aparecer e a mensagem de erro SHALL ser exibida no formulário.

#### Scenario: Login aceito

- **WHEN** o usuário informa credenciais válidas
- **THEN** o overlay entra com fade e o vídeo toca do início

#### Scenario: Login recusado

- **WHEN** o login é recusado
- **THEN** o overlay não aparece e a mensagem genérica de erro é exibida

### Requirement: Painel carregado por baixo e revelação suave

Com o overlay opaco, a rota SHALL trocar para `/inicio` por baixo dele, sem que nenhum elemento do painel fique visível durante o vídeo e sem que o foco de teclado alcance controles por baixo do overlay. Ao fim do vídeo, o logotipo SHALL sumir com fade e o overlay SHALL se dissolver suavemente (cerca de 800 ms), revelando o painel. Quem pede menos movimento no sistema SHALL ir direto ao painel, sem overlay nem vídeo.

#### Scenario: Fim do vídeo

- **WHEN** o vídeo termina
- **THEN** o logotipo some, o overlay se dissolve e o painel em `/inicio` aparece

### Requirement: Usuário nunca fica preso

Se o vídeo falhar, o frontend SHALL concluir imediatamente; se o vídeo não sinalizar o término, SHALL concluir após 11 segundos. A revelação MUST ocorrer somente depois de o painel `/inicio` avisar que carregou; se o aviso não vier em 8 segundos após o fim do vídeo, o overlay SHALL permanecer, informar a demora, reenviar a navegação e oferecer o botão "Continuar" (com foco de teclado), sem se dissolver sozinho.

#### Scenario: Painel demorando

- **WHEN** o painel não avisa que carregou em 8 segundos após o fim do vídeo
- **THEN** o overlay continua opaco, mostra a mensagem de demora e o botão "Continuar", que fecha o overlay

#### Scenario: Vídeo não carrega

- **WHEN** o arquivo de vídeo falha
- **THEN** o overlay se dissolve sem esperar o limite

### Requirement: Logins consecutivos e chave de desativação

Cada login SHALL tocar o vídeo do início, com o limite contado a partir desse login. Com `SPLASH_ATIVO = False`, o login SHALL ir direto a `/inicio`, sem overlay.

#### Scenario: Novo login

- **WHEN** o usuário sai e entra novamente
- **THEN** a animação toca do começo
