import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/providers/dashboard/dashboard_provider.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/screens/dashboard/widgets/dashboard_chart.dart';
import 'package:investai_mobile/presentation/screens/dashboard/widgets/metrics_grid.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  String _period = '1M';
  static const _periods = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider).user;
    final dashboardAsync = ref.watch(dashboardProvider(_period));
    final currency = user?.preferredCurrency ?? 'EUR';

    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Dashboard', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            if (user?.displayName != null)
              Text('Bonjour, ${user!.displayName}', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined),
            onPressed: () {},
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(dashboardProvider(_period)),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(dashboardProvider(_period)),
        child: dashboardAsync.when(
          loading: () => const AppLoading(),
          error: (e, _) => AppErrorWidget(
            message: e.toString(),
            onRetry: () => ref.invalidate(dashboardProvider(_period)),
          ),
          data: (summary) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Total value card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Valeur totale', style: TextStyle(color: AppColors.textSecondary, fontSize: 14)),
                      const SizedBox(height: 4),
                      Text(
                        CurrencyFormatter.format(summary.totalValue, currency: currency),
                        style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Icon(
                            summary.totalPnl >= 0 ? Icons.arrow_upward : Icons.arrow_downward,
                            size: 16,
                            color: summary.totalPnl >= 0 ? AppColors.success : AppColors.error,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            '${CurrencyFormatter.format(summary.totalPnl, currency: currency, showSign: true)} (${CurrencyFormatter.formatPercent(summary.totalPnlPercent)})',
                            style: TextStyle(
                              color: summary.totalPnl >= 0 ? AppColors.success : AppColors.error,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                      if (summary.dailyPnl != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          'Aujourd\'hui: ${CurrencyFormatter.format(summary.dailyPnl, currency: currency, showSign: true)} (${CurrencyFormatter.formatPercent(summary.dailyPnlPercent)})',
                          style: TextStyle(
                            color: (summary.dailyPnl ?? 0) >= 0 ? AppColors.success : AppColors.error,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),

              // Period selector
              SizedBox(
                height: 36,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  children: _periods.map((p) => Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(p),
                      selected: _period == p,
                      onSelected: (_) => setState(() => _period = p),
                    ),
                  )).toList(),
                ),
              ),
              const SizedBox(height: 12),

              // Chart
              DashboardChart(period: _period, currency: currency),
              const SizedBox(height: 12),

              // Metrics
              if (summary.advancedMetrics != null)
                MetricsGrid(metrics: summary.advancedMetrics!, currency: currency),
              const SizedBox(height: 12),

              // Stats
              Row(children: [
                Expanded(child: _StatCard(label: 'Portefeuilles', value: '${summary.portfolioCount}')),
                const SizedBox(width: 12),
                Expanded(child: _StatCard(label: 'Actifs', value: '${summary.assetCount}')),
                const SizedBox(width: 12),
                Expanded(child: _StatCard(label: 'Coût total', value: CurrencyFormatter.format(summary.totalCost, currency: currency, compact: true))),
              ]),
              const SizedBox(height: 80),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  const _StatCard({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(label, style: const TextStyle(color: AppColors.textSecondary, fontSize: 12), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
