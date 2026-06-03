import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/providers/portfolio/portfolio_provider.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

class PortfolioScreen extends ConsumerWidget {
  const PortfolioScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final portfoliosAsync = ref.watch(portfoliosProvider);
    final selectedId = ref.watch(selectedPortfolioIdProvider);
    final currency = ref.watch(authProvider).user?.preferredCurrency ?? 'EUR';

    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: const Text('Portefeuille'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () => _showCreateDialog(context, ref),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(portfoliosProvider),
        child: portfoliosAsync.when(
          loading: () => const AppLoading(),
          error: (e, _) => AppErrorWidget(message: e.toString(), onRetry: () => ref.invalidate(portfoliosProvider)),
          data: (portfolios) {
            if (portfolios.isEmpty) {
              return AppEmptyState(
                message: 'Aucun portefeuille',
                description: 'Créez votre premier portefeuille pour commencer',
                icon: Icons.account_balance_wallet_outlined,
                actionLabel: 'Créer un portefeuille',
                onAction: () => _showCreateDialog(context, ref),
              );
            }

            // Select first portfolio if none selected
            if (selectedId == null && portfolios.isNotEmpty) {
              WidgetsBinding.instance.addPostFrameCallback((_) {
                ref.read(selectedPortfolioIdProvider.notifier).state = portfolios.first.id;
              });
            }

            final selected = portfolios.firstWhere(
              (p) => p.id == selectedId,
              orElse: () => portfolios.first,
            );

            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // Portfolio selector
                if (portfolios.length > 1)
                  SizedBox(
                    height: 40,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      children: portfolios.map((p) => Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ChoiceChip(
                          label: Text(p.name),
                          selected: p.id == (selectedId ?? portfolios.first.id),
                          onSelected: (_) => ref.read(selectedPortfolioIdProvider.notifier).state = p.id,
                        ),
                      )).toList(),
                    ),
                  ),
                if (portfolios.length > 1) const SizedBox(height: 12),

                // Portfolio summary
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(selected.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                            if (selected.isDefault) const Chip(label: Text('Principal', style: TextStyle(fontSize: 11))),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          CurrencyFormatter.format(selected.totalValue, currency: currency),
                          style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 4),
                        Row(children: [
                          Icon(
                            selected.totalPnl >= 0 ? Icons.arrow_upward : Icons.arrow_downward,
                            size: 14,
                            color: selected.totalPnl >= 0 ? AppColors.success : AppColors.error,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            '${CurrencyFormatter.format(selected.totalPnl, currency: currency, showSign: true)} (${CurrencyFormatter.formatPercent(selected.totalPnlPercent)})',
                            style: TextStyle(
                              color: selected.totalPnl >= 0 ? AppColors.success : AppColors.error,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ]),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // Assets
                const Text('Actifs', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                _AssetsSection(portfolioId: selected.id, currency: currency),
                const SizedBox(height: 80),
              ],
            );
          },
        ),
      ),
    );
  }

  void _showCreateDialog(BuildContext context, WidgetRef ref) {
    final ctrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Nouveau portefeuille'),
        content: TextField(
          controller: ctrl,
          decoration: const InputDecoration(labelText: 'Nom du portefeuille'),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
          ElevatedButton(
            onPressed: () async {
              if (ctrl.text.trim().isEmpty) return;
              await ref.read(portfolioRepositoryProvider).createPortfolio(ctrl.text.trim());
              ref.invalidate(portfoliosProvider);
              if (ctx.mounted) Navigator.pop(ctx);
            },
            child: const Text('Créer'),
          ),
        ],
      ),
    );
  }
}

class _AssetsSection extends ConsumerWidget {
  final String portfolioId;
  final String currency;
  const _AssetsSection({required this.portfolioId, required this.currency});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assetsAsync = ref.watch(assetsProvider(portfolioId));

    return assetsAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString()),
      data: (assets) {
        if (assets.isEmpty) {
          return const AppEmptyState(
            message: 'Aucun actif',
            description: 'Ajoutez des transactions pour voir vos actifs',
            icon: Icons.pie_chart_outline,
          );
        }
        return Column(
          children: assets.map((asset) => Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: AppColors.primary.withOpacity(0.2),
                child: Text(asset.symbol.substring(0, asset.symbol.length.clamp(0, 3)).toUpperCase(),
                    style: const TextStyle(color: AppColors.primary, fontSize: 11, fontWeight: FontWeight.bold)),
              ),
              title: Text(asset.name),
              subtitle: Text('${asset.quantity} ${asset.symbol}', style: const TextStyle(color: AppColors.textSecondary)),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(CurrencyFormatter.format(asset.currentValue, currency: currency),
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  if (asset.pnlPercent != null)
                    Text(
                      CurrencyFormatter.formatPercent(asset.pnlPercent),
                      style: TextStyle(
                        color: (asset.pnlPercent ?? 0) >= 0 ? AppColors.success : AppColors.error,
                        fontSize: 12,
                      ),
                    ),
                ],
              ),
            ),
          )).toList(),
        );
      },
    );
  }
}
