import 'package:dio/dio.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/errors/app_exception.dart';
import 'package:investai_mobile/data/models/portfolio/portfolio_model.dart';
import 'package:investai_mobile/data/models/portfolio/asset_model.dart';

class PortfolioRepository {
  final Dio _dio;
  PortfolioRepository(this._dio);

  Future<List<PortfolioModel>> listPortfolios() async {
    try {
      final response = await _dio.get(ApiConstants.portfolios);
      return (response.data as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .map(PortfolioModel.fromJson)
          .toList();
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<PortfolioModel> createPortfolio(String name, {String? description}) async {
    try {
      final response = await _dio.post(
        ApiConstants.portfolios,
        data: {'name': name, if (description != null) 'description': description},
      );
      return PortfolioModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> deletePortfolio(String id) async {
    try {
      await _dio.delete('${ApiConstants.portfolios}/$id');
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<List<AssetModel>> listAssets({String? portfolioId}) async {
    try {
      final response = await _dio.get(
        ApiConstants.assets,
        queryParameters: {if (portfolioId != null) 'portfolio_id': portfolioId},
      );
      return (response.data as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .map(AssetModel.fromJson)
          .toList();
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }
}
