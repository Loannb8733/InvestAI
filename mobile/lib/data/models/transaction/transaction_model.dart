import 'package:investai_mobile/core/utils/parse_helpers.dart';

class TransactionModel {
  final String id;
  final String portfolioId;
  final String? assetId;
  final String assetSymbol;
  final String assetName;
  final String transactionType;
  final double quantity;
  final double price;
  final double fee;
  final double totalAmount;
  final String currency;
  final DateTime transactionDate;
  final String? notes;
  final DateTime createdAt;

  const TransactionModel({
    required this.id,
    required this.portfolioId,
    this.assetId,
    required this.assetSymbol,
    required this.assetName,
    required this.transactionType,
    required this.quantity,
    required this.price,
    required this.fee,
    required this.totalAmount,
    required this.currency,
    required this.transactionDate,
    this.notes,
    required this.createdAt,
  });

  factory TransactionModel.fromJson(Map<String, dynamic> json) {
    return TransactionModel(
      id: json['id'] as String,
      portfolioId: json['portfolio_id'] as String? ?? '',
      assetId: json['asset_id'] as String?,
      assetSymbol: json['asset_symbol'] as String? ?? '',
      assetName: json['asset_name'] as String? ?? '',
      transactionType: json['transaction_type'] as String? ?? 'buy',
      quantity: parseDoubleOrZero(json['quantity']),
      price: parseDoubleOrZero(json['price']),
      fee: parseDoubleOrZero(json['fee']),
      totalAmount: parseDoubleOrZero(json['total_amount']),
      currency: json['currency'] as String? ?? 'EUR',
      transactionDate: DateTime.tryParse(json['transaction_date'] as String? ?? '') ?? DateTime.now(),
      notes: json['notes'] as String?,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }

  String get typeLabel {
    const labels = {
      'buy': 'Achat',
      'sell': 'Vente',
      'deposit': 'Dépôt',
      'withdrawal': 'Retrait',
      'dividend': 'Dividende',
      'fee': 'Frais',
      'transfer': 'Transfert',
    };
    return labels[transactionType] ?? transactionType;
  }

  bool get isBuy => transactionType == 'buy' || transactionType == 'deposit';
}
