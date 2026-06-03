import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/data/models/transaction/transaction_model.dart';
import 'package:investai_mobile/data/repositories/transaction_repository.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';

final transactionRepositoryProvider = Provider<TransactionRepository>((ref) {
  return TransactionRepository(ref.watch(dioProvider));
});

class TransactionsNotifier extends StateNotifier<AsyncValue<List<TransactionModel>>> {
  final TransactionRepository _repo;
  String? _portfolioId;
  int _skip = 0;
  static const int _pageSize = 50;
  bool _hasMore = true;

  TransactionsNotifier(this._repo) : super(const AsyncValue.loading()) {
    load();
  }

  Future<void> load({String? portfolioId, bool reset = false}) async {
    if (reset || portfolioId != _portfolioId) {
      _portfolioId = portfolioId;
      _skip = 0;
      _hasMore = true;
      state = const AsyncValue.loading();
    }
    if (!_hasMore) return;

    try {
      final page = await _repo.listTransactions(
        portfolioId: _portfolioId,
        skip: _skip,
        limit: _pageSize,
      );
      _hasMore = page.length == _pageSize;
      _skip += page.length;
      final existing = state.valueOrNull ?? [];
      state = AsyncValue.data(_skip == page.length ? page : [...existing, ...page]);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  bool get hasMore => _hasMore;

  void loadMore() => load(portfolioId: _portfolioId);
}

final transactionsProvider = StateNotifierProvider<TransactionsNotifier, AsyncValue<List<TransactionModel>>>(
  (ref) => TransactionsNotifier(ref.watch(transactionRepositoryProvider)),
);
