import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

class SimulationsScreen extends ConsumerStatefulWidget {
  const SimulationsScreen({super.key});

  @override
  ConsumerState<SimulationsScreen> createState() => _SimulationsScreenState();
}

class _SimulationsScreenState extends ConsumerState<SimulationsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
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
        title: const Text('Simulations'),
        bottom: TabBar(
          controller: _tabCtrl,
          tabs: const [Tab(text: 'FIRE'), Tab(text: 'DCA')],
        ),
      ),
      body: TabBarView(
        controller: _tabCtrl,
        children: [_FIRETab(), _DCATab()],
      ),
    );
  }
}

class _FIRETab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_FIRETab> createState() => _FIRETabState();
}

class _FIRETabState extends ConsumerState<_FIRETab> {
  final _monthlyCtrl = TextEditingController(text: '2000');
  final _expensesCtrl = TextEditingController(text: '3000');
  final _returnCtrl = TextEditingController(text: '7');
  Map<String, dynamic>? _result;
  bool _isLoading = false;

  Future<void> _simulate() async {
    setState(() => _isLoading = true);
    try {
      final r = await ref.read(dioProvider).post(ApiConstants.simulationFIRE, data: {
        'monthly_savings': double.tryParse(_monthlyCtrl.text) ?? 2000,
        'monthly_expenses': double.tryParse(_expensesCtrl.text) ?? 3000,
        'expected_return': (double.tryParse(_returnCtrl.text) ?? 7) / 100,
      });
      setState(() => _result = r.data as Map<String, dynamic>);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()), backgroundColor: AppColors.error));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text('Calculez votre chemin vers l\'indépendance financière', style: TextStyle(color: AppColors.textSecondary)),
        const SizedBox(height: 16),
        TextField(controller: _monthlyCtrl, decoration: const InputDecoration(labelText: 'Épargne mensuelle (€)'), keyboardType: TextInputType.number),
        const SizedBox(height: 12),
        TextField(controller: _expensesCtrl, decoration: const InputDecoration(labelText: 'Dépenses mensuelles (€)'), keyboardType: TextInputType.number),
        const SizedBox(height: 12),
        TextField(controller: _returnCtrl, decoration: const InputDecoration(labelText: 'Rendement annuel attendu (%)'), keyboardType: const TextInputType.numberWithOptions(decimal: true)),
        const SizedBox(height: 16),
        ElevatedButton(
          onPressed: _isLoading ? null : _simulate,
          child: _isLoading ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('Simuler'),
        ),
        if (_result != null) ...[
          const SizedBox(height: 24),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  const Text('Résultats FIRE', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  _ResultRow(label: 'Capital FIRE nécessaire', value: CurrencyFormatter.format((_result!['fire_number'] as num?)?.toDouble())),
                  _ResultRow(label: 'Années jusqu\'au FIRE', value: '${((_result!['years_to_fire'] as num?)?.toInt() ?? '—')} ans'),
                  _ResultRow(label: 'Taux de retrait sûr', value: '4%'),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _DCATab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_DCATab> createState() => _DCATabState();
}

class _DCATabState extends ConsumerState<_DCATab> {
  final _symbolCtrl = TextEditingController(text: 'BTC');
  final _amountCtrl = TextEditingController(text: '100');
  final _monthsCtrl = TextEditingController(text: '12');
  Map<String, dynamic>? _result;
  bool _isLoading = false;

  Future<void> _simulate() async {
    setState(() => _isLoading = true);
    try {
      final r = await ref.read(dioProvider).post(ApiConstants.simulationDCA, data: {
        'symbol': _symbolCtrl.text.trim().toUpperCase(),
        'monthly_amount': double.tryParse(_amountCtrl.text) ?? 100,
        'duration_months': int.tryParse(_monthsCtrl.text) ?? 12,
      });
      setState(() => _result = r.data as Map<String, dynamic>);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()), backgroundColor: AppColors.error));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text('Simulez un investissement régulier (Dollar Cost Averaging)', style: TextStyle(color: AppColors.textSecondary)),
        const SizedBox(height: 16),
        TextField(controller: _symbolCtrl, decoration: const InputDecoration(labelText: 'Symbole (ex: BTC, ETH)'), textCapitalization: TextCapitalization.characters),
        const SizedBox(height: 12),
        TextField(controller: _amountCtrl, decoration: const InputDecoration(labelText: 'Montant mensuel (€)'), keyboardType: TextInputType.number),
        const SizedBox(height: 12),
        TextField(controller: _monthsCtrl, decoration: const InputDecoration(labelText: 'Durée (mois)'), keyboardType: TextInputType.number),
        const SizedBox(height: 16),
        ElevatedButton(
          onPressed: _isLoading ? null : _simulate,
          child: _isLoading ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('Simuler'),
        ),
        if (_result != null) ...[
          const SizedBox(height: 24),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  const Text('Résultats DCA', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  _ResultRow(label: 'Montant investi', value: CurrencyFormatter.format((_result!['total_invested'] as num?)?.toDouble())),
                  _ResultRow(label: 'Valeur finale', value: CurrencyFormatter.format((_result!['final_value'] as num?)?.toDouble())),
                  _ResultRow(label: 'ROI', value: CurrencyFormatter.formatPercent((_result!['roi_percent'] as num?)?.toDouble())),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _ResultRow extends StatelessWidget {
  final String label;
  final String value;
  const _ResultRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppColors.textSecondary)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
