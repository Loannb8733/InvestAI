import 'package:dio/dio.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/errors/app_exception.dart';
import 'package:investai_mobile/data/models/transaction/transaction_model.dart';

class TransactionRepository {
  final Dio _dio;
  TransactionRepository(this._dio);

  Future<List<TransactionModel>> listTransactions({
    String? portfolioId,
    int skip = 0,
    int limit = 50,
  }) async {
    try {
      final response = await _dio.get(
        ApiConstants.transactions,
        queryParameters: {
          if (portfolioId != null) 'portfolio_id': portfolioId,
          'skip': skip,
          'limit': limit,
        },
      );
      return (response.data as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .map(TransactionModel.fromJson)
          .toList();
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<TransactionModel> createTransaction(Map<String, dynamic> data) async {
    try {
      final response = await _dio.post(ApiConstants.transactions, data: data);
      return TransactionModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> deleteTransaction(String id) async {
    try {
      await _dio.delete('${ApiConstants.transactions}/$id');
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }
}
