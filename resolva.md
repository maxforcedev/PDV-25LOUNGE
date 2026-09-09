HOTFIX POS-4 — CORRIGIR RETORNO DA CÂMERA + SCANNER REAL DE PRODUTO NO VENDA RÁPIDA

Revise o código ATUAL antes de alterar.

NÃO avançar POS-5.
NÃO iniciar POS-6.
NÃO mexer no relatório de Tickets agora.
NÃO trocar mobile_scanner.
NÃO reescrever backend que já funciona.

Temos DOIS bugs de runtime confirmados.

==================================================
1. BUG CONFIRMADO — "VALIDAR OUTRO TICKET" NÃO VOLTA COM A CÂMERA
==================================================

Cenário REAL:

1. entra no Validador;
2. câmera aparece;
3. escaneia Ticket;
4. consulta;
5. valida;
6. sucesso;
7. toca "VALIDAR OUTRO TICKET";
8. volta para a tela de scanner;
9. MAS a câmera não funciona/aparece corretamente.

Se sair do módulo e entrar pelo Home:
→ câmera funciona novamente.

Reproduzir exatamente antes de corrigir.

==================================================
2. CAUSA A REVISAR NO CÓDIGO ATUAL
==================================================

Hoje o MobileScanner só existe dentro do painel de scanning/lookup.

Durante REVIEWING/SUCCESS:
→ widget da câmera sai da árvore.

No `_reset()` atual ocorre conceitualmente:

setState:
  state = SCANNING

imediatamente:
  await scanner.start()

O problema é que `setState` apenas agenda o rebuild.

Portanto `scanner.start()` pode estar sendo executado ANTES de o novo
`MobileScanner` estar montado/anexado novamente.

NÃO corrigir usando Navigator.pop/push.
NÃO obrigar usuário a voltar ao Home.

==================================================
3. CORREÇÃO DO LIFECYCLE
==================================================

Ao tocar:

VALIDAR OUTRO TICKET

fazer:

A. limpar estado da operação anterior;

B. mudar state para SCANNING;

C. aguardar o frame em que o MobileScanner foi realmente remontado;

D. somente DEPOIS iniciar/resumir o controller.

Usar mecanismo Flutter apropriado, como:

WidgetsBinding.instance.endOfFrame

ou post-frame callback seguro.

Não usar delay arbitrário como:

Future.delayed(500ms)

como solução definitiva.

Fluxo esperado conceitualmente:

setState(() {
  state = SCANNING;
  limpa ticket;
  limpa código;
  limpa quantidade;
  limpa resultado;
  limpa idempotência concluída;
});

aguardar próximo frame;

se mounted && state == SCANNING:
  iniciar/resumir scanner de acordo com estado REAL do controller.

==================================================
4. NÃO DUPLICAR START
==================================================

Antes de chamar start/resume:

verificar a API REAL do mobile_scanner 7.1.3 e o estado do controller.

Não gerar:

start()
start()
start()

em rebuilds sucessivos.

A inicialização deve ser idempotente do ponto de vista da UI.

Tratar corretamente casos em que:

- já está rodando;
- está parado;
- ainda está iniciando;
- widget foi desmontado;
- página foi fechada.

==================================================
5. TODOS OS RETORNOS DEVEM REATIVAR CÂMERA
==================================================

Testar:

Ticket válido
→ sucesso
→ Validar outro
→ câmera.

Ticket USED
→ Validar outro
→ câmera.

Ticket CANCELLED
→ Validar outro
→ câmera.

Ticket PARTIALLY_USED
→ entrega
→ Validar outro
→ câmera.

QR inexistente
→ tentar novamente
→ câmera.

Erro de rede
→ tentar novamente
→ câmera.

Cancelar revisão
→ câmera.

NENHUM fluxo pode exigir sair para o menu.

==================================================
6. TESTE MANUAL OBRIGATÓRIO
==================================================

SEM SAIR DO VALIDADOR:

Ticket A
→ scan
→ validar
→ VALIDAR OUTRO TICKET
→ câmera

Ticket B
→ scan
→ validar
→ VALIDAR OUTRO TICKET
→ câmera

Ticket C
→ scan

Fazer 3 scans consecutivos.

Se precisar sair pelo Home:
→ BUG NÃO CORRIGIDO.

==================================================
7. VENDA RÁPIDA — BOTÃO DE SCANNER NÃO É SCANNER HOJE
==================================================

BUG/IMPLEMENTAÇÃO INCOMPLETA CONFIRMADA.

Hoje existe um ícone:

qr_code_scanner

mas ele chama:

onBarcode: _barcode

E `_barcode()` apenas lê:

_search.text

e consulta:

quickSaleBarcode(barcode)

Isso NÃO abre câmera.

Portanto o botão visualmente promete "escanear", mas tecnicamente é apenas
uma consulta do texto já digitado.

Corrigir.

==================================================
8. SCANNER REAL DE CÓDIGO DE BARRAS NO VENDA RÁPIDA
==================================================

Ao tocar no botão de scanner da Venda Rápida:

→ abrir CÂMERA REAL;
→ utilizar mobile_scanner que já está instalado;
→ ler código de barras comercial;
→ obter rawValue;
→ chamar o endpoint existente de barcode;
→ localizar produto;
→ adicionar produto ao carrinho.

Fluxo:

VENDA RÁPIDA

[ busca........................ ][ SCANNER ]

toca SCANNER

↓


┌─────────────────────────────┐
│   ESCANEAR PRODUTO          │
│                             │
│       CÂMERA REAL           │
│                             │
│     ┌───────────────┐       │
│     │               │       │
│     │ CÓDIGO BARRAS │       │
│     │               │       │
│     └───────────────┘       │
│                             │
│ Aponte para o código        │
│ de barras do produto        │
│                             │
│ [ CANCELAR ]                │
└─────────────────────────────┘

==================================================
9. NÃO CONFUNDIR QR DE TICKET COM BARCODE DE PRODUTO
==================================================

VALIDADOR:

QR
→ validation_code
→ Ticket

VENDA RÁPIDA:

EAN/GTIN/Code128/etc
→ Product.barcode
→ Produto

Não usar endpoint de Ticket.

O Venda Rápida continua usando:

quickSaleBarcode(barcode)

e o endpoint já existente:

GET /api/v1/pos/products/barcode/{barcode}/

==================================================
10. USAR O BACKEND QUE JÁ EXISTE
==================================================

O backend atual de barcode já:

- deriva filial do device;
- exige sales.create;
- filtra empresa;
- filtra ativo;
- filtra não arquivado;
- exige vendável;
- respeita ProductBranchConfig;
- respeita COUNTER;
- respeita disponibilidade;
- retorna payload operacional do catálogo.

PRESERVAR.

Não criar endpoint paralelo.

==================================================
11. CÂMERA DO VENDA RÁPIDA
==================================================

Pode reutilizar `mobile_scanner`.

Preferir um componente genérico e pequeno SOMENTE se isso reduzir duplicação
sem arriscar o Validador.

Exemplo conceitual:

CodeScannerView

responsabilidade:
→ abrir câmera;
→ devolver rawValue;
→ controlar debounce;
→ controlar lifecycle.

NÃO colocar dentro dele:

- regra de Ticket;
- regra de Produto;
- regra de estoque;
- regra de carrinho.

Ele só lê código.

==================================================
12. LEITURA DO PRODUTO
==================================================

Ao detectar barcode:

- impedir múltiplas leituras do mesmo frame;
- pausar temporariamente;
- consultar backend;
- se encontrar:
    adicionar produto;
- dar feedback visual;
- preparar próxima leitura.

Não gerar 5 adições porque a câmera viu o mesmo barcode durante 5 frames.

Implementar debounce/trava por leitura.

==================================================
13. MODO DE SCANNER PARA CAIXA
==================================================

Quero que seja útil para operação real.

Ideal:

abre scanner uma vez

scan Coca
→ adiciona

scan Heineken
→ adiciona

scan Água
→ adiciona

sem precisar fechar e abrir a câmera para cada produto.

Adicionar botão:

[ CONCLUIR / VOLTAR À VENDA ]

Então o operador consegue passar vários produtos em sequência.

==================================================
14. PRODUTO REPETIDO
==================================================

Se escanear o MESMO produto simples várias vezes:

scan Heineken
→ Qtd. 1

scan Heineken novamente
→ Qtd. 2

scan novamente
→ Qtd. 3

Não quero três linhas idênticas:

Heineken 1
Heineken 1
Heineken 1

quando não existem modificadores/observações/descontos diferentes.

Para item simples e equivalente:
→ incrementar quantidade da linha existente.

IMPORTANTE:

NÃO mesclar automaticamente linhas que tenham diferenças como:

- modificadores;
- observação;
- desconto do item;
- configuração diferente.

==================================================
15. PRODUTO COM MODIFICADOR
==================================================

Se o produto escaneado exigir configuração/modificadores:

→ pausar scanner;
→ abrir editor de item já existente;
→ operador configura;
→ salva;
→ volta ao scanner;
→ câmera continua funcionando.

Não adicionar configuração inválida silenciosamente.

==================================================
16. PRODUTO NÃO ENCONTRADO
==================================================

Mostrar:

"Produto não encontrado para este código de barras."

Não fechar módulo inteiro.

Depois:

→ scanner volta;
→ pronto para próximo código.

==================================================
17. PRODUTO SEM ESTOQUE / NÃO VENDÁVEL
==================================================

Preservar regras já existentes.

Barcode não é bypass.

Se produto não puder ser vendido:

→ não adicionar;
→ mostrar mensagem existente/amigável;
→ scanner continua disponível.

==================================================
18. MANTER BUSCA MANUAL
==================================================

O campo:

Produto, código ou código de barras

continua funcionando.

Enter/HID continua podendo consultar barcode.

A câmera é uma opção ADICIONAL real.

Não remover leitor físico como teclado.

Portanto teremos:

A. nome digitado;
B. código interno;
C. barcode digitado;
D. leitor HID;
E. câmera.

==================================================
19. PERMISSÃO DE CÂMERA
==================================================

O projeto já usa mobile_scanner no Ticket.

Revisar também AndroidManifest/configuração.

Não duplicar permissões desnecessariamente.

Se câmera for negada:

mostrar mensagem amigável
+
permitir voltar
+
manter busca manual.

==================================================
20. TESTE REAL OBRIGATÓRIO — VENDA RÁPIDA
==================================================

Teste na máquina/dispositivo:

1. abrir Venda Rápida;
2. tocar ícone scanner;
3. câmera abre;
4. apontar para barcode real;
5. produto encontrado;
6. produto entra no carrinho;
7. câmera continua disponível;
8. escanear segundo produto;
9. segundo entra;
10. escanear primeiro novamente;
11. quantidade do primeiro aumenta;
12. fechar scanner;
13. carrinho permanece correto.

Se tocar o ícone e apenas tentar buscar o texto do campo:

→ NÃO ESTÁ IMPLEMENTADO.

==================================================
21. NÃO MEXER AGORA
==================================================

Não mexer:

- relatório de Tickets;
- impressão;
- POS-5;
- POS-6;
- Stone pagamento;
- cancelamento financeiro;
- estoque backend;
- checkout;
- preview;
- pagamentos.

Escopo desta rodada:

A. reativação correta da câmera do Ticket;
B. scanner REAL de produto no Venda Rápida.

==================================================
22. CHECKPOINT
==================================================

Ao terminar informar:

1. causa raiz exata da câmera do Ticket não voltar;
2. como foi corrigido o lifecycle;
3. confirmação de 3 tickets consecutivos sem sair do módulo;
4. como foi implementada a câmera no Venda Rápida;
5. componente/biblioteca utilizada;
6. confirmação de barcode REAL lido pela câmera;
7. confirmação de múltiplos produtos escaneados na mesma sessão;
8. comportamento para produto repetido;
9. comportamento para produto com modificadores;
10. comportamento de produto inexistente;
11. comportamento sem estoque;
12. arquivos alterados;
13. testes executados;
14. confirmação de que POS-5/POS-6 não foram iniciados.

PARE.