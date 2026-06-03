import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/validators.dart';
import 'package:investai_mobile/providers/transaction/transaction_provider.dart';
import 'package:investai_mobile/providers/portfolio/portfolio_provider.dart';

class TransactionFormScreen extends ConsumerStatefulWidget {
  const TransactionFormScreen({super.key});

  @override
  ConsumerState<TransactionFormScreen> createState() => _TransactionFormScreenState();
}

class _TransactionFormScreenState extends ConsumerState<TransactionFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _symbolCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _quantityCtrl = TextEditingController();
  final _priceCtrl = TextEditingController();
  final _feeCtrl = TextEditingController(text: '0');
  final _notesCtrl = TextEditingController();

  String _type = 'buy';
  String? _portfolioId;
  String _currency = 'EUR';
  DateTime _date = DateTime.now();
  bool _isLoading = false;

  static const _types = ['buy', 'sell', 'deposit', 'withdrawal', 'dividend'];
  static const _typeLabels = {'buy': 'Achat', 'sell': 'Vente', 'deposit': 'Dépôt', 'withdrawal': 'Retrait', 'dividend': 'Dividende'};

  @override
  void dispose() {
    _symbolCtrl.dispose();
    _nameCtrl.dispose();
    _quantityCtrl.dispose();
    _priceCtrl.dispose();
    _feeCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_portfolioId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sélectionnez un portefeuille'), backgroundColor: AppColors.error));
      return;
    }

    setState(() => _isLoading = true);
    try {
      await ref.read(transactionRepositoryProvider).createTransaction({
        'portfolio_id': _portfolioId,
        'asset_symbol': _symbolCtrl.text.trim().toUpperCase(),
        'asset_name': _nameCtrl.text.trim(),
        'transaction_type': _type,
        'quantity': double.parse(_quantityCtrl.text.replaceAll(',', '.')),
        'price': double.parse(_priceCtrl.text.replaceAll(',', '.')),
        'fee': double.tryParse(_feeCtrl.text.replaceAll(',', '.')) ?? 0,
        'currency': _currency,
        'transaction_date': _date.toIso8601String(),
        if (_notesCtrl.text.trim().isNotEmpty) 'notes': _notesCtrl.text.trim(),
      });
      ref.read(transactionsProvider.notifier).load(reset: true);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()), backgroundColor: AppColors.error));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final portfoliosAsync = ref.watch(portfoliosProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Nouvelle transaction')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Portfolio
              portfoliosAsync.when(
                data: (portfolios) {
                  if (_portfolioId == null && portfolios.isNotEmpty) {
                    _portfolioId = portfolios.first.id;
                  }
                  return DropdownButtonFormField<String>(
                    value: _portfolioId,
                    decoration: const InputDecoration(labelText: 'Portefeuille'),
                    items: portfolios.map((p) => DropdownMenuItem(value: p.id, child: Text(p.name))).toList(),
                    onChanged: (v) => setState(() => _portfolioId = v),
                    validator: (v) => v == null ? 'Requis' : null,
                  );
                },
                loading: () => const CircularProgressIndicator(),
                error: (_, __) => const SizedBox.shrink(),
              ),
              const SizedBox(height: 16),

              // Type
              DropdownButtonFormField<String>(
                value: _type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: _types.map((t) => DropdownMenuItem(value: t, child: Text(_typeLabels[t] ?? t))).toList(),
                onChanged: (v) => setState(() => _type = v ?? 'buy'),
              ),
              const SizedBox(height: 16),

              // Symbol & Name
              Row(children: [
                Expanded(
                  flex: 2,
                  child: TextFormField(
                    controller: _symbolCtrl,
                    decoration: const InputDecoration(labelText: 'Symbole (ex: BTC)'),
                    textCapitalization: TextCapitalization.characters,
                    validator: (v) => Validators.required(v, 'Symbole'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  flex: 3,
                  child: TextFormField(
                    controller: _nameCtrl,
                    decoration: const InputDecoration(labelText: 'Nom'),
                    validator: (v) => Validators.required(v, 'Nom'),
                  ),
                ),
              ]),
              const SizedBox(height: 16),

              // Quantity & Price
              Row(children: [
                Expanded(child: TextFormField(
                  controller: _quantityCtrl,
                  decoration: const InputDecoration(labelText: 'Quantité'),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  validator: Validators.positiveNumber,
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _priceCtrl,
                  decoration: const InputDecoration(labelText: 'Prix unitaire'),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  validator: Validators.positiveNumber,
                )),
              ]),
              const SizedBox(height: 16),

              // Fee & Currency
              Row(children: [
                Expanded(child: TextFormField(
                  controller: _feeCtrl,
                  decoration: const InputDecoration(labelText: 'Frais'),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
                const SizedBox(width: 12),
                Expanded(child: DropdownButtonFormField<String>(
                  value: _currency,
                  decoration: const InputDecoration(labelText: 'Devise'),
                  items: ['EUR', 'USD', 'CHF', 'GBP'].map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                  onChanged: (v) => setState(() => _currency = v ?? 'EUR'),
                )),
              ]),
              const SizedBox(height: 16),

              // Date
              InkWell(
                onTap: () async {
                  final picked = await showDatePicker(
                    context: context,
                    initialDate: _date,
                    firstDate: DateTime(2000),
                    lastDate: DateTime.now(),
                  );
                  if (picked != null) setState(() => _date = picked);
                },
                child: InputDecorator(
                  decoration: const InputDecoration(labelText: 'Date', suffixIcon: Icon(Icons.calendar_today)),
                  child: Text('${_date.day.toString().padLeft(2, '0')}/${_date.month.toString().padLeft(2, '0')}/${_date.year}'),
                ),
              ),
              const SizedBox(height: 16),

              // Notes
              TextFormField(
                controller: _notesCtrl,
                decoration: const InputDecoration(labelText: 'Notes (optionnel)'),
                maxLines: 3,
              ),
              const SizedBox(height: 24),

              ElevatedButton(
                onPressed: _isLoading ? null : _submit,
                child: _isLoading
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Enregistrer'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
