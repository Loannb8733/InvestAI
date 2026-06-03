import 'package:investai_mobile/core/utils/parse_helpers.dart';

class AssetModel {
  final String id;
  final String portfolioId;
  final String symbol;
  final String name;
  final String assetType;
  final double quantity;
  final double? currentPrice;
  final double? averageBuyPrice;
  final double currentValue;
  final double? pnl;
  final double? pnlPercent;
  final double? allocation;
  final String? currency;
  final DateTime? lastUpdated;

  const AssetModel({
    required this.id,
    required this.portfolioId,
    required this.symbol,
    required this.name,
    required this.assetType,
    required this.quantity,
    this.currentPrice,
    this.averageBuyPrice,
    required this.currentValue,
    this.pnl,
    this.pnlPercent,
    this.allocation,
    this.currency,
    this.lastUpdated,
  });

  factory AssetModel.fromJson(Map<String, dynamic> json) {
    return AssetModel(
      id: json['id'] as String,
      portfolioId: json['portfolio_id'] as String? ?? '',
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      assetType: json['asset_type'] as String? ?? 'other',
      quantity: parseDoubleOrZero(json['quantity']),
      currentPrice: parseDouble(json['current_price']),
      averageBuyPrice: parseDouble(json['average_buy_price']),
      currentValue: parseDoubleOrZero(json['current_value']),
      pnl: parseDouble(json['pnl']),
      pnlPercent: parseDouble(json['pnl_percent']),
      allocation: parseDouble(json['allocation']),
      currency: json['currency'] as String?,
      lastUpdated: DateTime.tryParse(json['last_updated'] as String? ?? ''),
    );
  }
}
