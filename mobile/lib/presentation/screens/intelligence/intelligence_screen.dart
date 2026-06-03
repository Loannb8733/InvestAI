import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _insightsProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.insights);
  return r.data as List<dynamic>;
});

final _predictionsProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.predictions);
  return r.data as List<dynamic>;
});

final _anomaliesProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.anomalies);
  return r.data as List<dynamic>;
});

class IntelligenceScreen extends ConsumerStatefulWidget {
  const IntelligenceScreen({super.key});

  @override
  ConsumerState<IntelligenceScreen> createState() => _IntelligenceScreenState();
}

class _IntelligenceScreenState extends ConsumerState<IntelligenceScreen> with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;

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
        title: const Text('Intelligence IA'),
        bottom: TabBar(
          controller: _tabCtrl,
          tabs: const [Tab(text: 'Insights'), Tab(text: 'Prédictions'), Tab(text: 'Anomalies')],
        ),
      ),
      body: TabBarView(
        controller: _tabCtrl,
        children: [
          _InsightsTab(),
          _PredictionsTab(),
          _AnomaliesTab(),
        ],
      ),
    );
  }
}

class _InsightsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final insightsAsync = ref.watch(_insightsProvider);
    return insightsAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString(), onRetry: () => ref.invalidate(_insightsProvider)),
      data: (insights) {
        if (insights.isEmpty) return const Center(child: Text('Aucun insight disponible', style: TextStyle(color: AppColors.textSecondary)));
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: insights.length,
          itemBuilder: (_, i) {
            final insight = insights[i] as Map<String, dynamic>;
            final severity = insight['severity'] as String? ?? 'info';
            final color = severity == 'high' ? AppColors.error : severity == 'medium' ? AppColors.warning : AppColors.info;
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: ListTile(
                leading: Icon(Icons.lightbulb_outline, color: color),
                title: Text(insight['title'] as String? ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(insight['message'] as String? ?? ''),
                    if (insight['created_at'] != null)
                      Text(DateFormatter.formatRelative(DateTime.tryParse(insight['created_at'] as String) ?? DateTime.now()),
                          style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}

class _PredictionsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final predsAsync = ref.watch(_predictionsProvider);
    return predsAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString()),
      data: (preds) {
        if (preds.isEmpty) return const Center(child: Text('Aucune prédiction disponible', style: TextStyle(color: AppColors.textSecondary)));
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: preds.length,
          itemBuilder: (_, i) {
            final pred = preds[i] as Map<String, dynamic>;
            final change = (pred['predicted_change_percent'] as num?)?.toDouble() ?? 0;
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: ListTile(
                title: Text(pred['symbol'] as String? ?? ''),
                subtitle: Text('Horizon: ${pred['horizon_days']} jours'),
                trailing: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '${change >= 0 ? '+' : ''}${change.toStringAsFixed(1)}%',
                      style: TextStyle(color: change >= 0 ? AppColors.success : AppColors.error, fontWeight: FontWeight.bold, fontSize: 16),
                    ),
                    Text('Conf: ${((pred['confidence'] as num?)?.toDouble() ?? 0 * 100).toStringAsFixed(0)}%',
                        style: const TextStyle(color: AppColors.textSecondary, fontSize: 11)),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}

class _AnomaliesTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final anomaliesAsync = ref.watch(_anomaliesProvider);
    return anomaliesAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString()),
      data: (anomalies) {
        if (anomalies.isEmpty) return const Center(child: Text('Aucune anomalie détectée', style: TextStyle(color: AppColors.success)));
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: anomalies.length,
          itemBuilder: (_, i) {
            final a = anomalies[i] as Map<String, dynamic>;
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: ListTile(
                leading: const Icon(Icons.warning_amber_rounded, color: AppColors.warning),
                title: Text(a['asset_symbol'] as String? ?? ''),
                subtitle: Text(a['description'] as String? ?? ''),
              ),
            );
          },
        );
      },
    );
  }
}
