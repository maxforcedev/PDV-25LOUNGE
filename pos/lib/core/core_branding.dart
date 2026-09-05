import 'package:flutter/material.dart';

class CoreSymbol extends StatelessWidget {
  const CoreSymbol({super.key, this.size = 112});

  final double size;

  @override
  Widget build(BuildContext context) => Image.asset(
        'assets/branding/core-logo.png',
        width: size,
        height: size,
        fit: BoxFit.contain,
        semanticLabel: 'CORE PDV',
      );
}

class CoreWordmark extends StatelessWidget {
  const CoreWordmark({super.key, this.width = 190});

  final double width;

  @override
  Widget build(BuildContext context) => Image.asset(
        'assets/branding/core-pdv-wordmark.png',
        width: width,
        fit: BoxFit.contain,
        semanticLabel: 'CORE PDV',
      );
}
