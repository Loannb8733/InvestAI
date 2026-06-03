import 'package:intl/intl.dart';

class DateFormatter {
  static final _dateFormat = DateFormat('dd/MM/yyyy', 'fr_FR');
  static final _dateTimeFormat = DateFormat('dd/MM/yyyy HH:mm', 'fr_FR');
  static final _shortFormat = DateFormat('dd MMM', 'fr_FR');
  static final _monthYearFormat = DateFormat('MMM yyyy', 'fr_FR');

  static String formatDate(DateTime? date) {
    if (date == null) return '—';
    return _dateFormat.format(date);
  }

  static String formatDateTime(DateTime? date) {
    if (date == null) return '—';
    return _dateTimeFormat.format(date);
  }

  static String formatShort(DateTime? date) {
    if (date == null) return '—';
    return _shortFormat.format(date);
  }

  static String formatMonthYear(DateTime? date) {
    if (date == null) return '—';
    return _monthYearFormat.format(date);
  }

  static String formatRelative(DateTime date) {
    final now = DateTime.now();
    final diff = now.difference(date);

    if (diff.inSeconds < 60) return "À l'instant";
    if (diff.inMinutes < 60) return '${diff.inMinutes}min';
    if (diff.inHours < 24) return '${diff.inHours}h';
    if (diff.inDays < 7) return '${diff.inDays}j';
    if (diff.inDays < 30) return '${(diff.inDays / 7).floor()}sem';
    if (diff.inDays < 365) return '${(diff.inDays / 30).floor()}mois';
    return '${(diff.inDays / 365).floor()}an';
  }

  static DateTime? parseIso(String? str) {
    if (str == null) return null;
    return DateTime.tryParse(str)?.toLocal();
  }
}
