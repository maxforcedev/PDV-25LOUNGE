<role>
Execute uma revisão TRANSVERSAL do CORE PDV focada exclusivamente em:

1. ordenação configurável pelo usuário;
2. tratamento e apresentação de erros.

Use o estado atual após o BLOCO 1.
</role>

<block name="ORDERING">

<rule>
Quando "ordem" representar apenas posição visual/configurável, o usuário não deve digitar números como:

0
1
2
3

sort_order continua existindo internamente.

A experiência deve ser:
- drag-and-drop;
- handle visual;
- alternativa acessível para mover para cima/baixo.
</rule>

<audit>
Audite TODO o repositório por:

- sort_order;
- order;
- position;
- sequence;
- campos equivalentes configuráveis pelo usuário.

Classifique cada caso antes de alterar.

NÃO transforme números de negócio em drag-and-drop.
</audit>

<known_cases>
Já identificados:

Category.sort_order
→ já possui reorder;
→ use como referência.

ModifierGroup.sort_order
→ substituir input numérico.

ModifierOption.sort_order
→ substituir input numérico.

ProductModifierGroup.sort_order
→ substituir input numérico.

Confirme se existem outros casos reais.
</known_cases>

<backend>
Quando necessário, crie endpoint/service de reorder que:

- valide RBAC;
- valide Company/Branch;
- rejeite IDs externos;
- rejeite IDs duplicados;
- seja transaction.atomic;
- normalize a sequência;
- audite a alteração.

Evite vários PATCH independentes quando um reorder atômico for possível.
</backend>

<do_not_convert>
Não transformar em drag-and-drop:

- installment_number;
- command_number;
- número de Mesa;
- códigos;
- documentos;
- sequências históricas;
- qualquer número com significado de negócio.
</do_not_convert>

</block>

<block name="ERRORS">

<critical>
NÃO faça replace global de textos.

Corrija a arquitetura de propagação de erros.
</critical>

<audit>
Audite TODO o frontend por:

- ApiError;
- caught.message;
- caught.fields;
- errorMessage;
- setError;
- ErrorBlock;
- "Não foi possível";
- tratamento manual de 400/403/404/409/500.

Localize catches que ignoram erros de fields.
</audit>

<http_client>
Corrija o cliente HTTP central.

Prioridade para mensagem exibida:

1. erro de domínio estruturado;
2. detail/message;
3. non_field_errors;
4. erros de campo;
5. mensagem específica pelo status;
6. fallback contextual.

ApiError.fields deve continuar disponível para o formulário.
</http_client>

<helper>
Crie/reutilize helper central para converter unknown em erro amigável.

Deve:

- reconhecer ApiError;
- extrair melhor mensagem;
- preservar fields;
- considerar code/details;
- aceitar fallback contextual.

Reduza helpers locais duplicados com segurança.
</helper>

<domain_errors>
Condições conhecidas devem retornar mensagens específicas, por exemplo:

produto indisponível;
promoção conflitante;
caixa obrigatório;
feature desabilitada;
estoque negativo proibido;
inventário conflitante;
idempotency conflict;
limite de consumo futuramente.

Não transforme toda ValidationError em DomainValidationError sem necessidade.
</domain_errors>

<server_errors>
HTTP 500 desconhecido:

"Não foi possível concluir a operação devido a um erro interno. Tente novamente."

Nunca exponha:
- traceback;
- SQL;
- secrets;
- exception interna.

Mas erros de negócio conhecidos NÃO devem chegar como 500.
</server_errors>

<promotions>
Garanta que conflito de promoção exiba a mensagem específica retornada pelo backend, inclusive ao ativar/desativar promoção.

Não cair no fallback genérico se a API já informou o conflito.
</promotions>

<platform_admin>
O Platform Admin já possui tratamento razoável de field errors.

Preserve-o.

Não faça refatoração funcional do Platform Admin neste bloco.
</platform_admin>

<validation>
Teste os reorder endpoints alterados.

Valide cenários de erro 400/403/404/409/500.

Execute:
- backend targeted tests;
- frontend lint;
- frontend build;
- git diff --check.
</validation>

<rules>
- Não alterar regras financeiras.
- Não alterar estoque fora do necessário.
- Não implementar novas funcionalidades.
- Não fazer commit.
- Não avançar para o BLOCO 3.
</rules>

<final_response>
Informe:

- todos os campos de ordenação encontrados;
- quais viraram drag-and-drop;
- quais foram preservados e por quê;
- endpoints/services de reorder;
- arquitetura final de erros;
- helpers removidos/criados;
- principais fluxos que deixaram de cair em erro genérico;
- testes/checks;
- riscos restantes.

Finalize:
BLOCO 2 APROVADO
ou
BLOCO 2 NÃO APROVADO.
</final_response>