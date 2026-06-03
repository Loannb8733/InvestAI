import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/data/models/portfolio/portfolio_model.dart';
import 'package:investai_mobile/data/models/portfolio/asset_model.dart';
import 'package:investai_mobile/data/repositories/portfolio_repository.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';

final portfolioRepositoryProvider = Provider<PortfolioRepository>((ref) {
  return PortfolioRepository(ref.watch(dioProvider));
});

final portfoliosProvider = FutureProvider<List<PortfolioModel>>((ref) async {
  return ref.watch(portfolioRepositoryProvider).listPortfolios();
});

final assetsProvider = FutureProvider.family<List<AssetModel>, String?>(
  (ref, portfolioId) async {
    return ref.watch(portfolioRepositoryProvider).listAssets(portfolioId: portfolioId);
  },
);

final selectedPortfolioIdProvider = StateProvider<String?>((ref) => null);
