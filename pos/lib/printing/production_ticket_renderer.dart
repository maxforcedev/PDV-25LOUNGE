import 'dart:typed_data';

import 'models.dart';

class ProductionTicketRenderer {
  Uint8List render(List<PrintJob> jobs,
      {required int paperWidth, required bool cut}) {
    if (jobs.isEmpty) return Uint8List(0);
    final width = paperWidth == 58 ? 32 : 48;
    final first = jobs.first;
    final payload = first.payload;
    final bytes = BytesBuilder()
      ..add(const [0x1b, 0x40]) // Initialize.
      ..add(const [0x1b, 0x74, 2]); // CP850, with ASCII fallback below.
    if (first.isTest || payload['test'] == true) {
      _center(bytes, 'CORE PDV', width, bold: true, large: true);
      _center(bytes, 'TESTE DE IMPRESSAO', width, bold: true);
      _line(bytes, 'Filial: ${payload['branch'] ?? ''}');
      _line(bytes, 'Impressora: ${payload['printer'] ?? ''}');
      _line(bytes, 'IP: ${payload['host'] ?? ''}');
      _line(bytes, _time(payload));
    } else {
      final cancelled = payload['event'] == 'cancel';
      final reprint = first.reprintNumber > 0 || payload['reprint'] == true;
      _center(bytes, '${payload['branch_name'] ?? 'CORE PDV'}', width,
          bold: true);
      if (cancelled) {
        _center(bytes, '*** CANCELAMENTO ***', width, bold: true, large: true);
      } else if (reprint) {
        _center(bytes, '*** REIMPRESSAO #${first.reprintNumber} ***', width,
            bold: true);
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
        final modifiers = item['modifiers'];
        if (modifiers is List) {
          for (final modifier in modifiers) {
            final label = modifier is Map
                ? (modifier['name'] ??
                        modifier['label'] ??
                        modifier['option_name'] ??
                        '')
                    .toString()
                : modifier.toString();
            if (label.isNotEmpty) _line(bytes, '* $label');
          }
        }
        final notes = '${item['notes'] ?? ''}'.trim();
        if (notes.isNotEmpty) _line(bytes, 'OBS: $notes', bold: true);
      }
      if (cancelled &&
          '${payload['cancellation_reason'] ?? ''}'.trim().isNotEmpty) {
        _line(bytes, 'Motivo: ${payload['cancellation_reason']}', bold: true);
      }
      final operator = '${payload['operator'] ?? ''}'.trim();
      if (operator.isNotEmpty) _line(bytes, 'Atendente: $operator');
    }
    bytes.add(const [0x0a, 0x0a, 0x0a]);
    if (cut) bytes.add(const [0x1d, 0x56, 0x00]);
    return bytes.toBytes();
  }

  String _time(Map<String, dynamic> payload) {
    final instant =
        DateTime.tryParse('${payload['created_at'] ?? ''}')?.toLocal() ??
            DateTime.now();
    String part(int value) => value.toString().padLeft(2, '0');
    return '${part(instant.day)}/${part(instant.month)} ${part(instant.hour)}:${part(instant.minute)}';
  }

  void _center(BytesBuilder bytes, String value, int width,
      {bool bold = false, bool large = false}) {
    bytes.add(const [0x1b, 0x61, 1]);
    _line(bytes, value, bold: bold, large: large);
    bytes.add(const [0x1b, 0x61, 0]);
  }

  void _line(BytesBuilder bytes, String value,
      {bool bold = false, bool large = false}) {
    bytes.add([0x1b, 0x45, bold ? 1 : 0]);
    bytes.add([0x1d, 0x21, large ? 0x11 : 0]);
    bytes.add(_encode(value));
    bytes.addByte(0x0a);
    bytes.add(const [0x1d, 0x21, 0, 0x1b, 0x45, 0]);
  }

  List<int> _encode(String value) {
    // CP850 covers common Portuguese characters; unknown glyphs become ASCII.
    const cp850 = {
      'á': 160,
      'à': 133,
      'â': 131,
      'ã': 198,
      'ä': 132,
      'é': 130,
      'ê': 136,
      'ë': 137,
      'í': 161,
      'ì': 141,
      'î': 140,
      'ó': 162,
      'ò': 149,
      'ô': 147,
      'õ': 228,
      'ö': 148,
      'ú': 163,
      'ù': 151,
      'û': 150,
      'ü': 129,
      'ç': 135,
      'Á': 181,
      'À': 183,
      'Â': 182,
      'Ã': 199,
      'É': 144,
      'Ê': 210,
      'Í': 214,
      'Ó': 224,
      'Ô': 226,
      'Õ': 229,
      'Ú': 233,
      'Ç': 128,
    };
    return value.runes.map((rune) {
      final character = String.fromCharCode(rune);
      if (rune >= 32 && rune <= 126) return rune;
      return cp850[character] ?? 63;
    }).toList(growable: false);
  }
}
