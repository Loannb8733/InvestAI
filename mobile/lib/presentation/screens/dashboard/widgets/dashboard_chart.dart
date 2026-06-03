import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/dashboard/dashboard_provider.dart';

class DashboardChart extends ConsumerWidget {
  final String period;
  final String currency;
  const DashboardChart({super.key, required this.period, required this.currency});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sparklinesAsync = ref.watch(sparklinesProvider(period));

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: SizedBox(
          height: 200,
          child: sparklinesAsync.when(
            loading: () => const Center(child: CircularProgressIndicator(color: AppColors.primary)),
            error: (_, __) => const Center(child: Text('Données indisponibles', style: TextStyle(color: AppColors.textSecondary))),
            data: (points) {
              if (points.isEmpty) {
                return const Center(child: Text('Aucune donnée', style: TextStyle(color: AppColors.textSecondary)));
              }

              final spots = points.asMap().entries.map((e) => FlSpot(e.key.toDouble(), e.value.value)).toList();
              final minY = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
              final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
              final isPositive = points.last.value >= points.first.value;
              final color = isPositive ? AppColors.success : AppColors.error;

              return LineChart(
                LineChartData(
                  gridData: const FlGridData(show: false),
                  titlesData: const FlTitlesData(show: false),
                  borderData: FlBorderData(show: false),
                  minY: minY * 0.99,
                  maxY: maxY * 1.01,
                  lineBarsData: [
                    LineChartBarData(
                      spots: spots,
                      isCurved: true,
                      color: color,
                      barWidth: 2,
                      dotData: const FlDotData(show: false),
                      belowBarData: BarAreaData(
                        show: true,
                        color: color.withOpacity(0.1),
                      ),
                    ),
                  ],
                  lineTouchData: LineTouchData(
                    touchTooltipData: LineTouchTooltipData(
                      getTooltipItems: (spots) => spots.map((spot) {
                        final point = points[spot.spotIndex];
                        return LineTooltipItem(
                          '${DateFormatter.formatShort(point.date)}\n${CurrencyFormatter.format(spot.y, currency: currency)}',
                          const TextStyle(color: Colors.white, fontSize: 12),
                        );
                      }).toList(),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
