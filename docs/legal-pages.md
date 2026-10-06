# Páginas jurídicas do site

Rotas: `/termos-de-uso`, `/privacidade`, `/licenca-e-assinatura`, `/tratamento-de-dados`.

Os textos completos foram importados dos quatro documentos da pasta TERMOS, sem reescrita das cláusulas. Os templates versionados ficam em `frontend/src/content/legal`; o manifesto registra SHA-256 das fontes. Campos próprios da contratante permanecem identificados como registrados eletronicamente, sem usar dados institucionais da CORE.

## Configuração

Aplicar a migração `saas.0013_legal_settings` com `python manage.py migrate` no processo normal de implantação. Ela preserva a razão social e o CNPJ antes usados no rodapé, armazenando-os na configuração global existente. Não cria registro global nem inventa contatos.

No Platform Admin, abrir Políticas globais → Dados jurídicos públicos. Preencher razão social, nome fantasia, CNPJ, endereço, cidade/UF, e-mails comercial, jurídico, privacidade, segurança, identificação/e-mail do DPO, site, URL de suboperadores e vigência. O suporte continua usando os campos existentes. As alterações mantêm a proteção administrativa, justificativa e senha já exigidas pelo endpoint.

Esses campos são públicos, não devem conter credenciais. O endpoint `public/settings/` expõe somente a lista permitida de dados jurídicos. PATCH parcial preserva os demais campos; enviar string vazia limpa um campo.

Os quatro documentos e o rodapé leem `legal_settings` dessa API, sem CNPJ ou contatos fixos no frontend. Datas são exibidas em português. Campos sem informação ficam explicitamente sinalizados, nunca substituídos por valores presumidos. Os links do rodapé apontam diretamente para as páginas locais; o link de cookies existente é preservado.

Não foram criadas políticas de cookies, cobrança/cancelamento, SLA ou uma lista de suboperadores: são referenciadas pelos textos, mas não foram fornecidas na pasta TERMOS.

O trabalho cria páginas informativas. Não registra aceite contratual nem publica o site automaticamente.
