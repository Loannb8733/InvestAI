import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _plannedOrdersProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.plannedOrders);
  return r.data as List<dynamic>;
});

class StrategyScreen extends ConsumerWidget {
  const StrategyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersAsync = ref.watch(_plannedOrdersProvider);

    return Scaffold(
      appBar: AppBar(leading: const DrawerMenuButton(), title: const Text('Stratégie')),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_plannedOrdersProvider),
        child: ordersAsync.when(
          loading: () => const AppLoading(),
          error: (_, __) => const AppEmptyState(message: 'Erreur de chargement', icon: Icons.account_tree_outlined),
          data: (orders) {
            if (orders.isEmpty) {
              return const AppEmptyState(
                message: 'Aucun ordre planifié',
                description: 'Planifiez vos prochains achats et ventes',
                icon: Icons.account_tree_outlined,
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: orders.length,
              itemBuilder: (_, i) {
                final order = orders[i] as Map<String, dynamic>;
                final isBuy = (order['order_type'] as String?) == 'buy';
                final targetDate = DateTime.tryParse(order['target_date'] as String? ?? '');
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: Icon(isBuy ? Icons.arrow_downward : Icons.arrow_upward, color: isBuy ? AppColors.success : AppColors.error),
                    title: Text('${isBuy ? "Achat" : "Vente"} ${order['asset_symbol']}'),
                    subtitle: targetDate != null ? Text('Cible: ${DateFormatter.formatDate(targetDate)}') : null,
                    trailing: Text(CurrencyFormatter.format((order['target_amount'] as num?)?.toDouble()), style: const TextStyle(fontWeight: FontWeight.w600)),
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
