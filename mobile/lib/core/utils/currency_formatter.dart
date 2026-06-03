import 'package:intl/intl.dart';

class CurrencyFormatter {
  static String format(
    double? value, {
    String currency = 'EUR',
    bool showSign = false,
    bool compact = false,
  }) {
    if (value == null) return '—';

    if (compact && value.abs() >= 1000000) {
      final m = value / 1000000;
      return '${showSign && value > 0 ? '+' : ''}${m.toStringAsFixed(2)}M ${_symbol(currency)}';
    }
    if (compact && value.abs() >= 1000) {
      final k = value / 1000;
      return '${showSign && value > 0 ? '+' : ''}${k.toStringAsFixed(1)}k ${_symbol(currency)}';
    }

    final formatter = NumberFormat.currency(
      locale: 'fr_FR',
      symbol: _symbol(currency),
      decimalDigits: 2,
    );

    final formatted = formatter.format(value);
    if (showSign && value > 0) return '+$formatted';
    return formatted;
  }

  static String formatPercent(double? value, {bool showSign = true}) {
    if (value == null) return '—';
    final sign = showSign && value > 0 ? '+' : '';
    return '$sign${value.toStringAsFixed(2)}%';
  }

  static String _symbol(String currency) {
    const symbols = {'EUR': '€', 'USD': '\$', 'CHF': 'CHF', 'GBP': '£'};
    return symbols[currency] ?? currency;
  }
}
