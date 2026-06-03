class Validators {
  static String? email(String? value) {
    if (value == null || value.isEmpty) return 'L\'email est requis';
    final regex = RegExp(r'^[\w-.]+@([\w-]+\.)+[\w-]{2,4}$');
    if (!regex.hasMatch(value)) return 'Email invalide';
    return null;
  }

  static String? password(String? value) {
    if (value == null || value.isEmpty) return 'Le mot de passe est requis';
    if (value.length < 10) return 'Minimum 10 caractères';
    if (!RegExp(r'[A-Z]').hasMatch(value)) return 'Au moins une majuscule';
    if (!RegExp(r'[0-9]').hasMatch(value)) return 'Au moins un chiffre';
    return null;
  }

  static String? required(String? value, [String fieldName = 'Ce champ']) {
    if (value == null || value.trim().isEmpty) return '$fieldName est requis';
    return null;
  }

  static String? positiveNumber(String? value) {
    if (value == null || value.isEmpty) return 'Requis';
    final n = double.tryParse(value.replaceAll(',', '.'));
    if (n == null) return 'Nombre invalide';
    if (n <= 0) return 'Doit être positif';
    return null;
  }

  static String? mfaCode(String? value) {
    if (value == null || value.length != 6) return 'Code à 6 chiffres requis';
    if (!RegExp(r'^\d{6}$').hasMatch(value)) return 'Chiffres uniquement';
    return null;
  }
}
