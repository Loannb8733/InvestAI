import 'package:dio/dio.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/errors/app_exception.dart';
import 'package:investai_mobile/data/models/dashboard/dashboard_summary_model.dart';

class DashboardRepository {
  final Dio _dio;
  DashboardRepository(this._dio);

  Future<DashboardSummaryModel> getDashboard({String? portfolioId, String period = '1M'}) async {
    try {
      final response = await _dio.get(
        ApiConstants.dashboard,
        queryParameters: {
          if (portfolioId != null) 'portfolio_id': portfolioId,
          'period': period,
        },
      );
      return DashboardSummaryModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<List<ChartPoint>> getSparklines({String? portfolioId, String period = '1M'}) async {
    try {
      final response = await _dio.get(
        ApiConstants.sparklines,
        queryParameters: {
          if (portfolioId != null) 'portfolio_id': portfolioId,
          'period': period,
        },
      );
      final data = response.data;
      if (data is List) {
        return data
            .cast<Map<String, dynamic>>()
            .map(ChartPoint.fromJson)
            .toList();
      }
      final points = data['points'] as List<dynamic>? ?? [];
      return points.cast<Map<String, dynamic>>().map(ChartPoint.fromJson).toList();
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }
}
