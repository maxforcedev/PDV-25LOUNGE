import 'package:flutter/material.dart';
import 'dart:async';
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
        title: 'CORE PDV',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xff3454d1),
            primary: const Color(0xff3454d1),
            surface: const Color(0xffffffff),
          ),
          scaffoldBackgroundColor: const Color(0xfff0f2f8),
          textTheme: ThemeData.light().textTheme.apply(
                bodyColor: const Color(0xff283c50),
                displayColor: const Color(0xff283c50),
              ),
          inputDecorationTheme: InputDecorationTheme(
            filled: true,
            fillColor: const Color(0xffffffff),
            contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: Color(0xffe2e8f0)),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: Color(0xffe2e8f0)),
            ),
          ),
          filledButtonTheme: FilledButtonThemeData(
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xff3454d1),
              foregroundColor: Colors.white,
              minimumSize: const Size.fromHeight(54),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              textStyle: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
          useMaterial3: true,
        ),
        home: AppShell(controller: controller),
      );
}
