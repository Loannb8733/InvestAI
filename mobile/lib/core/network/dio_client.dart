import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:investai_mobile/core/network/auth_interceptor.dart';

class DioClient {
  static Dio create(AuthInterceptor authInterceptor) {
    final baseUrl = dotenv.env['API_BASE_URL'] ?? 'http://localhost:8000';

    final dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    dio.interceptors.add(authInterceptor);
    dio.interceptors.add(LogInterceptor(
      requestBody: false,
      responseBody: false,
      logPrint: (obj) => debugPrint(obj.toString()),
    ));

    return dio;
  }
}
