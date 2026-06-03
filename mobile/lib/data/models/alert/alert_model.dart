import 'package:investai_mobile/core/utils/parse_helpers.dart';

class AlertModel {
  final String id;
  final String? assetId;
  final String? assetSymbol;
  final String alertType;
  final double threshold;
  final String condition;
  final bool isActive;
  final bool isTriggered;
  final DateTime? triggeredAt;
  final DateTime createdAt;

  const AlertModel({
    required this.id,
    this.assetId,
    this.assetSymbol,
    required this.alertType,
    required this.threshold,
    required this.condition,
    required this.isActive,
    required this.isTriggered,
    this.triggeredAt,
    required this.createdAt,
  });

  factory AlertModel.fromJson(Map<String, dynamic> json) {
    return AlertModel(
      id: json['id'] as String,
      assetId: json['asset_id'] as String?,
      assetSymbol: json['asset_symbol'] as String?,
      alertType: json['alert_type'] as String? ?? 'price',
      threshold: parseDoubleOrZero(json['threshold']),
      condition: json['condition'] as String? ?? 'above',
      isActive: json['is_active'] as bool? ?? true,
      isTriggered: json['is_triggered'] as bool? ?? false,
      triggeredAt: DateTime.tryParse(json['triggered_at'] as String? ?? ''),
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}
