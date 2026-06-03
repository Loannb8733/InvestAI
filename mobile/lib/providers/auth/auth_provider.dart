import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/storage_keys.dart';
import 'package:investai_mobile/data/repositories/auth_repository.dart';
import 'package:investai_mobile/data/models/auth/token_model.dart';
import 'package:investai_mobile/providers/auth/auth_state.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/providers/core/storage_provider.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final dio = ref.watch(dioProvider);
  return AuthRepository(dio);
});

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(
    ref.watch(authRepositoryProvider),
    ref.watch(storageProvider),
  );
});

class AuthNotifier extends StateNotifier<AuthState> {
  final AuthRepository _repository;
  final dynamic _storage;

  AuthNotifier(this._repository, this._storage) : super(const AuthState()) {
    _init();
  }

  Future<void> _init() async {
    final token = await _storage.readSecure(StorageKeys.accessToken);
    if (token != null) {
      try {
        final user = await _repository.getCurrentUser();
        state = state.copyWith(
          isAuthenticated: true,
          isLoading: false,
          user: user,
        );
      } catch (_) {
        await _storage.deleteSecure(StorageKeys.accessToken);
        await _storage.deleteSecure(StorageKeys.refreshToken);
        state = state.copyWith(isAuthenticated: false, isLoading: false);
      }
    } else {
      state = state.copyWith(isAuthenticated: false, isLoading: false);
    }
  }

  Future<TokenModel?> login(String email, String password) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final token = await _repository.login(email, password);

      if (token.requiresMFA) {
        state = state.copyWith(isLoading: false);
        return token;
      }

      await _saveTokens(token);
      final user = await _repository.getCurrentUser();
      state = state.copyWith(
        isAuthenticated: true,
        isLoading: false,
        user: user,
      );
      return null;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  Future<void> verifyMFA(String tempToken, String code) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final token = await _repository.verifyMFA(tempToken, code);
      await _saveTokens(token);
      final user = await _repository.getCurrentUser();
      state = state.copyWith(
        isAuthenticated: true,
        isLoading: false,
        user: user,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  Future<void> register(String email, String password, {String? firstName, String? lastName}) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      await _repository.register(email, password, firstName: firstName, lastName: lastName);
      state = state.copyWith(isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    await _storage.clearSecure();
    state = const AuthState(isLoading: false);
  }

  Future<void> refreshUser() async {
    try {
      final user = await _repository.getCurrentUser();
      state = state.copyWith(user: user);
    } catch (_) {}
  }

  Future<void> _saveTokens(TokenModel token) async {
    if (token.accessToken.isNotEmpty) {
      await _storage.writeSecure(StorageKeys.accessToken, token.accessToken);
    }
    if (token.refreshToken != null) {
      await _storage.writeSecure(StorageKeys.refreshToken, token.refreshToken!);
    }
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }
}
