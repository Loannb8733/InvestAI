import 'package:investai_mobile/core/utils/parse_helpers.dart';

class DashboardSummaryModel {
  final double totalValue;
  final double totalCost;
  final double totalPnl;
  final double totalPnlPercent;
  final double? dailyPnl;
  final double? dailyPnlPercent;
  final int portfolioCount;
  final int assetCount;
  final AdvancedMetrics? advancedMetrics;

  const DashboardSummaryModel({
    required this.totalValue,
    required this.totalCost,
    required this.totalPnl,
    required this.totalPnlPercent,
    this.dailyPnl,
    this.dailyPnlPercent,
    required this.portfolioCount,
    required this.assetCount,
    this.advancedMetrics,
  });

  factory DashboardSummaryModel.fromJson(Map<String, dynamic> json) {
    return DashboardSummaryModel(
      totalValue: parseDoubleOrZero(json['total_value']),
      totalCost: parseDoubleOrZero(json['total_cost']),
      totalPnl: parseDoubleOrZero(json['total_pnl']),
      totalPnlPercent: parseDoubleOrZero(json['total_pnl_percent']),
      dailyPnl: parseDouble(json['daily_pnl']),
      dailyPnlPercent: parseDouble(json['daily_pnl_percent']),
      portfolioCount: json['portfolio_count'] as int? ?? 0,
      assetCount: json['asset_count'] as int? ?? 0,
      advancedMetrics: json['advanced_metrics'] != null
          ? AdvancedMetrics.fromJson(json['advanced_metrics'] as Map<String, dynamic>)
          : null,
    );
  }
}

class AdvancedMetrics {
  final double? roiAnnualized;
  final double? volatility;
  final double? sharpeRatio;
  final double? maxDrawdown;
  final double? beta;

  const AdvancedMetrics({
    this.roiAnnualized,
    this.volatility,
    this.sharpeRatio,
    this.maxDrawdown,
    this.beta,
  });

  factory AdvancedMetrics.fromJson(Map<String, dynamic> json) {
    return AdvancedMetrics(
      roiAnnualized: parseDouble(json['roi_annualized']),
      volatility: parseDouble(json['volatility']),
      sharpeRatio: parseDouble(json['sharpe_ratio']),
      maxDrawdown: parseDouble(json['max_drawdown']),
      beta: parseDouble(json['beta']),
    );
  }
}

class ChartPoint {
  final DateTime date;
  final double value;

  const ChartPoint({required this.date, required this.value});

  factory ChartPoint.fromJson(Map<String, dynamic> json) {
    return ChartPoint(
      date: DateTime.tryParse(json['date'] as String? ?? '') ?? DateTime.now(),
      value: parseDoubleOrZero(json['value']),
    );
  }
}
