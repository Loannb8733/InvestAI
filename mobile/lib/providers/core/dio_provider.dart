import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:investai_mobile/core/network/auth_interceptor.dart';
import 'package:investai_mobile/providers/core/storage_provider.dart';

final authInterceptorProvider = Provider<AuthInterceptor>((ref) {
  return AuthInterceptor(ref.watch(storageProvider));
});

final dioProvider = Provider<Dio>((ref) {
  final baseUrl = dotenv.env['API_BASE_URL'] ?? 'http://localhost:8000';
  final authInterceptor = ref.watch(authInterceptorProvider);

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

  // Refresh Dio (no auth interceptor to avoid loops)
  final refreshDio = Dio(BaseOptions(baseUrl: baseUrl));
  authInterceptor.setRefreshDio(refreshDio);

  dio.interceptors.add(authInterceptor);

  return dio;
});
