import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/data/models/dashboard/dashboard_summary_model.dart';
import 'package:investai_mobile/data/repositories/dashboard_repository.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';

final dashboardRepositoryProvider = Provider<DashboardRepository>((ref) {
  return DashboardRepository(ref.watch(dioProvider));
});

final dashboardProvider = FutureProvider.family<DashboardSummaryModel, String>(
  (ref, period) async {
    return ref.watch(dashboardRepositoryProvider).getDashboard(period: period);
  },
);

final sparklinesProvider = FutureProvider.family<List<ChartPoint>, String>(
  (ref, period) async {
    return ref.watch(dashboardRepositoryProvider).getSparklines(period: period);
  },
);
