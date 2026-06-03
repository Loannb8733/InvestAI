import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _analyticsProvider = FutureProvider.family<Map<String, dynamic>, String>((ref, period) async {
  final dio = ref.watch(dioProvider);
  final response = await dio.get(ApiConstants.analyticsPerformance, queryParameters: {'period_days': _periodToDays(period)});
  return response.data as Map<String, dynamic>;
});

final _diversificationProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final response = await dio.get(ApiConstants.analyticsDiversification);
  return response.data as Map<String, dynamic>;
});

final _riskProvider = FutureProvider.family<Map<String, dynamic>, String>((ref, period) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.analyticsRisk, queryParameters: {'period_days': _periodToDays(period)});
  return r.data as Map<String, dynamic>;
});

int _periodToDays(String period) {
  const map = {'1W': 7, '1M': 30, '3M': 90, '6M': 180, '1Y': 365, 'ALL': 3650};
  return map[period] ?? 30;
}

class AnalyticsScreen extends ConsumerStatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  ConsumerState<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends ConsumerState<AnalyticsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;
  String _period = '1M';

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: const Text('Analytics'),
        bottom: TabBar(
          controller: _tabCtrl,
          tabs: const [
            Tab(text: 'Performance'),
            Tab(text: 'Diversification'),
            Tab(text: 'Risque'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabCtrl,
        children: [
          _PerformanceTab(period: _period, onPeriodChanged: (p) => setState(() => _period = p)),
          _DiversificationTab(),
          _RiskTab(period: _period),
        ],
      ),
    );
  }
}

class _PerformanceTab extends ConsumerWidget {
  final String period;
  final ValueChanged<String> onPeriodChanged;
  static const _periods = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];
  const _PerformanceTab({required this.period, required this.onPeriodChanged});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(_analyticsProvider(period));
    return dataAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString(), onRetry: () => ref.invalidate(_analyticsProvider(period))),
      data: (data) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SizedBox(
            height: 36,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: _periods.map((p) => Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(label: Text(p), selected: period == p, onSelected: (_) => onPeriodChanged(p)),
              )).toList(),
            ),
          ),
          const SizedBox(height: 16),
          _InfoCard(label: 'Rendement total', value: CurrencyFormatter.formatPercent((data['total_return'] as num?)?.toDouble())),
          const SizedBox(height: 8),
          _InfoCard(label: 'Rendement annualisé', value: CurrencyFormatter.formatPercent((data['annualized_return'] as num?)?.toDouble())),
          const SizedBox(height: 8),
          _InfoCard(label: 'Volatilité', value: '${((data['volatility'] as num?)?.toDouble() ?? 0).toStringAsFixed(1)}%'),
          const SizedBox(height: 8),
          _InfoCard(label: 'Sharpe', value: ((data['sharpe_ratio'] as num?)?.toDouble() ?? 0).toStringAsFixed(2)),
        ],
      ),
    );
  }
}

class _DiversificationTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(_diversificationProvider);
    return dataAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString()),
      data: (data) {
        final byType = (data['by_asset_type'] as Map<String, dynamic>?) ?? {};
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Répartition par type', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            ...byType.entries.map((e) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(e.key),
                      Text('${(e.value as num).toStringAsFixed(1)}%', style: const TextStyle(fontWeight: FontWeight.w600)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  LinearProgressIndicator(
                    value: (e.value as num).toDouble() / 100,
                    backgroundColor: AppColors.cardDark,
                    color: AppColors.primary,
                  ),
                ],
              ),
            )),
          ],
        );
      },
    );
  }
}

class _RiskTab extends ConsumerWidget {
  final String period;
  const _RiskTab({required this.period});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(_riskProvider(period));

    return dataAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString()),
      data: (data) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _InfoCard(label: 'Max Drawdown', value: '-${((data['max_drawdown']?['max_drawdown_percent'] as num?)?.toDouble() ?? 0).toStringAsFixed(1)}%', valueColor: AppColors.error),
          const SizedBox(height: 8),
          _InfoCard(label: 'VaR 95%', value: '-${((data['var_95']?['var_percent'] as num?)?.toDouble() ?? 0).toStringAsFixed(1)}%', valueColor: AppColors.warning),
          const SizedBox(height: 8),
          _InfoCard(label: 'Beta', value: ((data['beta'] as num?)?.toDouble() ?? 1.0).toStringAsFixed(2)),
        ],
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;
  const _InfoCard({required this.label, required this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(label, style: const TextStyle(color: AppColors.textSecondary)),
        trailing: Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: valueColor)),
      ),
    );
  }
}
