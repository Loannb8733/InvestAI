import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:investai_mobile/core/constants/storage_keys.dart';
import 'package:investai_mobile/core/services/storage_service.dart';

class AuthInterceptor extends Interceptor {
  final StorageService _storage;
  Dio? _refreshDio;
  bool _isRefreshing = false;
  final List<RequestOptions> _pendingRequests = [];

  AuthInterceptor(this._storage);

  void setRefreshDio(Dio dio) {
    _refreshDio = dio;
  }

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await _storage.readSecure(StorageKeys.accessToken);
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      if (_isRefreshing) {
        _pendingRequests.add(err.requestOptions);
        return;
      }

      _isRefreshing = true;
      try {
        final refreshToken = await _storage.readSecure(StorageKeys.refreshToken);
        if (refreshToken == null) {
          await _clearTokens();
          handler.next(err);
          return;
        }

        final response = await _refreshDio?.post(
          '/api/v1/auth/refresh',
          data: {'refresh_token': refreshToken},
        );

        if (response?.statusCode == 200) {
          final newAccessToken = response!.data['access_token'] as String;
          final newRefreshToken = response.data['refresh_token'] as String?;

          await _storage.writeSecure(StorageKeys.accessToken, newAccessToken);
          if (newRefreshToken != null) {
            await _storage.writeSecure(StorageKeys.refreshToken, newRefreshToken);
          }

          // Retry original request
          err.requestOptions.headers['Authorization'] = 'Bearer $newAccessToken';
          final retryResponse = await _refreshDio?.request(
            err.requestOptions.path,
            options: Options(
              method: err.requestOptions.method,
              headers: err.requestOptions.headers,
            ),
            data: err.requestOptions.data,
            queryParameters: err.requestOptions.queryParameters,
          );

          _isRefreshing = false;
          handler.resolve(retryResponse!);
        } else {
          await _clearTokens();
          handler.next(err);
        }
      } catch (e) {
        debugPrint('Token refresh failed: $e');
        _isRefreshing = false;
        await _clearTokens();
        handler.next(err);
      }
    } else {
      handler.next(err);
    }
  }

  Future<void> _clearTokens() async {
    await _storage.deleteSecure(StorageKeys.accessToken);
    await _storage.deleteSecure(StorageKeys.refreshToken);
    _isRefreshing = false;
  }
}
