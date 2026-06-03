import 'package:investai_mobile/core/utils/parse_helpers.dart';

class PortfolioModel {
  final String id;
  final String name;
  final String? description;
  final double totalValue;
  final double totalCost;
  final double totalPnl;
  final double totalPnlPercent;
  final bool isDefault;
  final DateTime createdAt;

  const PortfolioModel({
    required this.id,
    required this.name,
    this.description,
    required this.totalValue,
    required this.totalCost,
    required this.totalPnl,
    required this.totalPnlPercent,
    required this.isDefault,
    required this.createdAt,
  });

  factory PortfolioModel.fromJson(Map<String, dynamic> json) {
    return PortfolioModel(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      totalValue: parseDoubleOrZero(json['total_value']),
      totalCost: parseDoubleOrZero(json['total_cost']),
      totalPnl: parseDoubleOrZero(json['total_pnl']),
      totalPnlPercent: parseDoubleOrZero(json['total_pnl_percent']),
      isDefault: json['is_default'] as bool? ?? false,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}
