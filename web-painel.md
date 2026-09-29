Quero que você reformule completamente o site institucional público do CORE PDV.

Antes de alterar qualquer arquivo, analise o projeto atual, entenda a arquitetura existente e reutilize obrigatoriamente a stack, os padrões, os componentes e os tokens já usados no projeto.

Não quero outro projeto separado.

STACK ATUAL:

Frontend:
- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4

Backend:
- Django
- Django REST Framework
- PostgreSQL

O objetivo é reinventar o institucional do CORE, sem alterar desnecessariamente o Backoffice autenticado ou o CORE POS.

---

# 1. OBJETIVO DO NOVO SITE

O novo site precisa:

- apresentar profissionalmente o CORE;
- explicar claramente o produto;
- diferenciar CORE POS de CORE Backoffice;
- mostrar as principais soluções;
- transmitir confiança;
- gerar leads comerciais;
- servir também como apresentação institucional para clientes, parceiros, adquirentes e empresas que estiverem avaliando o CORE;
- eliminar a aparência atual de landing page genérica.

O resultado precisa parecer desenvolvido por uma equipe de produto/design que realmente conhece o sistema.

---

# 2. REGRA VISUAL PRINCIPAL

O SITE NÃO PODE PARECER FEITO POR IA.

Evite completamente padrões visuais genéricos de sites criados automaticamente.

NÃO usar:

- fonte serifada;
- títulos serifados;
- emojis;
- fundos quadriculados;
- grid decorativo;
- fundo com pontinhos;
- glow azul em tudo;
- neon;
- blur exagerado;
- glassmorphism;
- gradientes aleatórios;
- cards para absolutamente tudo;
- dezenas de quadrados com ícones genéricos;
- ícones apenas para preencher espaço;
- ilustrações genéricas;
- imagens criadas por IA;
- elementos 3D genéricos;
- robôs;
- foguetes;
- formas abstratas aleatórias;
- mockups falsos;
- dashboards falsos;
- gráficos inventados;
- números fictícios;
- depoimentos fictícios;
- logos fictícios;
- clientes fictícios;
- contadores falsos;
- slogans genéricos de startup;
- animações apenas para enfeite.

Evitar aparência de:

- template do Framer;
- v0;
- landing page genérica de SaaS;
- site de startup de IA;
- fintech neon;
- crypto.

O CORE precisa ter identidade própria.

---

# 3. DIREÇÃO VISUAL

Quero um site:

- moderno;
- limpo;
- profissional;
- tecnológico;
- operacional;
- brasileiro;
- confiável;
- premium sem exagero.

O PRODUTO deve ser o principal elemento visual.

Priorizar:

- bastante espaço em branco;
- tipografia sans-serif forte;
- hierarquia clara;
- títulos grandes, mas sem exagero;
- screenshots reais;
- imagens reais;
- vídeos reais;
- blocos visuais maiores;
- menos cards;
- divisões claras entre assuntos;
- azul CORE utilizado com controle;
- bordas e superfícies discretas;
- animações sutis somente quando fizerem sentido.

Não inventar visual apenas para preencher espaço.

---

# 4. IDENTIDADE VISUAL OFICIAL

Utilizar a identidade atual do CORE.

Primary:
#3454D1

Primary Dark:
#2945B6

Texto principal:
#283C50

Canvas:
#F0F2F8

Surface:
#FFFFFF

Muted:
#64748B

Border:
#E2E8F0

Success:
#17C666

Warning:
#FFA21D

Danger:
#EA4D4D

Dark mode:

Canvas:
#101722

Surface:
#182230

Surface muted:
#222F40

Surface raised:
#1D2A3A

Texto:
#E4EBF3

Muted:
#A9B7C8

Border:
#344458

Focus:
#91A4FF

Não transformar o dark mode em neon.

---

# 5. PRODUTO REAL COMO ELEMENTO VISUAL

Hoje o site possui elementos ilustrativos/fictícios que fazem parecer uma landing page de template.

Quero eliminar isso.

Não criar dashboard fictício em JSX.

Não criar gráfico falso.

Não inventar métricas para parecer que o sistema está funcionando.

Não criar browser fake com números inventados.

Quero utilizar screenshots REAIS do CORE.

Prepare a arquitetura de assets para receber imagens como:

- dashboard;
- venda rápida;
- seleção de operador;
- mesas;
- pagamentos;
- produtos;
- estoque;
- compras;
- relatórios;
- financeiro;
- filiais;
- usuários;
- CORE POS em dispositivo real;
- produção/impressão.

Exemplo de organização:

`/public/site/screenshots/`
`/public/site/videos/`
`/public/site/images/`

Se algum asset ainda não existir, NÃO inventar uma interface para substituir.

Deixe um placeholder técnico discreto ou documente o asset pendente.

---

# 6. POSICIONAMENTO DO CORE

Existe uma separação fundamental que o site precisa deixar clara.

## CORE POS = OPERAÇÃO

A operação acontece no CORE POS.

Exemplos:

- venda;
- atendimento;
- operador;
- caixa;
- mesas;
- comandas;
- pedidos;
- pagamentos;
- impressão;
- produção;
- fechamento operacional.

## CORE BACKOFFICE = GESTÃO

A gestão acontece no CORE Backoffice.

Exemplos:

- dashboard;
- produtos;
- estoque;
- compras;
- fornecedores;
- relatórios;
- financeiro;
- filiais;
- usuários;
- permissões;
- auditoria;
- configurações;
- integrações.

Não apresentar operações do POS como se acontecessem no Backoffice.

O site precisa comunicar que os dois trabalham juntos, mas possuem papéis diferentes.

---

# 7. NAVEGAÇÃO PRINCIPAL

Reestruturar a navegação pública pensando em:

- Home
- Soluções
- Integrações
- Segmentos
- Planos
- Empresa
- Ajuda

Na área direita:

- Entrar
- Solicitar demonstração

Adicionar `/solucoes`.

Criar também `/contato`.

Outras páginas podem ser criadas conforme necessidade real da arquitetura, mas não inventar páginas vazias apenas para encher menu.

---

# 8. HOME

Quero reconstruir a Home.

Ela precisa contar uma história mais profissional.

Uma direção possível:

1. Hero
2. O que o CORE conecta
3. Teaser em vídeo
4. CORE POS
5. CORE Backoffice
6. Fluxo conectado
7. Principais soluções
8. Multiempresa / multifilial
9. Pagamentos e integrações
10. Segmentos
11. CTA comercial final

---

# 9. HERO

A comunicação deve caminhar para algo como:

“Sua operação inteira. Conectada pelo CORE.”

ou:

“Seu negócio acontece em vários lugares. O CORE conecta todos eles.”

Texto conceitual:

“PDV, pagamentos, mesas, estoque, compras, financeiro e gestão em uma plataforma criada para operações que não podem parar.”

Não precisa utilizar exatamente essas frases.

Escreva algo profissional e direto, sem slogan vazio.

CTA principal:

“Solicitar demonstração”

→ `/contato`

CTA secundário:

“Ver o CORE em ação”

→ seção do teaser.

Manter:

“Entrar”

→ `/login`

para clientes existentes.

---

# 10. TEASER EM VÍDEO

Quero uma seção importante na Home mostrando o CORE em funcionamento através de vídeo.

Não criar animação falsa do sistema.

Não reconstruir telas em HTML.

O vídeo posteriormente será produzido utilizando:

- CORE POS real;
- CORE Backoffice real;
- fluxos reais;
- screenshots reais;
- eventualmente equipamentos reais.

Preparar o site para receber assets como:

`/public/site/videos/core-teaser.mp4`

e:

`/public/site/videos/core-teaser-poster.webp`

A seção pode utilizar uma comunicação como:

“Veja o CORE em operação.”

ou:

“Do atendimento à gestão. Veja como o CORE conecta sua operação.”

O vídeo deve mostrar conceitualmente:

CORE POS
→ operação
→ venda
→ pagamento
→ estoque/processos
→ Backoffice
→ gestão.

Implementar player de forma profissional.

Requisitos:

- sem autoplay com áudio;
- responsivo;
- poster otimizado;
- controles adequados;
- carregamento eficiente;
- possibilidade de abrir em modal ou reproduzir inline;
- acessibilidade;
- sem player visualmente poluído.

Enquanto o vídeo final não existir, deixar estrutura pronta e asset pendente claramente documentado.

---

# 11. CORE POS NA HOME

Criar uma seção específica para o CORE POS.

Mensagem principal:

“A operação acontece aqui.”

Mostrar e explicar de forma realista:

- venda rápida;
- operadores;
- atendimento;
- mesas;
- pedidos;
- pagamentos;
- impressão;
- fluxo operacional.

Utilizar screenshots/fotos reais quando disponíveis.

Não criar mockup falso de POS.

---

# 12. CORE BACKOFFICE NA HOME

Criar seção específica para o Backoffice.

Mensagem principal:

“A gestão acontece aqui.”

Mostrar:

- dashboard;
- produtos;
- estoque;
- compras;
- relatórios;
- financeiro;
- filiais;
- usuários;
- acompanhamento da operação.

Utilizar produto real como prova.

---

# 13. FLUXO CONECTADO

Mostrar de forma simples que os módulos trabalham juntos.

Por exemplo:

Venda
→ Pagamento
→ Caixa
→ Estoque
→ Gestão

Não precisa transformar isso em cards.

Pode utilizar tipografia, linhas, setas e screenshots reais.

Precisa parecer um fluxo de produto, não um infográfico de template.

---

# 14. `/solucoes`

Criar página:

`/solucoes`

Essa página deve apresentar as principais áreas do CORE.

Não quero uma grade com dezenas de cards genéricos.

Estruture por fluxos reais.

## CORE POS / VENDAS

Mostrar:

- venda;
- operadores;
- caixa;
- atendimento;
- descontos/permissões;
- fluxo operacional.

Sempre deixando claro que acontece no CORE POS.

---

## MESAS E COMANDAS

Mostrar:

- mesas;
- atendimento;
- pedido;
- itens;
- divisão;
- fechamento.

Não inventar funcionalidades.

Verifique o estado real do produto e o roadmap antes de escrever afirmações definitivas.

---

## PAGAMENTOS

Direção de comunicação:

“Pagamento faz parte da venda. Não deveria ser outro processo.”

Explicar arquitetura de pagamentos integrada ao fluxo da venda.

Não afirmar parceria ou homologação sem comprovação.

---

## ESTOQUE E COMPRAS

Mostrar:

Compra
→ Entrada
→ Estoque
→ Transferência
→ Venda
→ Perda
→ Inventário

Explicar rastreabilidade das movimentações.

---

## GESTÃO E RELATÓRIOS

Apresentar o Backoffice.

Mostrar:

- dashboards;
- vendas;
- recebimentos;
- estoque;
- CMV;
- performance;
- relatórios;
- financeiro.

---

## MULTIEMPRESA E MULTIFILIAL

Mostrar arquitetura:

Empresa
→ Filiais
→ Usuários
→ Dispositivos

Mensagem conceitual:

“Uma loja ou várias. O controle continua no mesmo lugar.”

---

## SEGURANÇA E AUDITORIA

Mostrar apenas o que realmente existe ou está previsto oficialmente.

Exemplos:

- RBAC;
- permissões;
- contexto de filial;
- dispositivos;
- sessões;
- auditoria;
- isolamento entre tenants;
- API segura.

Não inventar certificações.

---

# 15. PAGAMENTOS E INTEGRAÇÕES

Muito cuidado com essa parte.

Não inventar:

- parceria;
- homologação;
- aprovação;
- certificação;
- clientes;
- transações;
- números comerciais;
- disponibilidade.

Antes de exibir nome/logo/status de:

- Stone;
- Cielo;
- Rede;
- Getnet;
- Mercado Pago;
- qualquer outro provider;

verifique o estado real da integração no projeto.

Se não houver segurança sobre o status, utilizar comunicação genérica:

“Arquitetura preparada para múltiplos provedores de pagamento.”

Não utilizar logo de terceiros sem base real para isso.

---

# 16. SEGMENTOS

Não posicionar o CORE exclusivamente como sistema para restaurante.

Pode trabalhar segmentos compatíveis como:

- bares;
- restaurantes;
- lounges;
- casas noturnas;
- casas de eventos;
- pizzarias;
- lanchonetes;
- food service;
- varejo;
- outras operações presenciais compatíveis.

Não inventar funcionalidades específicas de um segmento se elas não existem.

---

# 17. CAPTAÇÃO DE CLIENTES

Neste momento o site NÃO terá contratação automática.

O visitante NÃO deve conseguir:

- criar Tenant sozinho;
- criar Empresa sozinho;
- criar Owner sozinho;
- iniciar assinatura automaticamente;
- pagar online;
- cadastrar cartão;
- comprar plano sem contato comercial.

O fluxo será:

Visitante
→ site CORE
→ Solicitar demonstração
→ formulário
→ Lead salvo
→ equipe CORE recebe
→ contato humano
→ criação do cliente posteriormente.

---

# 18. `/contato`

Criar página:

`/contato`

Formulário simples.

Campos:

- Nome
- Empresa
- WhatsApp
- E-mail
- Segmento
- Mensagem opcional

Capturar automaticamente quando disponível:

- página de origem;
- plano de interesse;
- utm_source;
- utm_medium;
- utm_campaign.

Não pedir dados desnecessários.

Não pedir:

- senha;
- cartão;
- dados bancários;
- CNPJ obrigatoriamente.

CTA:

“Quero conhecer o CORE”

Após sucesso:

“Recebemos seu contato. Nossa equipe falará com você.”

Não dizer que conta foi criada.

---

# 19. BACKEND DE LEADS

Utilizar obrigatoriamente o backend Django/DRF já existente.

Não criar backend paralelo.

Criar uma entidade comercial simples.

Sugestão:

`CommercialLead`

Campos possíveis:

- id
- name
- company_name
- whatsapp
- email
- segment
- message
- source_path
- plan_interest
- utm_source
- utm_medium
- utm_campaign
- status
- created_at
- updated_at

Status inicial:

`NEW`

Pode preparar enum para futura evolução como:

- NEW
- CONTACTED
- QUALIFIED
- LOST
- CONVERTED

Mas NÃO desenvolver CRM completo agora.

---

# 20. ENDPOINT DE LEADS

Criar endpoint público coerente com a arquitetura atual.

Por exemplo:

`POST /api/v1/public/leads/`

ou equivalente seguindo o padrão existente.

Implementar:

- serializer;
- validação;
- normalização;
- rate limiting;
- tratamento de erro;
- proteção básica contra spam;
- honeypot simples se fizer sentido.

Não armazenar dados desnecessários.

---

# 21. REGRA CRÍTICA DE ENVIO

Primeiro:

SALVAR O LEAD NO BANCO.

Depois:

TENTAR ENVIAR A NOTIFICAÇÃO.

Se o SMTP falhar:

O lead NÃO pode ser perdido.

Se o lead foi salvo corretamente, o frontend não deve informar ao visitante que o envio do formulário falhou somente porque a notificação de e-mail falhou.

Registrar o erro técnico adequadamente para acompanhamento.

---

# 22. E-MAIL COMERCIAL

Reutilizar a infraestrutura Django Mail / SMTP existente.

Não hardcode meu e-mail no código.

Criar configuração própria.

Exemplo:

`SALES_LEAD_EMAIL`

ou configuração equivalente dentro das configurações globais se isso fizer mais sentido no projeto.

O e-mail recebido deve conter:

- nome;
- empresa;
- WhatsApp;
- e-mail;
- segmento;
- mensagem;
- página de origem;
- plano de interesse;
- UTMs;
- data/hora.

---

# 23. SELF-SERVICE PÚBLICO ATUAL

Hoje existe arquitetura pública de signup.

Não destruir essa arquitetura.

Ela poderá ser utilizada futuramente.

Preservar:

- provisioning;
- criação automática de Owner;
- empresa;
- filial;
- trial;
- billing mode;
- auto approve;
- estruturas já desenvolvidas.

Porém ela deve ficar DESATIVADA publicamente neste momento.

Não basta remover o botão no frontend.

O backend também precisa impedir provisionamento público.

Criar configuração clara, preferencialmente integrada à configuração SaaS atual.

Exemplo:

`public_signup_enabled = False`

Quando estiver desativado:

`PublicSignupView`

não deve provisionar clientes.

Retornar resposta apropriada orientando para contato comercial.

Preservar tudo necessário para reativação futura.

---

# 24. `/cadastro`

A rota atual:

`/cadastro`

não deve mais criar contas.

Redirecionar:

`/cadastro`
→ `/contato`

Preservar query params relevantes.

Exemplo:

`/cadastro?plano=123`

deve virar:

`/contato?plano=123`

---

# 25. `/planos`

Os planos podem continuar sendo exibidos.

Mas os CTAs precisam mudar.

Remover comportamento de contratação automática.

Utilizar algo como:

“Falar sobre este plano”

ou:

“Solicitar demonstração”

Destino:

`/contato?plano=<id>`

O formulário deve reconhecer automaticamente o plano selecionado.

Não iniciar checkout.

Não solicitar cartão.

---

# 26. HEADER

Atualizar o Header público.

Adicionar:

“Soluções”

Substituir:

“Criar conta”

por:

“Solicitar demonstração”

Manter:

“Entrar”

Também organizar melhor a navegação para não ficar com aparência de menu improvisado.

---

# 27. FOOTER

Reformular o Footer para transmitir empresa real.

Adicionar links institucionais relevantes:

- Soluções
- Integrações
- Segmentos
- Planos
- Segurança
- Empresa
- Ajuda
- Contato
- Privacidade
- Termos
- Área do cliente

Deixar preparado para informações reais como:

- CORE PDV;
- razão social;
- CNPJ;
- e-mail comercial;
- suporte;
- cidade/estado;
- redes oficiais.

Não inventar dados ausentes.

---

# 28. RESPONSIVIDADE

Desktop e mobile precisam ser tratados corretamente.

Não simplesmente diminuir o desktop.

Revisar:

- Header;
- menu;
- Hero;
- vídeo;
- screenshots;
- textos;
- soluções;
- planos;
- formulário;
- CTAs;
- Footer.

---

# 29. PERFORMANCE

Não sacrificar performance em nome do visual.

Evitar:

- bibliotecas pesadas sem necessidade;
- WebGL;
- animações exageradas;
- vídeos carregados imediatamente sem necessidade;
- imagens gigantes.

Usar quando apropriado:

- Next Image;
- WebP;
- AVIF;
- lazy loading;
- poster de vídeo;
- preload somente para recursos críticos.

---

# 30. ACESSIBILIDADE

Manter:

- HTML semântico;
- headings corretos;
- contraste;
- navegação por teclado;
- focus visible;
- aria quando necessário;
- alt text;
- prefers-reduced-motion.

---

# 31. SEO

Revisar metadata de cada página.

Direção conceitual:

Title:
“CORE PDV | PDV, gestão e pagamentos para sua operação”

Description:
“Conecte vendas, caixa, estoque, mesas, compras, pagamentos e gestão em uma única plataforma.”

Pode melhorar a redação.

Criar metadata específica por página.

Preparar Structured Data factual quando adequado:

- Organization;
- SoftwareApplication.

Não inventar:

- avaliações;
- estrelas;
- quantidade de clientes;
- reviews.

---

# 32. CÓDIGO

Não concentrar o institucional inteiro dentro de um único `page.tsx`.

Criar componentes reutilizáveis quando realmente fizer sentido.

Por outro lado:

NÃO criar componente para cada pequeno elemento apenas para parecer arquitetura sofisticada.

Quero código:

- simples;
- legível;
- consistente;
- reutilizável;
- alinhado ao restante do projeto.

Reutilizar componentes existentes quando forem bons.

Remover componentes antigos somente depois de confirmar que não são usados.

Não deixar legado morto.

---

# 33. NÃO ALTERAR SEM NECESSIDADE

Não mexer desnecessariamente em:

- CORE POS;
- regras de negócio operacionais;
- estoque;
- pagamentos internos;
- RBAC;
- permissions;
- Backoffice autenticado;
- CORE Admin;
- arquitetura SaaS interna.

Mudanças backend desta missão devem ficar restritas principalmente a:

- Leads;
- e-mail comercial;
- bloqueio seguro do signup público.

---

# 34. CONTEÚDO

Não usar Lorem Ipsum.

Não criar texto genérico só para preencher espaço.

Toda afirmação precisa estar baseada:

- no produto atual;
- na arquitetura atual;
- ou no roadmap oficialmente definido.

Se não souber se uma funcionalidade realmente existe:

NÃO INVENTE.

Marque para validação.

---

# 35. ORDEM DE EXECUÇÃO

Primeiro faça uma análise do site atual e dos arquivos afetados.

Depois execute em blocos.

Sugestão:

## WEB-1
Fundação visual + arquitetura do institucional.

## WEB-2
Header + Home + Footer.

## WEB-3
`/solucoes`.

## WEB-4
`/contato` + backend de Leads + e-mail.

## WEB-5
Bloqueio do signup público + `/cadastro` redirect + atualização de `/planos`.

## WEB-6
Teaser em vídeo + preparação dos assets reais.

## WEB-7
Integrações / Segmentos / Empresa / Segurança e demais páginas institucionais necessárias.

## WEB-8
SEO + acessibilidade + performance + limpeza de legado.

Pode reorganizar se encontrar uma divisão tecnicamente melhor depois de analisar o projeto, mas não misture toda a implementação sem controle.

---

# 36. CRITÉRIOS DE ACEITE

O novo site NÃO pode:

- parecer criado por IA;
- utilizar fonte serifada;
- utilizar fundo quadriculado;
- utilizar emojis;
- utilizar glow excessivo;
- utilizar glassmorphism exagerado;
- utilizar dezenas de cards iguais;
- possuir dashboard fake;
- possuir gráficos inventados;
- possuir números inventados;
- confundir CORE POS com Backoffice;
- permitir criação automática de cliente;
- iniciar checkout;
- afirmar parceria inexistente;
- inventar funcionalidades;
- inventar certificações;
- utilizar imagens falsas do produto.

O novo site DEVE:

- possuir identidade CORE;
- parecer profissional;
- apresentar produto real;
- explicar CORE POS;
- explicar CORE Backoffice;
- possuir `/solucoes`;
- possuir `/contato`;
- captar leads;
- enviar notificação comercial;
- manter signup automático desativado publicamente;
- preservar arquitetura futura;
- ter teaser em vídeo;
- ser responsivo;
- ter boa performance;
- possuir SEO básico;
- possuir acessibilidade adequada.

---

# 37. ENTREGA

Ao concluir cada bloco, me entregue objetivamente:

1. resumo do que foi feito;
2. arquivos alterados;
3. arquivos criados;
4. migrations criadas;
5. endpoints criados;
6. endpoints alterados;
7. componentes removidos;
8. legado removido;
9. mudanças de navegação;
10. fluxo comercial final;
11. configuração necessária para e-mail comercial;
12. como ficou o bloqueio do signup público;
13. assets reais que ainda preciso fornecer;
14. funcionalidades citadas no site que foram validadas no código;
15. pendências ou riscos encontrados.

Não responda apenas “feito”.

Quero conseguir validar tecnicamente cada entrega.

# PRINCÍPIO FINAL

Não invente o CORE para melhorar o marketing.

Mostre melhor o produto que já existe.

CORE POS representa a operação.

CORE Backoffice representa gestão e controle.

O site deve conectar essas duas histórias, transmitir confiança e transformar interesse em contato comercial.

Quero um site que pareça um produto de software real e consolidado, não uma landing page criada automaticamente.