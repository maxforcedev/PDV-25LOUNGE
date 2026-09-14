import 'package:flutter/material.dart';

import 'sale_models.dart';

class SharedAuthorizationDialog extends StatefulWidget {
  const SharedAuthorizationDialog({
    required this.authorizers,
    required this.onAuthorize,
    super.key,
  });

  final List<QuickSaleAuthorizer> authorizers;
  final Future<String?> Function(QuickSaleAuthorization authorization)
      onAuthorize;

  @override
  State<SharedAuthorizationDialog> createState() =>
      _SharedAuthorizationDialogState();
}

class _SharedAuthorizationDialogState extends State<SharedAuthorizationDialog> {
  final _pin = TextEditingController();
  int? _authorizerId;
  bool _validating = false;
  String? _error;

  Future<void> _authorize() async {
    if (_authorizerId == null || _pin.text.length != 6 || _validating) return;
    setState(() {
      _validating = true;
      _error = null;
    });
    final authorization = QuickSaleAuthorization(
      userId: _authorizerId!,
      credential: _pin.text,
    );
    String? error;
    try {
      error = await widget.onAuthorize(authorization);
    } finally {
      _pin.clear();
    }
    if (!mounted) return;
    if (error == null) {
      Navigator.of(context).pop(authorization);
      return;
    }
    setState(() {
      _validating = false;
      _error = error;
    });
  }

  @override
  void dispose() {
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('AUTORIZAÇÃO NECESSÁRIA'),
        content: SizedBox(
          width: 360,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButtonFormField<int>(
              initialValue: _authorizerId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Autorizador'),
              items: widget.authorizers
                  .map((authorizer) => DropdownMenuItem(
                        value: authorizer.id,
                        child: Text(authorizer.displayName,
                            overflow: TextOverflow.ellipsis),
                      ))
                  .toList(growable: false),
              onChanged: (value) => setState(() {
                _authorizerId = value;
                _pin.clear();
                _error = null;
              }),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pin,
              autofocus: true,
              obscureText: true,
              keyboardType: TextInputType.number,
              maxLength: 6,
              enableSuggestions: false,
              autocorrect: false,
              onChanged: (value) {
                if (!RegExp(r'^\d{0,6}$').hasMatch(value)) _pin.clear();
                setState(() {});
              },
              decoration: InputDecoration(
                  labelText: 'PIN do autorizador', errorText: _error),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: _validating ? null : () => Navigator.of(context).pop(),
            child: const Text('VOLTAR'),
          ),
          FilledButton(
            onPressed:
                _authorizerId == null || _pin.text.length != 6 || _validating
                    ? null
                    : _authorize,
            child: Text(_validating ? 'VALIDANDO...' : 'AUTORIZAR'),
          ),
        ],
      );
}
