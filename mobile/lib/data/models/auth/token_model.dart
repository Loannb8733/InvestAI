class TokenModel {
  final String accessToken;
  final String? refreshToken;
  final bool requiresMFA;
  final String? tempToken;

  const TokenModel({
    required this.accessToken,
    this.refreshToken,
    this.requiresMFA = false,
    this.tempToken,
  });

  factory TokenModel.fromJson(Map<String, dynamic> json) {
    return TokenModel(
      accessToken: json['access_token'] as String? ?? '',
      refreshToken: json['refresh_token'] as String?,
      requiresMFA: json['requires_mfa'] as bool? ?? false,
      tempToken: json['temp_token'] as String?,
    );
  }
}
