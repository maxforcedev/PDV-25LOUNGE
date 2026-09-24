Continue no HEAD atual.

Nova missão: **ao fechar a mesa, o sistema deve emitir automaticamente um cupom final parecido com o exemplo enviado pelo usuário**.

Use a imagem de referência **apenas como referência visual/estrutural** do cupom:
- simples;
- térmico;
- texto puro;
- largura 58mm/80mm;
- sem visual “fiscal”;
- com cara de relatório/recibo gerencial.

## OBJETIVO

Quando a mesa for fechada com sucesso, o POS deve emitir um **cupom final de fechamento da mesa** semelhante ao modelo enviado.

Esse cupom **não é NFC-e**, **não é cupom fiscal**, **não é SAT**.

É um:

```text
RELATÓRIO GERENCIAL
NÃO É DOCUMENTO FISCAL
1. TIPO DE DOCUMENTO

Usar o fluxo de documento final da mesa.

Preservar a arquitetura de documentos já existente.

O fechamento da mesa deve emitir:

TABLE_FINAL_RECEIPT

Não usar:

TABLE_CONFERENCE para isso;
TABLE_BILL legado;
PAYMENT_RECEIPT no lugar do recibo final.

A lógica deve ser:

fechar mesa com sucesso
→ gerar/emitir TABLE_FINAL_RECEIPT
→ criar PrintJob conforme rota efetiva
→ PrintManager imprime
2. MOMENTO DA IMPRESSÃO

A emissão deve acontecer depois que a mesa realmente foi fechada com sucesso.

Fluxo esperado:

Mesa aberta
→ pagamentos ok
→ operador fecha mesa
→ backend fecha attendance
→ status closed
→ emite TABLE_FINAL_RECEIPT
→ volta para o grid das mesas

Se a impressão falhar ou a rota estiver desabilitada:

não desfazer o fechamento da mesa;
fechamento continua válido;
impressão é efeito documental separado.
3. LAYOUT ESPERADO DO CUPOM

O cupom deve seguir esse espírito do exemplo:

Cabeçalho
nome da empresa;
nome da filial;
endereço (se houver disponível);
telefone (se houver disponível).
Identificação do documento
data/hora de impressão;
título:
SIMPLES CONFERENCIA DA CONTA não
aqui deve ser algo como:
RECIBO DE FECHAMENTO DA MESA
ou FECHAMENTO DA CONTA
ou RELATÓRIO GERENCIAL DE FECHAMENTO
linha:
RELATÓRIO GERENCIAL
aviso:
*** NÃO É DOCUMENTO FISCAL ***
Dados operacionais
mesa;
atendimento/comanda/conta (se houver identificador);
aberto em;
fechado em;
operador/usuário;
cliente, se houver.
Itens

Listar os itens vendidos.

Formato próximo do exemplo:

ITEM (V.Unit)                   Total
1 X BURGER (39,90)              39,90
  1 COCA ZERO LATA
  OBS: sem cebola

Pode usar formatação melhor alinhada, mas precisa continuar simples para ESC/POS.

Totais
subtotal;
desconto total, se houver;
taxa de serviço, se houver;
total a pagar;
total pago;
troco, se houver.
Pagamentos

Listar as formas de pagamento utilizadas.

Exemplo:

TOTAL PAGO
CARTAO DE DEBITO VISA          39,90
PIX                            20,00
DINHEIRO                       19,90
Rodapé
operador;
mensagem opcional de agradecimento;
talvez site/instagram se já existir configuração;
número/senha/identificador final, se fizer sentido.
4. NÃO COPIAR LITERALMENTE O TEXTO DO EXEMPLO

A imagem é uma referência de estrutura.

Não copiar literalmente dados do estabelecimento da foto.

Não reproduzir:

nome da loja da imagem;
endereço da imagem;
telefone da imagem;
domínio da imagem.

Usar os dados reais do CORE / filial atual.

5. DIFERENÇA ENTRE CONFERÊNCIA E RECIBO FINAL

Deixar a separação bem clara:

Conferência

Antes do fechamento:

CONFERÊNCIA
SEM VALOR FISCAL
Cupom final ao fechar mesa

Depois do fechamento:

RECIBO DE FECHAMENTO / RELATÓRIO GERENCIAL
NÃO É DOCUMENTO FISCAL

Ou seja:

a conferência continua existindo;
o recibo final é outro documento.

Não unificar os dois indevidamente.

6. USAR A ROTA CORRETA

O documento final deve obedecer a rota efetiva de:

TABLE_FINAL_RECEIPT

Respeitar:

PrintRoute da filial;
PrintRouteOverride do POS;
mode;
printer_device_ids;
copies;
document_format.

Não hardcodar impressora.

7. FORMATO DO DOCUMENTO

Se já existe suporte a:

detailed
simplified

em document_format, usar isso também para o recibo final.

Detailed

Mais próximo do exemplo:

itens;
modificadores;
observações;
timestamps;
pagamentos;
operador.
Simplified

Mais enxuto:

cabeçalho;
itens resumidos;
total;
pagamentos;
operador.
8. RENDERER

Revisar o renderer do TABLE_FINAL_RECEIPT.

Se ainda estiver simples demais ou ausente, implementar.

O resultado impresso deve ser visualmente parecido com o modelo:

centralização no cabeçalho;
divisórias com traços;
texto legível;
blocos bem separados;
bom uso de largura 58/80 mm.

Não exagerar em estilos.
Manter compatível com ESC/POS simples.

9. DADOS QUE O DOCUMENTO DEVE TRAZER

No mínimo:

company_name
branch_name
endereço da filial, se disponível
telefone da filial, se disponível
printed_at
opened_at
closed_at
número da mesa
identificador do atendimento
operador
cliente (se houver)
itens
modificadores
observações
subtotal
desconto
taxa de serviço
total
pagamentos
troco (se houver)
10. ITENS E AGRUPAMENTO

Se o documento final hoje usa agrupamento, manter coerência com o restante do projeto.

Se houver itens iguais agrupados, ok.

Mas precisa continuar claro no papel.

Exemplo aceitável:

2 X HEINEKEN LONG NECK (12,00)   24,00

Ou, se não agrupar:

1 X HEINEKEN LONG NECK (12,00)   12,00
1 X HEINEKEN LONG NECK (12,00)   12,00

Escolher o formato que já estiver mais consistente com o projeto.

11. PAGAMENTOS

O cupom final precisa mostrar as formas de pagamento realmente usadas no fechamento.

Exemplo:

PAGAMENTOS
PIX                            50,00
CARTÃO CRÉDITO                 30,00
DINHEIRO                       20,00

Se existir reversão anterior ou múltiplos pagamentos, mostrar apenas o resultado final válido da mesa fechada.

12. NÃO REGREDIR O FECHAMENTO DA MESA

Preservar:

fechar mesa continua funcionando;
volta ao grid das mesas;
grid atualiza;
mesa fica livre;
não reabre mesa por causa de impressão;
não duplica venda;
não duplica baixa de estoque;
não duplica pagamento.

Impressão é apenas documento pós-fechamento.

13. COMPORTAMENTO EM CASO DE ROTA DESABILITADA

Se TABLE_FINAL_RECEIPT estiver desabilitado:

a mesa fecha normalmente;
o sistema pode informar que o recibo final não foi impresso;
não bloquear o fechamento.

A mensagem deve ser operacional e clara.

Exemplo:

Mesa fechada com sucesso.
A impressão do recibo final está desabilitada para esta filial/POS.
14. COMPORTAMENTO EM CASO DE FALHA DE IMPRESSÃO

Se houver FAILED ou UNCERTAIN:

mesa continua fechada;
documento final continua existente;
pode ser reimpresso depois conforme regra atual;
não refazer fechamento;
não recriar pagamento.
15. REIMPRESSÃO

Depois que o recibo final existir/imprimir:

permitir reimpressão pelo fluxo já existente de PrintDocument, se aplicável;
preservar diferença entre:
impressão inicial;
reimpressão.

Não gerar vários “primeiros recibos” duplicados.

16. NÃO ALTERAR O QUE JÁ ESTÁ CERTO

Preservar:

polling de produção;
polling de PrintDocument;
UNCERTAIN;
hash unificado + fallback legado;
Conferência atualizada;
PAYMENT_RECEIPT;
Solicitar Conta → TABLE_CONFERENCE;
fechamento da mesa voltando ao grid;
1.000x → 1x;
retry != reprint;
impressão NETWORK local;
rotas por filial/POS.
17. REFERÊNCIA VISUAL

Usar como referência o exemplo enviado pelo usuário:

cabeçalho centralizado;
linhas separadoras;
aviso de não fiscal;
bloco de itens;
bloco de total;
bloco de pagamentos;
rodapé simples.

Não precisa copiar pixel a pixel.
Precisa apenas ficar no mesmo estilo operacional.

18. CENÁRIO ESPERADO
Mesa com itens
→ registrar pagamentos
→ fechar mesa
→ backend fecha attendance
→ emite TABLE_FINAL_RECEIPT
→ PrintJob criado
→ impressora imprime cupom final
→ POS sai da tela e volta para o grid

Cupom esperado:

simples;
térmico;
gerencial;
com itens e pagamentos;
semelhante ao exemplo.
19. ARQUIVOS A REVISAR

No mínimo, revisar o que for necessário em:

backend/apps/attendance/services.py
backend/apps/sales/services.py
backend/apps/production/services.py
backend/apps/production/serializers.py
backend/apps/pos/views.py

pos/lib/printing/models.dart
pos/lib/printing/print_manager.dart
pos/lib/printing/production_ticket_renderer.dart

e principalmente o renderer/geração do:

TABLE_FINAL_RECEIPT

Se existir arquivo específico para renderização de documentos, revisar também.

20. REGRA CRÍTICA

NÃO EXECUTE TESTES.

NÃO execute:

flutter analyze
flutter test
flutter build
flutter run
pytest
npm test
npm build
npm lint
makemigrations --check

Eu farei os testes manualmente.

CHECKPOINT

Ao terminar informe:

onde passou a emitir o TABLE_FINAL_RECEIPT no fechamento da mesa;
se a mesa continua fechando mesmo quando a impressão falha;
como ficou o layout do recibo final;
quais campos foram incluídos no documento;
como ficou a distinção entre Conferência e recibo final;
como os pagamentos aparecem no cupom;
como ficou o renderer em 58/80 mm;
se preservou reimpressão;
arquivos backend alterados;
arquivos Flutter alterados;
migrations criadas — não deveria precisar;
pontos restantes para teste manual.

NÃO EXECUTE TESTES.

Depois pare.