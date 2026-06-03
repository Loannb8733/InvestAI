class AppException implements Exception {
  final String message;
  final int? statusCode;
  final String? code;

  const AppException({
    required this.message,
    this.statusCode,
    this.code,
  });

  factory AppException.fromDioError(dynamic err) {
    if (err?.response != null) {
      final statusCode = err.response.statusCode as int?;
      final data = err.response.data;
      String message = 'Une erreur est survenue';

      if (data is Map) {
        message = data['detail']?.toString() ??
            data['message']?.toString() ??
            message;
      }

      return AppException(
        message: message,
        statusCode: statusCode,
      );
    }
    return const AppException(message: 'Erreur de connexion. Vérifiez votre réseau.');
  }

  @override
  String toString() => message;
}

class AuthException extends AppException {
  const AuthException({required super.message, super.statusCode, super.code});
}

class NetworkException extends AppException {
  const NetworkException({required super.message});
}
