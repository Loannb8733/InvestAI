import 'package:flutter/material.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/data/models/dashboard/dashboard_summary_model.dart';

class MetricsGrid extends StatelessWidget {
  final AdvancedMetrics metrics;
  final String currency;
  const MetricsGrid({super.key, required this.metrics, required this.currency});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Métriques avancées', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: _MetricCard(
            label: 'ROI annualisé',
            value: metrics.roiAnnualized != null ? CurrencyFormatter.formatPercent(metrics.roiAnnualized) : '—',
            color: metrics.roiAnnualized != null && metrics.roiAnnualized! > 0 ? AppColors.success : AppColors.error,
          )),
          const SizedBox(width: 8),
          Expanded(child: _MetricCard(
            label: 'Volatilité',
            value: metrics.volatility != null ? '${metrics.volatility!.toStringAsFixed(1)}%' : '—',
          )),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: _MetricCard(
            label: 'Sharpe',
            value: metrics.sharpeRatio != null ? metrics.sharpeRatio!.toStringAsFixed(2) : '—',
            color: metrics.sharpeRatio != null
                ? metrics.sharpeRatio! >= 1 ? AppColors.success : metrics.sharpeRatio! >= 0 ? AppColors.warning : AppColors.error
                : null,
          )),
          const SizedBox(width: 8),
          Expanded(child: _MetricCard(
            label: 'Max Drawdown',
            value: metrics.maxDrawdown != null ? '-${metrics.maxDrawdown!.toStringAsFixed(1)}%' : '—',
            color: AppColors.error,
          )),
        ]),
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  const _MetricCard({required this.label, required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
            const SizedBox(height: 4),
            Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: color)),
          ],
        ),
      ),
    );
  }
}
