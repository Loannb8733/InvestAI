import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _alertsProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.alerts);
  return r.data as List<dynamic>;
});

class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alertsAsync = ref.watch(_alertsProvider);

    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: const Text('Alertes'),
        actions: [
          IconButton(icon: const Icon(Icons.add), onPressed: () => _showCreateDialog(context, ref)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_alertsProvider),
        child: alertsAsync.when(
          loading: () => const AppLoading(),
          error: (e, _) => AppErrorWidget(message: e.toString(), onRetry: () => ref.invalidate(_alertsProvider)),
          data: (alerts) {
            if (alerts.isEmpty) {
              return AppEmptyState(
                message: 'Aucune alerte',
                description: 'Créez des alertes de prix pour être notifié',
                icon: Icons.notifications_outlined,
                actionLabel: 'Créer une alerte',
                onAction: () => _showCreateDialog(context, ref),
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: alerts.length,
              itemBuilder: (_, i) {
                final alert = alerts[i] as Map<String, dynamic>;
                final isActive = alert['is_active'] as bool? ?? true;
                final isTriggered = alert['is_triggered'] as bool? ?? false;
                final condition = alert['condition'] as String? ?? 'above';
                final threshold = (alert['threshold'] as num?)?.toDouble() ?? 0;

                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: Icon(
                      isTriggered ? Icons.notifications_active : Icons.notifications_outlined,
                      color: isTriggered ? AppColors.warning : isActive ? AppColors.primary : AppColors.textMuted,
                    ),
                    title: Text(alert['asset_symbol'] as String? ?? '—'),
                    subtitle: Text(
                      '${condition == 'above' ? 'Au-dessus de' : 'En-dessous de'} ${CurrencyFormatter.format(threshold)}',
                    ),
                    trailing: Switch(
                      value: isActive,
                      onChanged: (v) async {
                        await ref.read(dioProvider).patch('${ApiConstants.alerts}/${alert['id']}', data: {'is_active': v});
                        ref.invalidate(_alertsProvider);
                      },
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

  void _showCreateDialog(BuildContext context, WidgetRef ref) {
    final symbolCtrl = TextEditingController();
    final thresholdCtrl = TextEditingController();
    String condition = 'above';

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Nouvelle alerte'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: symbolCtrl, decoration: const InputDecoration(labelText: 'Symbole (ex: BTC)')),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: condition,
                items: const [
                  DropdownMenuItem(value: 'above', child: Text('Au-dessus de')),
                  DropdownMenuItem(value: 'below', child: Text('En-dessous de')),
                ],
                onChanged: (v) => setState(() => condition = v ?? 'above'),
              ),
              const SizedBox(height: 12),
              TextField(controller: thresholdCtrl, decoration: const InputDecoration(labelText: 'Seuil'), keyboardType: const TextInputType.numberWithOptions(decimal: true)),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
            ElevatedButton(
              onPressed: () async {
                await ref.read(dioProvider).post(ApiConstants.alerts, data: {
                  'asset_symbol': symbolCtrl.text.trim().toUpperCase(),
                  'alert_type': 'price',
                  'condition': condition,
                  'threshold': double.tryParse(thresholdCtrl.text) ?? 0,
                });
                ref.invalidate(_alertsProvider);
                if (ctx.mounted) Navigator.pop(ctx);
              },
              child: const Text('Créer'),
            ),
          ],
        ),
      ),
    );
  }
}
