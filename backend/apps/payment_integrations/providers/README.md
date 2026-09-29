# Payment Provider Adapters

Adapters convert a provider protocol into `ProviderPaymentResult`; domain services
then pass that result to `resolve_payment_attempt()`. Cielo Smart builds a `lio://`
Deep Link command for a future client launcher. The URI embeds credentials in Base64
and must never be logged, audited, persisted, or included in a repr.
