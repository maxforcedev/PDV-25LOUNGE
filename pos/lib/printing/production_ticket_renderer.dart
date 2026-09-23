import 'dart:typed_data';

import 'models.dart';

/// Renders both production and document jobs. Physical dispatch remains owned
/// by PrintManager; a document is never sent directly from a UI action.
class ProductionTicketRenderer {
  int _printableWidth = 42;
  int _leftMargin = 3;

  Uint8List render(List<PrintJob> jobs,
      {required int paperWidth, required bool cut}) {
    if (jobs.isEmpty) return Uint8List(0);
    final width = paperWidth == 58 ? 28 : 42;
    _printableWidth = width;
    // Safe content is inset from both physical paper edges (32/48 columns).
    _leftMargin = paperWidth == 58 ? 2 : 3;
    final bytes = BytesBuilder()
      ..add(const [0x1b, 0x40])
      ..add(const [0x1b, 0x74, 2]);
    final first = jobs.first;
    if (first.isTest || first.payload['test'] == true) {
      _renderTest(bytes, first.payload, width, paperWidth);
    } else if (first.documentType != null) {
      _renderDocument(bytes, jobs, width);
    } else {
      _renderProduction(bytes, jobs, width);
    }
    // Feed before cutting so the final printed line is not lost at the blade.
    bytes.add(const [0x0a, 0x0a, 0x0a, 0x0a]);
    if (cut) bytes.add(const [0x1d, 0x56, 0x00]);
    return bytes.toBytes();
  }

  void _renderTest(BytesBuilder bytes, Map<String, dynamic> payload, int width,
      int paperWidth) {
    _center(bytes, 'CORE PDV', width, bold: true, large: true);
    _center(bytes, 'TESTE DE IMPRESSAO', width, bold: true);
    _line(bytes, 'Impressora: ${payload['printer'] ?? ''}');
    _line(bytes, 'IP: ${payload['host'] ?? ''}');
    _line(bytes, 'Papel: ${paperWidth == 58 ? '58mm' : '80mm'}');
    _line(bytes, _time(payload));
    _line(bytes, '-' * width);
  }

  void _renderProduction(BytesBuilder bytes, List<PrintJob> jobs, int width) {
    final first = jobs.first;
    final payload = first.payload;
    final cancelled = payload['event'] == 'cancel';
    final reprint = first.reprintNumber > 0 || payload['reprint'] == true;
    _centerIfPresent(bytes, '${payload['branch_name'] ?? ''}', width,
        bold: true);
    if (cancelled) {
      _center(bytes, '*** CANCELAMENTO ***', width, bold: true, large: true);
    } else if (reprint) {
      _reprintBanner(bytes, first.reprintNumber, width);
    }
    _center(bytes,
        '${(payload['destination'] as Map?)?['name'] ?? 'PRODUCAO'}', width,
        bold: true, large: true);
    _line(bytes, '-' * width);
    final table = payload['table'] as Map?;
    final sale = payload['sale'] as Map?;
    if (table != null && '${table['name'] ?? ''}'.isNotEmpty) {
      _line(bytes, 'MESA ${table['name']}');
    }
    if (sale != null && '${sale['identifier'] ?? ''}'.isNotEmpty) {
      _line(bytes, '${sale['identifier']}');
    }
    _line(bytes, _time(payload));
    for (final job in jobs) {
      final item = job.payload['source_item'] as Map? ?? const {};
      _line(bytes, '${item['quantity'] ?? ''}x ${item['product_name'] ?? ''}',
          bold: true, large: true);
      _itemDetails(bytes, item, width);
    }
    if (cancelled && '${payload['cancellation_reason'] ?? ''}'.trim().isNotEmpty) {
      _line(bytes, 'Motivo: ${payload['cancellation_reason']}', bold: true);
    }
    _lineIfPresent(bytes, 'Atendente', payload['operator'], width);
  }

  void _renderDocument(BytesBuilder bytes, List<PrintJob> jobs, int width) {
    final job = jobs.first;
    final payload = job.payload;
    final snapshot = _snapshot(payload);
    final type = job.documentType!;
    final detailed = _documentFormat(payload) != 'simplified';
    _centerIfPresent(bytes, _first(snapshot, ['company_name', 'branch_name', 'branch']),
        width, bold: true);
    if (job.reprintNumber > 0 || payload['reprint'] == true) {
      _reprintBanner(bytes, job.reprintNumber, width);
    }
    switch (type) {
      case PrintDocumentType.tableBill:
        _center(bytes, 'CONTA', width, bold: true, large: true);
        _tableDocument(bytes, snapshot, width,
            fiscalLabel: null, detailed: detailed);
        break;
      case PrintDocumentType.tableConference:
        _center(bytes, 'CONFERENCIA', width, bold: true, large: true);
        _tableDocument(bytes, snapshot, width,
            fiscalLabel: 'SEM VALOR FISCAL', detailed: detailed);
        break;
      case PrintDocumentType.tableFinalReceipt:
      case PrintDocumentType.quickSaleReceipt:
        _center(bytes, 'RECIBO NAO FISCAL', width, bold: true);
        _receiptDocument(bytes, snapshot, width, detailed: detailed);
        break;
      case PrintDocumentType.paymentReceipt:
        _center(bytes, 'COMPROVANTE DE PAGAMENTO', width, bold: true);
        _paymentDocument(bytes, snapshot, width);
        break;
      case PrintDocumentType.ticket:
        _ticketDocument(bytes, snapshot, width);
        break;
    }
  }

  void _tableDocument(BytesBuilder bytes, Map<String, dynamic> snapshot,
      int width, {required String? fiscalLabel, required bool detailed}) {
    if (fiscalLabel != null) _center(bytes, fiscalLabel, width, bold: true);
    _centerIfPresent(bytes, _tableLabel(snapshot), width, bold: true, large: true);
    _commonDocumentHeader(bytes, snapshot, width, attendant: true);
    _documentItems(bytes, snapshot, width, detailed: detailed);
    _financials(bytes, snapshot, width);
    _lineIfPresent(bytes, 'Cliente', _first(snapshot, ['customer_name', 'customer']), width);
  }

  void _receiptDocument(BytesBuilder bytes, Map<String, dynamic> snapshot,
      int width, {required bool detailed}) {
    _lineIfPresent(bytes, 'Venda', _saleNumber(snapshot), width);
    final table = _tableLabel(snapshot);
    if (table.isNotEmpty) _line(bytes, table);
    _commonDocumentHeader(bytes, snapshot, width, attendant: true);
    _documentItems(bytes, snapshot, width, detailed: detailed);
    _financials(bytes, snapshot, width);
    _payments(bytes, snapshot, width);
    _lineIfPresent(bytes, 'Operador',
        _first(snapshot, ['operator', 'seller', 'operator_name']), width);
    _lineIfPresent(bytes, 'Cliente',
        _first(snapshot, ['customer', 'customer_name']), width);
  }

  void _paymentDocument(BytesBuilder bytes, Map<String, dynamic> snapshot, int width) {
    final nestedPayment = _map(snapshot['payment']);
    final payment = nestedPayment.isEmpty ? snapshot : nestedPayment;
    _centerIfPresent(bytes, _tableLabel(snapshot), width, bold: true);
    _lineIfPresent(bytes, 'Pagamento', _first(payment, ['payment_id', 'number', 'id']), width);
    _lineIfPresent(bytes, 'Forma', _first(payment, ['payment_method_name', 'method_name', 'method']), width);
    _lineIfPresent(bytes, 'Valor', _first(payment, ['amount']), width);
    _lineIfPresent(bytes, 'Recebido', _first(payment, ['received_amount']), width);
    _lineIfPresent(bytes, 'Troco', _first(payment, ['change_amount']), width);
    _lineIfPresent(bytes, 'Data/hora', _first(payment, ['created_at', 'paid_at']), width);
    _lineIfPresent(bytes, 'Operador',
        _first(snapshot, ['operator', 'attendant', 'operator_name']), width);
  }

  void _ticketDocument(BytesBuilder bytes, Map<String, dynamic> snapshot, int width) {
    final nestedTicket = _map(snapshot['ticket']);
    final ticket = nestedTicket.isEmpty ? snapshot : nestedTicket;
    final item = _map(ticket['item']);
    final number = _first(ticket, ['number', 'ticket_number']);
    _center(bytes, number == null ? 'TICKET' : 'TICKET #$number', width,
        bold: true, large: true);
    _lineIfPresent(bytes, 'Produto',
        _first(ticket, ['product_name', 'product']) ?? _first(item, ['product_name', 'name', 'product']), width);
    _lineIfPresent(bytes, 'Quantidade',
        _first(ticket, ['quantity']) ?? _first(item, ['quantity']), width);
    _lineIfPresent(bytes, 'Codigo', _first(ticket, ['validation_code', 'code']), width);
    _lineIfPresent(bytes, 'Data/hora', _first(ticket, ['issued_at', 'created_at']), width);
  }

  void _commonDocumentHeader(
      BytesBuilder bytes, Map<String, dynamic> snapshot, int width,
      {bool attendant = false}) {
    _lineIfPresent(bytes, 'Data/hora',
        _first(snapshot, ['opened_at', 'created_at', 'issued_at']), width);
    if (attendant) {
      _lineIfPresent(bytes, 'Atendente',
          _first(snapshot, ['attendant', 'operator', 'seller']), width);
    }
  }

  void _documentItems(BytesBuilder bytes, Map<String, dynamic> snapshot,
      int width, {required bool detailed}) {
    final items = snapshot['items'];
    if (items is! List || items.isEmpty) return;
    _line(bytes, '-' * width);
    for (final raw in items) {
      final item = _map(raw);
      final name = _first(item, ['product_name', 'name']);
      if (name == null) continue;
      final quantity = _first(item, ['quantity']) ?? '';
      final financial = _map(item['financial']);
      _columns(bytes, '$quantity${quantity.isEmpty ? '' : 'x '} $name',
          _first(item, ['line_total', 'net_subtotal', 'subtotal', 'total']) ??
              _first(financial, ['net_subtotal', 'subtotal']),
          width,
          bold: true);
      if (detailed) {
        _lineIfPresent(bytes, 'Unit.', _first(item, ['unit_price']), width);
        _itemDetails(bytes, item, width);
      }
    }
  }

  void _itemDetails(BytesBuilder bytes, Map item, int width) {
    final modifiers = item['modifiers'] ?? item['modifier_snapshot'];
    if (modifiers is List) {
      for (final modifier in modifiers) {
        final values = _map(modifier);
        final label = _first(values, ['name', 'label', 'option_name']) ?? '${modifier ?? ''}';
        if (label.trim().isNotEmpty) _line(bytes, '* $label');
      }
    }
    final notes = '${item['notes'] ?? ''}'.trim();
    if (notes.isNotEmpty) _line(bytes, 'OBS: $notes', bold: true);
  }

  void _financials(BytesBuilder bytes, Map<String, dynamic> snapshot, int width) {
    final financials = {
      ...snapshot,
      ..._map(snapshot['financials']),
      ..._map(snapshot['summary']),
    };
    const labels = {
      'subtotal': 'Subtotal',
      'promotion_discount_total': 'Promocoes',
      'item_discount_total': 'Desconto por item',
      'discount': 'Desconto',
      'checkout_discount_total': 'Desconto',
      'discount_total': 'Desconto',
      'service_fee_total': 'Taxa de servico',
      'service_fee_amount': 'Taxa de servico',
      'service_fee': 'Taxa de servico',
      'total_due': 'TOTAL',
      'total': 'TOTAL',
    };
    final rows = <MapEntry<String, String>>[];
    for (final entry in labels.entries) {
      final value = financials[entry.key];
      if (value != null && '$value'.trim().isNotEmpty) {
        if (!rows.any((row) => row.value == entry.value)) {
          rows.add(MapEntry(entry.value, '$value'));
        }
      }
    }
    if (rows.isEmpty) return;
    _line(bytes, '-' * width);
    for (final row in rows) {
      _columns(bytes, row.key, row.value, width, bold: row.key == 'TOTAL');
    }
  }

  void _payments(BytesBuilder bytes, Map<String, dynamic> snapshot, int width) {
    final payments = snapshot['payments'];
    if (payments is! List || payments.isEmpty) return;
    _line(bytes, '-' * width);
    _center(bytes, 'PAGAMENTOS', width, bold: true);
    for (final raw in payments) {
      final payment = _map(raw);
      final method = _first(payment, ['payment_method_name', 'method_name', 'method']);
      if (method == null) continue;
      _columns(bytes, method, _first(payment, ['amount']), width);
      _lineIfPresent(bytes, 'Recebido', _first(payment, ['received_amount']), width);
      _lineIfPresent(bytes, 'Troco', _first(payment, ['change_amount']), width);
    }
  }

  Map<String, dynamic> _snapshot(Map<String, dynamic> payload) {
    final document = _map(payload['document']);
    final snapshot = _map(document['snapshot']);
    if (snapshot.isNotEmpty) return snapshot;
    final printDocument = _map(payload['print_document']);
    final printDocumentSnapshot = _map(printDocument['snapshot']);
    if (printDocumentSnapshot.isNotEmpty) return printDocumentSnapshot;
    final payloadSnapshot = _map(payload['snapshot']);
    return payloadSnapshot.isNotEmpty ? payloadSnapshot : payload;
  }

  String _documentFormat(Map<String, dynamic> payload) {
    final document = _map(payload['document']);
    final printDocument = _map(payload['print_document']);
    return '${document['format'] ?? document['document_format'] ?? printDocument['format'] ?? payload['document_format'] ?? ''}'
        .trim()
        .toLowerCase();
  }

  Map<String, dynamic> _map(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : const {};

  String? _first(Map values, List<String> keys) {
    for (final key in keys) {
      final value = values[key];
      if (value != null && '$value'.trim().isNotEmpty) return '$value';
    }
    return null;
  }

  String _tableLabel(Map<String, dynamic> snapshot) {
    final table = _map(snapshot['table']);
    final name = _first(table, ['name']) ?? _first(snapshot, ['table_name']);
    return name == null ? '' : 'MESA $name';
  }

  String? _saleNumber(Map<String, dynamic> snapshot) {
    final sale = _map(snapshot['sale']);
    final value = _first(sale, ['number', 'sale_number', 'identifier']) ??
        _first(snapshot, ['sale_number', 'number']);
    return value == null ? null : '#$value';
  }

  String _time(Map<String, dynamic> payload) {
    final instant = DateTime.tryParse('${payload['created_at'] ?? ''}')?.toLocal() ?? DateTime.now();
    String part(int value) => value.toString().padLeft(2, '0');
    return '${part(instant.day)}/${part(instant.month)} ${part(instant.hour)}:${part(instant.minute)}';
  }

  void _reprintBanner(BytesBuilder bytes, int number, int width) =>
      _center(bytes, number > 0 ? '*** REIMPRESSAO #$number ***' : '*** REIMPRESSAO ***', width, bold: true);

  void _centerIfPresent(BytesBuilder bytes, String? value, int width,
      {bool bold = false, bool large = false}) {
    if (value != null && value.trim().isNotEmpty) {
      _center(bytes, value, width, bold: bold, large: large);
    }
  }

  void _lineIfPresent(BytesBuilder bytes, String label, String? value, int width) {
    if (value != null && value.trim().isNotEmpty) _line(bytes, '$label: $value');
  }

  void _center(BytesBuilder bytes, String value, int width,
      {bool bold = false, bool large = false}) {
    final lineWidth = large ? width ~/ 2 : width;
    for (final line in _wrap(value, lineWidth)) {
      final padding =
          ((lineWidth - line.length) ~/ 2).clamp(0, lineWidth).toInt();
      _line(bytes, '${' ' * padding}$line', bold: bold, large: large);
    }
  }

  void _columns(BytesBuilder bytes, String left, String? right, int width,
      {bool bold = false}) {
    if (right == null || right.isEmpty) {
      _line(bytes, left, bold: bold);
      return;
    }
    final rightText = right.length > width ? right.substring(0, width) : right;
    final leftWidth = width - rightText.length - 1;
    if (leftWidth < 1) {
      _line(bytes, left, bold: bold);
      _line(bytes, rightText, bold: bold);
      return;
    }
    final wrapped = _wrap(left, leftWidth);
    for (var index = 0; index < wrapped.length - 1; index++) {
      _line(bytes, wrapped[index], bold: bold);
    }
    final finalLeft = wrapped.isEmpty ? '' : wrapped.last;
    _line(bytes, '$finalLeft${' ' * (width - finalLeft.length - rightText.length)}$rightText', bold: bold);
  }

  void _line(BytesBuilder bytes, String value,
      {bool bold = false, bool large = false}) {
    final width = large ? _printableWidth ~/ 2 : _printableWidth;
    for (final line in _wrap(value, width)) {
      bytes.add([0x1b, 0x45, bold ? 1 : 0]);
      bytes.add([0x1d, 0x21, large ? 0x11 : 0]);
      final margin = large ? _leftMargin ~/ 2 : _leftMargin;
      bytes.add(_encode('${' ' * margin}$line'));
      bytes.addByte(0x0a);
      bytes.add(const [0x1d, 0x21, 0, 0x1b, 0x45, 0]);
    }
  }

  List<String> _wrap(String value, int width) {
    if (value.isEmpty) return const [''];
    final result = <String>[];
    for (final paragraph in value.replaceAll('\r', '').split('\n')) {
      var remaining = paragraph.trimRight();
      while (remaining.length > width) {
        var split = remaining.lastIndexOf(' ', width);
        if (split <= 0) split = width;
        result.add(remaining.substring(0, split).trimRight());
        remaining = remaining.substring(split).trimLeft();
      }
      result.add(remaining);
    }
    return result;
  }

  List<int> _encode(String value) {
    const cp850 = {
      'á': 160, 'à': 133, 'â': 131, 'ã': 198, 'ä': 132, 'é': 130,
      'ê': 136, 'ë': 137, 'í': 161, 'ì': 141, 'î': 140, 'ó': 162,
      'ò': 149, 'ô': 147, 'õ': 228, 'ö': 148, 'ú': 163, 'ù': 151,
      'û': 150, 'ü': 129, 'ç': 135, 'Á': 181, 'À': 183, 'Â': 182,
      'Ã': 199, 'É': 144, 'Ê': 210, 'Í': 214, 'Ó': 224, 'Ô': 226,
      'Õ': 229, 'Ú': 233, 'Ç': 128,
    };
    return value.runes.map((rune) {
      final character = String.fromCharCode(rune);
      if (rune >= 32 && rune <= 126) return rune;
      return cp850[character] ?? 63;
    }).toList(growable: false);
  }
}
