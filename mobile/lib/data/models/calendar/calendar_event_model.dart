import 'package:investai_mobile/core/utils/parse_helpers.dart';

class CalendarEventModel {
  final String id;
  final String title;
  final String? description;
  final String eventType;
  final DateTime eventDate;
  final double? amount;
  final String? currency;
  final String? assetSymbol;
  final bool isRecurring;
  final DateTime createdAt;

  const CalendarEventModel({
    required this.id,
    required this.title,
    this.description,
    required this.eventType,
    required this.eventDate,
    this.amount,
    this.currency,
    this.assetSymbol,
    required this.isRecurring,
    required this.createdAt,
  });

  factory CalendarEventModel.fromJson(Map<String, dynamic> json) {
    return CalendarEventModel(
      id: json['id'] as String,
      title: json['title'] as String? ?? '',
      description: json['description'] as String?,
      eventType: json['event_type'] as String? ?? 'other',
      eventDate: DateTime.tryParse(json['event_date'] as String? ?? '') ?? DateTime.now(),
      amount: parseDouble(json['amount']),
      currency: json['currency'] as String?,
      assetSymbol: json['asset_symbol'] as String?,
      isRecurring: json['is_recurring'] as bool? ?? false,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }

  String get typeLabel {
    const labels = {
      'dividend': 'Dividende',
      'rent': 'Loyer',
      'interest': 'Intérêts',
      'tax': 'Impôt',
      'earning': 'Résultats',
      'ipo': 'IPO',
      'maturity': 'Échéance',
      'other': 'Autre',
    };
    return labels[eventType] ?? eventType;
  }
}
