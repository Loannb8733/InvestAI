import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:investai_mobile/core/router/route_names.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/transaction/transaction_provider.dart';
import 'package:investai_mobile/providers/portfolio/portfolio_provider.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

class TransactionsScreen extends ConsumerStatefulWidget {
  const TransactionsScreen({super.key});

  @override
  ConsumerState<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends ConsumerState<TransactionsScreen> {
  String? _selectedPortfolioId;
  String? _filterType;

  static const _types = ['buy', 'sell', 'deposit', 'withdrawal', 'dividend'];
  static const _typeLabels = {
    'buy': 'Achat', 'sell': 'Vente', 'deposit': 'Dépôt',
    'withdrawal': 'Retrait', 'dividend': 'Dividende',
  };

  @override
  Widget build(BuildContext context) {
    final txAsync = ref.watch(transactionsProvider);
    final notifier = ref.read(transactionsProvider.notifier);
    final portfoliosAsync = ref.watch(portfoliosProvider);
    final currency = ref.watch(authProvider).user?.preferredCurrency ?? 'EUR';

    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: const Text('Transactions'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () => context.push(RouteNames.transactionForm),
          ),
        ],
      ),
      body: Column(
        children: [
          // Filters
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(children: [
              // Portfolio filter
              Expanded(
                child: portfoliosAsync.when(
                  data: (portfolios) => DropdownButtonFormField<String?>(
                    value: _selectedPortfolioId,
                    decoration: const InputDecoration(labelText: 'Portefeuille', isDense: true, contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8)),
                    items: [
                      const DropdownMenuItem(value: null, child: Text('Tous')),
                      ...portfolios.map((p) => DropdownMenuItem(value: p.id, child: Text(p.name))),
                    ],
                    onChanged: (v) {
                      setState(() => _selectedPortfolioId = v);
                      notifier.load(portfolioId: v, reset: true);
                    },
                  ),
                  loading: () => const SizedBox.shrink(),
                  error: (_, __) => const SizedBox.shrink(),
                ),
              ),
              const SizedBox(width: 8),
              // Type filter
              DropdownButton<String?>(
                value: _filterType,
                hint: const Text('Type'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Tous')),
                  ..._types.map((t) => DropdownMenuItem(value: t, child: Text(_typeLabels[t] ?? t))),
                ],
                onChanged: (v) => setState(() => _filterType = v),
              ),
            ]),
          ),

          // Transaction list
          Expanded(
            child: txAsync.when(
              loading: () => const AppLoading(),
              error: (e, _) => AppErrorWidget(message: e.toString()),
              data: (transactions) {
                final filtered = _filterType == null
                    ? transactions
                    : transactions.where((t) => t.transactionType == _filterType).toList();

                if (filtered.isEmpty) {
                  return AppEmptyState(
                    message: 'Aucune transaction',
                    icon: Icons.swap_horiz_outlined,
                    actionLabel: 'Ajouter une transaction',
                    onAction: () => context.push(RouteNames.transactionForm),
                  );
                }

                return ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: filtered.length + (notifier.hasMore ? 1 : 0),
                  itemBuilder: (ctx, i) {
                    if (i == filtered.length) {
                      return Padding(
                        padding: const EdgeInsets.all(16),
                        child: ElevatedButton(
                          onPressed: notifier.loadMore,
                          child: const Text('Charger plus'),
                        ),
                      );
                    }
                    final tx = filtered[i];
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        leading: CircleAvatar(
                          backgroundColor: tx.isBuy ? AppColors.success.withOpacity(0.2) : AppColors.error.withOpacity(0.2),
                          child: Icon(
                            tx.isBuy ? Icons.arrow_downward : Icons.arrow_upward,
                            color: tx.isBuy ? AppColors.success : AppColors.error,
                            size: 20,
                          ),
                        ),
                        title: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(tx.assetSymbol, style: const TextStyle(fontWeight: FontWeight.w600)),
                            Text(
                              CurrencyFormatter.format(tx.totalAmount, currency: currency),
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ],
                        ),
                        subtitle: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('${tx.typeLabel} · ${tx.quantity} @ ${CurrencyFormatter.format(tx.price, currency: currency)}'),
                            Text(DateFormatter.formatDate(tx.transactionDate), style: const TextStyle(color: AppColors.textMuted)),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
