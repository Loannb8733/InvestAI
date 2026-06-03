class UserModel {
  final String id;
  final String email;
  final String? firstName;
  final String? lastName;
  final String role;
  final bool mfaEnabled;
  final bool isActive;
  final String preferredCurrency;
  final DateTime createdAt;

  const UserModel({
    required this.id,
    required this.email,
    this.firstName,
    this.lastName,
    required this.role,
    required this.mfaEnabled,
    required this.isActive,
    required this.preferredCurrency,
    required this.createdAt,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] as String,
      email: json['email'] as String,
      firstName: json['first_name'] as String?,
      lastName: json['last_name'] as String?,
      role: json['role'] as String? ?? 'user',
      mfaEnabled: json['mfa_enabled'] as bool? ?? false,
      isActive: json['is_active'] as bool? ?? true,
      preferredCurrency: json['preferred_currency'] as String? ?? 'EUR',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }

  String get displayName {
    if (firstName != null && lastName != null) return '$firstName $lastName';
    if (firstName != null) return firstName!;
    return email;
  }

  bool get isAdmin => role == 'admin';

  UserModel copyWith({
    String? firstName,
    String? lastName,
    String? preferredCurrency,
    bool? mfaEnabled,
  }) {
    return UserModel(
      id: id,
      email: email,
      firstName: firstName ?? this.firstName,
      lastName: lastName ?? this.lastName,
      role: role,
      mfaEnabled: mfaEnabled ?? this.mfaEnabled,
      isActive: isActive,
      preferredCurrency: preferredCurrency ?? this.preferredCurrency,
      createdAt: createdAt,
    );
  }
}
