Quero fazer uma nova rodada de refinamento do site institucional público do CORE PDV em cima do que já foi implementado.

IMPORTANTE: eu gostei da direção atual. NÃO quero reconstruir o site do zero e NÃO quero trocar a arquitetura.

Quero melhorar o que já existe.

Antes de alterar, analise novamente os arquivos atuais e trabalhe em cima do commit mais recente.

A base evoluiu bastante, mas ainda existem:
- partes visualmente muito cruas;
- falta de imagens e presença visual;
- alguns textos que parecem instruções internas em vez de copy comercial;
- placeholders técnicos aparecendo para o visitante;
- pontos técnicos pendentes no fluxo comercial;
- footer fraco;
- ausência de gerenciamento de cookies.

O objetivo agora é dar acabamento de produto real.

---

# 1. DIREÇÃO GERAL

Quero que o institucional fique:

- mais premium;
- mais visual;
- mais maduro;
- mais institucional;
- mais confiável;
- com mais personalidade CORE;
- menos seco;
- menos “texto + borda”;
- com produto real aparecendo mais;
- com fotografias e screenshots participando da composição.

Continuam valendo TODAS as restrições anteriores.

NÃO quero:

- aparência de site feito por IA;
- fonte serifada;
- fundo quadriculado;
- grid decorativo;
- pontinhos;
- glow azul em tudo;
- neon;
- glassmorphism;
- gradientes aleatórios;
- emojis;
- dezenas de cards iguais;
- ícones genéricos usados para preencher espaço;
- mockups falsos;
- dashboard falso;
- gráfico inventado;
- números fictícios;
- depoimentos fictícios;
- logos fictícios;
- imagens geradas por IA para fingir que são o produto.

O CORE real continua sendo o principal elemento visual.

---

# 2. HERO — MANTER A DIREÇÃO, MELHORAR A COMPOSIÇÃO

Gostei da direção do Hero atual:

“Sua operação inteira. Conectada pelo CORE.”

Não quero abandonar essa linguagem.

Porém o bloco que aparece ao lado contendo:

“Do atendimento à gestão”

“CORE POS registra a operação. CORE Backoffice transforma esse contexto em controle.”

“Os dois ambientes têm papéis diferentes e trabalham sobre a mesma rotina da empresa.”

deve ser substituído.

Não quero aquele bloco textual ocupando o destaque visual principal.

## Quero no lugar:

UMA IMAGEM FORTE.

Pode ser, preferencialmente:

- fotografia real do CORE POS em equipamento;
- produto sendo utilizado em uma operação;
- composição real CORE POS + Backoffice;
- equipamento POS em primeiro plano com produto real;
- outro asset real que comunique tecnologia + operação.

A parte direita do Hero deve funcionar como prova visual do produto.

Não criar mockup falso.

Se eu ainda não tiver enviado o asset definitivo, deixe tecnicamente preparado, mas sem mostrar para o visitante textos como:

“imagem pendente”

“asset pendente”

“screenshot pendente”

ou caminho de arquivo.

---

# 3. REMOVER COPY QUE PARECE INSTRUÇÃO PARA IA

Existem atualmente alguns textos públicos que não devem aparecer para o visitante.

Por exemplo:

“Do atendimento à gestão, sem reconstruir o produto para a apresentação.”

Isso é uma regra interna do projeto, NÃO é copy comercial.

Também remover/reformular textos como:

“Não apresentamos certificações ou integrações sem comprovação.”

“A demonstração deve confirmar a configuração adequada para cada operação.”

“O site não declara parceria, homologação ou disponibilidade comercial sem validação específica.”

As REGRAS por trás dessas frases continuam obrigatórias.

Ou seja:

- não inventar homologação;
- não inventar integração;
- não inventar certificação;
- não inventar funcionalidade.

Mas o visitante não precisa ler nossas instruções internas.

Transforme essas áreas em comunicação comercial natural.

---

# 4. “O QUE O CORE CONECTA” ESTÁ MUITO CRU

Hoje temos algo próximo de:

“O que o CORE conecta”

Venda → Pagamento → Caixa → Estoque → Gestão

A ideia é boa.

A execução está muito simples.

Quero transformar isso em uma seção visual forte.

## Quero comunicar:

VENDA
→ PAGAMENTO
→ CAIXA
→ ESTOQUE
→ GESTÃO

Mas não quero cinco palavras perdidas no meio da página.

Criar uma composição visual própria do CORE.

Pode trabalhar com:

- tipografia forte;
- linha de fluxo;
- conectores;
- transições;
- pequenas imagens reais;
- elementos do produto;
- composição desktop horizontal e mobile vertical.

Não transformar isso em cinco cards genéricos com cinco ícones.

Essa seção precisa explicar visualmente uma das maiores propostas do CORE:

**a informação nasce na operação e continua conectada até a gestão.**

---

# 5. CORE POS E CORE BACKOFFICE

Manter a separação atual porque está correta:

## CORE POS
A operação acontece aqui.

## CORE Backoffice
A gestão acontece aqui.

Mas essas duas seções precisam ganhar mais presença visual quando os assets estiverem disponíveis.

Não quero que pareçam apenas:

texto de um lado + placeholder cinza do outro.

Usar screenshots reais em destaque.

Pode utilizar:
- recortes grandes;
- detalhes de tela;
- screenshot inteiro;
- foto do equipamento;
- composições editoriais simples.

Sem criar notebook/browser fake envolvendo tudo.

---

# 6. CORRIGIR `ProductEvidence`

O componente atual não está adequado para produção.

Hoje ele recebe um caminho de asset, mas em vez de renderizar a imagem real, mostra para o visitante:

“Screenshot real pendente”

e até o caminho:

`/site/screenshots/...`

Isso NÃO pode acontecer.

## Quero corrigir:

`ProductEvidence` deve efetivamente renderizar o asset real quando existir.

Utilizar a solução adequada do Next.js, preferencialmente `next/image` quando aplicável.

Precisa existir:
- dimensões/proporção adequada;
- `alt`;
- otimização;
- responsividade;
- carregamento apropriado.

Quando o asset não estiver disponível:

NÃO mostrar caminho interno.

NÃO mostrar “screenshot pendente”.

NÃO mostrar mensagem de desenvolvedor.

A seção pode:
- ser omitida;
- utilizar composição neutra;
- ou ter fallback visual institucional discreto.

Mas nada técnico deve vazar para produção.

---

# 7. TEASER EM VÍDEO

A ideia do vídeo continua.

Quero ter uma seção forte mostrando:

**Veja o CORE em operação.**

O vídeo será do produto REAL.

Pode mostrar:
- CORE POS;
- venda;
- mesas;
- pagamento;
- operação;
- Backoffice;
- estoque;
- gestão.

Porém hoje, quando o vídeo não existe, aparece algo como:

“Vídeo do CORE em preparação”

e caminho de arquivo.

REMOVER isso da interface pública.

## Comportamento correto:

Se o vídeo estiver configurado:
→ mostrar seção completa.

Se o vídeo não estiver configurado:
→ ocultar o player ou apresentar uma composição institucional adequada.

Nunca mostrar mensagens de desenvolvimento.

Preparar corretamente:

- poster;
- preload;
- controles;
- responsividade;
- acessibilidade;
- lazy loading quando adequado;
- sem autoplay com áudio.

---

# 8. PAGAMENTOS E INTEGRAÇÕES PRECISAM DE MUITO MAIS PRESENÇA VISUAL

Hoje essa área está correta conceitualmente, mas visualmente está fraca.

Essa seção merece ser uma das partes mais marcantes da Home.

## Quero imagens de equipamentos de pagamento.

Quero uma faixa/carrossel horizontal com maquininhas/dispositivos passando para o lado.

Pode funcionar como:

- carrossel;
- slider;
- marquee muito suave;
- track horizontal com movimento discreto.

Precisa parecer premium.

Não quero carrossel genérico cheio de cards.

Quero os EQUIPAMENTOS sendo protagonistas.

Exemplos de material visual:
- Stone;
- Cielo;
- Getnet;
- Rede;
- Mercado Pago;
- outros equipamentos compatíveis com o planejamento real.

IMPORTANTE:

Antes de colocar marca, logo ou declarar integração/homologação, verificar o status real.

Imagem de dispositivo também deve ter origem adequada/autorizada para uso no site.

Não afirmar:
- “Parceiro oficial”;
- “Homologado”;
- “Integrado”;
- “Disponível”;

sem comprovação real.

Podemos comunicar arquitetura multi-provider sem inventar status comercial.

O texto conceitual:

“Pagamento faz parte da venda. Não deveria ser outro processo.”

pode continuar.

Quero que a parte visual fique muito mais forte.

---

# 9. SEGMENTOS ESTÁ MUITO CRU

Hoje temos basicamente texto.

Quero uma seção visual.

Segmentos possíveis:

- bares;
- restaurantes;
- lounges;
- casas noturnas;
- casas de eventos;
- pizzarias;
- lanchonetes;
- food service;
- varejo compatível;
- outras operações presenciais.

Mas NÃO quero:

uma grade com 9 cards e 9 ícones genéricos.

## Quero fotografia.

Pode existir uma composição utilizando fotografias reais que representem:

- balcão;
- salão;
- bar;
- restaurante;
- operação noturna;
- atendimento;
- varejo.

Trabalhar com layout mais editorial.

Fotos grandes.

Pouco texto.

Boa tipografia.

Pode destacar segmentos em cima ou ao lado das imagens.

O objetivo é fazer o visitante se enxergar usando o CORE.

---

# 10. SEGURANÇA E AUDITORIA TAMBÉM PRECISA DE IMAGEM

Hoje essa seção também está muito simples.

Quero dar mais peso visual.

A seção deve transmitir:

- controle;
- rastreabilidade;
- responsabilidade;
- permissões;
- segurança operacional;
- histórico;
- dispositivos;
- contexto por filial.

Podemos utilizar:

- screenshot real de auditoria;
- screenshot de usuários/permissões;
- screenshot de sessões/dispositivos;
- detalhe real do Backoffice.

Não precisa usar cadeado gigante, escudo 3D ou estética de cybersecurity.

Quero mostrar segurança através do PRODUTO.

---

# 11. `/solucoes` TAMBÉM PRECISA RECEBER O MESMO REFINAMENTO

Não quero melhorar somente a Home.

A página `/solucoes` precisa seguir a mesma direção visual.

Atualmente ela também depende muito de:

texto + placeholder.

Melhorar progressivamente as áreas com screenshots reais.

Manter os blocos:

- CORE POS / Vendas;
- Mesas e Comandas;
- Pagamentos;
- Estoque e Compras;
- Gestão e Relatórios;
- Multiempresa e Multifilial;
- Segurança e Auditoria.

Mas não escrever instruções internas no conteúdo.

Exemplo atual que deve ser removido/reformulado:

“O site não declara parceria, homologação ou disponibilidade comercial sem validação específica.”

Essa regra é para VOCÊ, não para o visitante.

---

# 12. FOOTER — REFAZER

O footer atual ficou desagradável.

Quero redesenhar completamente o footer mantendo simplicidade.

Ele precisa parecer rodapé de uma empresa de software profissional.

## Quero organizar melhor:

### Marca
- Logo CORE;
- pequena descrição institucional.

### Produto
- Soluções;
- CORE POS;
- Gestão;
- Planos;
- Integrações.

### Empresa
- Sobre/Empresa;
- Contato;
- Segurança.

### Suporte
- Ajuda;
- Área do cliente;
- canais de atendimento.

### Legal
- Privacidade;
- Cookies;
- Termos.

### Informações institucionais
Quando estiverem configuradas:
- razão social;
- CNPJ;
- cidade/estado;
- e-mail;
- outros dados reais necessários.

Não inventar nada que ainda não esteja cadastrado.

Visualmente:

- melhorar espaçamento;
- melhorar hierarquia;
- melhorar distribuição;
- melhorar linha inferior;
- deixar menos “lista de links jogada”.

Pode usar uma área final discretamente diferenciada do restante da página, mas sem glow, neon ou gradientão.

---

# 13. “EMPRESA” NO HEADER

Hoje “Empresa” aponta para `/#empresa`.

Porém essa seção é apenas CTA comercial:

“Vamos conversar”.

Isso não corresponde a “Empresa”.

Corrigir.

Tem duas opções:

1. criar uma página/seção institucional real sobre o CORE;
ou
2. remover “Empresa” do menu enquanto essa página não estiver pronta.

NÃO manter link com nome “Empresa” levando para CTA de vendas.

Preferencialmente preparar posteriormente:

`/empresa`

ou:

`/sobre`

com:
- quem é o CORE;
- o que construímos;
- proposta;
- informações institucionais reais;
- contato.

Sem inventar história, números ou equipe.

---

# 14. COOKIES — FALTA IMPLEMENTAR

Quero implementar gerenciamento de consentimento de cookies no site público.

Não quero apenas um banner fake que não controla nada.

## Criar:

### Cookie Consent Banner

Visual:
- discreto;
- profissional;
- integrado à identidade CORE;
- responsivo;
- não bloquear a página inteira.

Mensagem clara em português.

Ações:

- “Aceitar”
- “Recusar”
- “Configurar” / “Preferências”

ou uma estrutura equivalente simples e correta.

## Categorias

Preparar pelo menos:

### Necessários
Sempre ativos quando forem tecnicamente necessários para funcionamento e segurança.

### Analytics
Desativados até consentimento, caso sejam implementados.

### Marketing
Desativados até consentimento, caso sejam implementados no futuro.

Não ativar cookie não essencial antes da escolha do usuário.

## Persistência

Salvar preferência de consentimento.

Não mostrar o banner novamente a cada navegação.

Preparar também possibilidade de:
- alterar preferência posteriormente;
- link “Preferências de cookies” no Footer.

Preferencialmente versionar o consentimento para conseguirmos solicitar novamente se a política mudar futuramente.

## Importante

Não instalar Google Analytics, Meta Pixel ou outras ferramentas nesta missão sem necessidade explícita.

O sistema deve ficar preparado para respeitar consentimento quando esses scripts forem adicionados.

---

# 15. PRIVACIDADE E TERMOS

Hoje o Footer depende de `institutional_links`.

Revisar isso.

Precisamos ter uma estratégia clara para:

- Política de Privacidade;
- Política de Cookies;
- Termos de Uso.

Se as páginas/documentos definitivos ainda não existirem:

NÃO inventar conteúdo jurídico.

Deixar a estrutura pronta e informar quais documentos reais precisam ser fornecidos.

O consentimento de cookies deve apontar para a política correspondente quando ela estiver disponível.

---

# 16. FLUXO COMERCIAL — MANTER

A arquitetura implementada de Lead está no caminho certo.

Manter:

Visitante
→ Solicitar demonstração
→ `/contato`
→ CommercialLead
→ banco
→ notificação
→ contato humano.

Não voltar com auto cadastro.

Manter:

`public_signup_enabled = False`

por padrão.

`/cadastro`
→ `/contato`

Planos:
→ `/contato?plano=...`

---

# 17. CORRIGIR CONFIGURAÇÃO REAL DO E-MAIL NO DEPLOY

Foi identificado um problema importante.

O backend já possui:

`SALES_LEAD_EMAIL`

e infraestrutura SMTP.

Porém o `docker-stack.yml` precisa efetivamente repassar para o container as configurações necessárias.

Revisar e corrigir.

Garantir passagem apropriada de:

- SALES_LEAD_EMAIL
- DEFAULT_FROM_EMAIL
- EMAIL_HOST
- EMAIL_PORT
- EMAIL_HOST_USER
- EMAIL_HOST_PASSWORD
- EMAIL_USE_TLS
- EMAIL_USE_SSL
- EMAIL_TIMEOUT

Não expor secrets no repositório.

Quando necessário utilizar Docker Secrets ou mecanismo equivalente coerente com a infraestrutura atual.

O comportamento precisa continuar:

Lead salvo
→ tenta e-mail.

SMTP falhou
→ Lead permanece salvo.

---

# 18. `public_signup_enabled` NO PLATFORM ADMIN

Foi adicionado no backend:

`GlobalSaaSSettings.public_signup_enabled`

mas essa configuração ainda não está corretamente representada na interface do Platform Admin.

Quero corrigir.

Adicionar ao tipo `GlobalSettings` e à interface de configurações.

Preciso conseguir visualizar/controlar:

**Cadastro público**
- Ativado
- Desativado

Neste momento deve permanecer:

**DESATIVADO**

Respeitar o padrão de ações críticas/configurações já utilizado pelo Platform Admin.

Não criar configuração paralela.

---

# 19. PLANOS — PEQUENO REFINAMENTO

A lógica atual está correta:

“Falar sobre este plano”

→ `/contato?plano=...`

Manter.

Porém revisar visualmente a página para garantir que não volte a parecer aquela grade genérica de SaaS.

Também revisar o badge:

“Disponível”

Não quero que o primeiro plano receba automaticamente destaque apenas porque é o primeiro array se isso não representar regra comercial real.

Se existe plano recomendado/destaque, essa informação deve vir de dado/configuração real.

Não inferir:

`index === 0`

como “plano em destaque”.

---

# 20. CORRIGIR NUMERAÇÃO CORE POS / BACKOFFICE

Na Home atual, os itens do CORE POS aparecem repetindo:

`01`

e os do Backoffice repetindo:

`02`

Isso parece erro visual.

Se:

`01 = CORE POS`

e:

`02 = CORE Backoffice`

o número deve identificar a SEÇÃO, não cada item.

Corrigir a composição.

---

# 21. HEADER MOBILE

Revisar também o Header mobile depois das mudanças.

Hoje a estrutura usa `<details>`.

Pode permanecer se estiver acessível e funcional, mas verificar:

- abrir/fechar;
- foco;
- navegação por teclado;
- clique externo;
- navegação depois de selecionar item;
- tamanho dos alvos;
- organização dos CTAs.

Não trocar biblioteca só por trocar.

---

# 22. ASSETS REAIS

Ao final desta missão quero receber uma lista EXATA dos assets necessários.

Não simplesmente:

“faltam imagens”.

Quero algo como:

1. `hero-operation.webp`
   - proporção recomendada
   - resolução mínima
   - conteúdo esperado.

2. `core-pos-venda.webp`
   - screenshot da Venda Rápida.

3. `backoffice-dashboard.webp`
   - dashboard real.

4. `mesas.webp`

5. `estoque-compras.webp`

6. `relatorios.webp`

7. `auditoria.webp`

8. fotos dos dispositivos de pagamento.

9. fotos de segmentos.

10. vídeo teaser + poster.

Para cada asset informar:

- onde será usado;
- proporção;
- resolução recomendada;
- formato.

Assim eu consigo produzir/enviar os arquivos corretamente.

---

# 23. NÃO DEIXAR PLACEHOLDER TÉCNICO VISÍVEL

Regra absoluta:

Em produção o visitante NUNCA deve visualizar:

- “pendente”;
- “asset pendente”;
- “screenshot pendente”;
- “vídeo em preparação”;
- TODO;
- caminho `/public/...`;
- caminho `/site/...`;
- instruções para desenvolvedor;
- notas da missão;
- texto explicando que algo ainda não foi implementado.

Quando algo não tiver asset:

ou ocultar,
ou usar fallback institucional apropriado.

---

# 24. LIMPEZA DO REPOSITÓRIO

Revisar também o commit anterior.

Não quero artefatos desnecessários versionados.

Verificar especialmente:

`frontend/tsconfig.tsbuildinfo`

Se for artefato gerado e não houver motivo explícito para versionamento, remover e colocar no `.gitignore`.

Também revisar arquivos como:

`web-painel.md`

`x.md`

Não remover automaticamente se tiverem finalidade real.

Mas identificar claramente:
- o que são;
- por que estão versionados;
- se pertencem ao produto;
- se são apenas arquivos temporários de missão/log.

Não quero lixo de execução acumulando no repositório.

---

# 25. TESTES / BUILD

O último commit não possui CI/status registrado no GitHub.

Nesta rodada, antes de declarar concluído:

Executar os checks já previstos pelo projeto.

Validar no mínimo o que for aplicável:

Frontend:
- lint;
- TypeScript;
- build.

Backend:
- checks;
- migrations;
- testes afetados;
- CommercialLead;
- signup público bloqueado.

Não alterar testes apenas para fazê-los passar sem resolver causa real.

Informar exatamente o que foi executado e o resultado.

---

# 26. RESPONSIVIDADE

Essa nova camada visual precisa funcionar de verdade em:

- desktop grande;
- notebook;
- tablet;
- mobile.

A presença de fotos não pode quebrar mobile.

No mobile:

- reorganizar fluxo;
- controlar crop;
- manter texto legível;
- evitar carrossel impossível de usar;
- manter CTA acessível;
- footer não pode virar uma lista gigante desorganizada.

---

# 27. PERFORMANCE

Com novas imagens e fotos, performance passa a ser ainda mais importante.

Aplicar:

- Next Image quando adequado;
- WebP/AVIF;
- `sizes`;
- dimensões corretas;
- lazy load abaixo da dobra;
- prioridade apenas no Hero quando necessário;
- poster otimizado;
- evitar carregar todos os assets pesados imediatamente.

O carrossel de equipamentos também não pode causar custo exagerado.

---

# 28. ACESSIBILIDADE

Fotos e screenshots precisam ter:

- alt coerente;
- sem descrição inútil;
- elementos decorativos corretamente marcados;
- contraste;
- foco;
- controle de movimento;
- `prefers-reduced-motion`.

Se houver movimento automático nas maquininhas, respeitar `prefers-reduced-motion`.

---

# 29. OBJETIVO VISUAL FINAL

Quero sair de:

“site correto, mas cru”

para:

“produto sério, visualmente forte e convincente”.

Quero mais:

FOTO.
PRODUTO.
OPERAÇÃO.
SCREENSHOT REAL.
EQUIPAMENTO REAL.
IDENTIDADE CORE.

E menos:

CARD.
ÍCONE.
TEXTO SOLTO.
PLACEHOLDER.
DECORAÇÃO GENÉRICA.

O site precisa passar a sensação de que o CORE existe, funciona e está sendo construído por uma empresa que conhece operação presencial.

---

# 30. ORDEM DE EXECUÇÃO

Executar em blocos controlados.

## WEB-REFINO-1 — CORREÇÕES DE PUBLICAÇÃO

Primeiro resolver:

- textos internos vazando para a interface;
- placeholders técnicos;
- `ProductEvidence`;
- fallback do vídeo;
- numeração 01/02;
- link “Empresa”;
- problemas de deploy do e-mail;
- controle `public_signup_enabled` no Platform Admin;
- limpeza técnica evidente.

## WEB-REFINO-2 — HOME VISUAL

Depois:

- Hero com imagem;
- fluxo “O que o CORE conecta”;
- CORE POS;
- Backoffice;
- pagamentos/equipamentos;
- segmentos/fotos;
- segurança/auditoria.

## WEB-REFINO-3 — FOOTER + COOKIES

Depois:

- novo Footer;
- Cookie Consent;
- preferências;
- estrutura legal.

## WEB-REFINO-4 — `/solucoes`

Aplicar a mesma qualidade visual e remover copy inadequada.

## WEB-REFINO-5 — QUALIDADE FINAL

- mobile;
- acessibilidade;
- performance;
- SEO;
- build;
- lint;
- testes;
- limpeza.

Não sair alterando tudo sem controle.

---

# 31. ENTREGA FINAL

Ao terminar cada bloco, informe:

1. resumo;
2. arquivos alterados;
3. arquivos criados;
4. arquivos removidos;
5. componentes criados;
6. componentes substituídos;
7. correções de copy;
8. correções backend;
9. alterações no `docker-stack.yml`;
10. configuração SMTP necessária;
11. como ficou `public_signup_enabled`;
12. como funciona o Cookie Consent;
13. quais cookies são considerados necessários;
14. quais scripts ficam condicionados a consentimento;
15. assets que faltam;
16. especificação exata de cada asset;
17. comandos de validação executados;
18. resultado de lint/build/test;
19. pendências restantes.

Não responda apenas “feito”.

---

# PRINCÍPIO FINAL

Não quero que você reinvente novamente a identidade que acabou de ser construída.

Quero amadurecê-la.

O problema agora não é falta de estrutura.

É falta de acabamento, imagens reais, presença visual e alguns ajustes técnicos.

O CORE precisa parecer menos uma página montada por componentes e mais uma marca de software real.

CORE POS = operação.

CORE Backoffice = gestão.

O site conecta os dois.

E o produto real, as fotografias, equipamentos e screenshots devem fazer cada vez mais parte da narrativa visual.