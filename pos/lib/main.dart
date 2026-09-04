import 'package:flutter/material.dart';

import 'core/app_config.dart';
import 'core/app_controller.dart';
import 'core/app_shell.dart';
import 'network/pos_api.dart';
import 'storage/secret_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final config = AppConfig.fromEnvironment();
  final secrets = FlutterSecretStore();
  final controller = AppController(
    api: HttpPosApi(baseUrl: config.apiBaseUrl, secrets: secrets),
    secrets: secrets,
    device: config.device,
  );
  runApp(CorePosApp(controller: controller));
  unawaited(controller.initialize());
}

class CorePosApp extends StatelessWidget {
  const CorePosApp({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'CORE POS',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff6e3025)),
          useMaterial3: true,
        ),
        home: AppShell(controller: controller),
      );
}
