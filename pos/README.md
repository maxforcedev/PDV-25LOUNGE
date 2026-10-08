# CORE POS

Cliente Android Flutter para o fluxo POS-1: pareamento do device, autenticacao do operador por PIN e bootstrap autenticado.

## Desenvolvimento

```text
flutter pub get
flutter test
flutter run --dart-define=POS_API_BASE_URL=http://10.0.2.2:18000
```

`POS_API_BASE_URL` e obrigatorio em todo build e deve apontar para a API publica do ambiente. Nao ha endpoint padrao no aplicativo: isso evita distribuir builds de producao apontando para localhost ou para o emulador.

```text
flutter build apk --release --dart-define=POS_API_BASE_URL=https://api.seudominio.com
```

Use HTTPS fora do build debug. Tambem sao aceitos `POS_APP_VERSION`, `POS_DEVICE_NAME` e `POS_DEVICE_TYPE` via `--dart-define`.

Os secrets sao guardados somente por `flutter_secure_storage`. O PIN nunca e persistido.
