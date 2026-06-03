import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _crowdfundingProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.crowdfunding);
  return r.data as List<dynamic>;
});

class CrowdfundingScreen extends ConsumerWidget {
  const CrowdfundingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectsAsync = ref.watch(_crowdfundingProvider);

    return Scaffold(
      appBar: AppBar(leading: const DrawerMenuButton(), title: const Text('Crowdfunding')),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_crowdfundingProvider),
        child: projectsAsync.when(
          loading: () => const AppLoading(),
          error: (_, __) => const AppEmptyState(message: 'Erreur de chargement', icon: Icons.business_outlined),
          data: (projects) {
            if (projects.isEmpty) {
              return const AppEmptyState(
                message: 'Aucun projet',
                description: 'Suivez vos investissements en crowdfunding',
                icon: Icons.business_outlined,
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: projects.length,
              itemBuilder: (_, i) {
                final project = projects[i] as Map<String, dynamic>;
                final funded = (project['amount_raised'] as num?)?.toDouble() ?? 0;
                final target = (project['target_amount'] as num?)?.toDouble() ?? 1;
                final progress = (funded / target).clamp(0.0, 1.0);
                final status = project['status'] as String? ?? 'active';
                final statusColor = status == 'active' ? AppColors.success : status == 'completed' ? AppColors.info : AppColors.textMuted;
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(child: Text(project['name'] as String? ?? '', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16))),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(color: statusColor.withOpacity(0.2), borderRadius: BorderRadius.circular(8)),
                              child: Text(status, style: TextStyle(color: statusColor, fontSize: 11)),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (project['platform'] != null) Text(project['platform'] as String, style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                        const SizedBox(height: 8),
                        LinearProgressIndicator(value: progress, backgroundColor: AppColors.cardDark, color: AppColors.primary),
                        const SizedBox(height: 4),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(CurrencyFormatter.format(funded), style: const TextStyle(fontWeight: FontWeight.w600)),
                            Text('${(progress * 100).toStringAsFixed(0)}% · objectif ${CurrencyFormatter.format(target)}', style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
