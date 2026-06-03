import 'package:dio/dio.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/errors/app_exception.dart';
import 'package:investai_mobile/data/models/auth/token_model.dart';
import 'package:investai_mobile/data/models/auth/user_model.dart';

class AuthRepository {
  final Dio _dio;

  AuthRepository(this._dio);

  Future<TokenModel> login(String email, String password) async {
    try {
      final response = await _dio.post(
        ApiConstants.login,
        data: {'email': email, 'password': password},
      );
      return TokenModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<TokenModel> verifyMFA(String tempToken, String code) async {
    try {
      final response = await _dio.post(
        ApiConstants.verifyMFA,
        data: {'temp_token': tempToken, 'code': code},
      );
      return TokenModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> register(String email, String password, {String? firstName, String? lastName}) async {
    try {
      await _dio.post(
        ApiConstants.register,
        data: {
          'email': email,
          'password': password,
          if (firstName != null) 'first_name': firstName,
          if (lastName != null) 'last_name': lastName,
        },
      );
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<UserModel> getCurrentUser() async {
    try {
      final response = await _dio.get(ApiConstants.me);
      return UserModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> logout() async {
    try {
      await _dio.post(ApiConstants.logout);
    } catch (_) {}
  }

  Future<void> forgotPassword(String email) async {
    try {
      await _dio.post(ApiConstants.forgotPassword, data: {'email': email});
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<UserModel> updateProfile({
    String? firstName,
    String? lastName,
    String? preferredCurrency,
  }) async {
    try {
      final response = await _dio.put(
        ApiConstants.profile,
        data: {
          if (firstName != null) 'first_name': firstName,
          if (lastName != null) 'last_name': lastName,
          if (preferredCurrency != null) 'preferred_currency': preferredCurrency,
        },
      );
      return UserModel.fromJson(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> changePassword(String current, String newPwd) async {
    try {
      await _dio.post(
        ApiConstants.changePassword,
        data: {'current_password': current, 'new_password': newPwd},
      );
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<Map<String, dynamic>> setupMFA() async {
    try {
      final response = await _dio.post(ApiConstants.setupMFA);
      return response.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> confirmMFA(String code) async {
    try {
      await _dio.post(ApiConstants.verifyMFA, data: {'code': code});
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }

  Future<void> disableMFA(String code) async {
    try {
      await _dio.post(ApiConstants.disableMFA, data: {'code': code});
    } on DioException catch (e) {
      throw AppException.fromDioError(e);
    }
  }
}
