# InvestAI Mobile

Application mobile Flutter pour InvestAI — gestion et analyse d'investissements.

## Stack

- **Flutter 3.16+** avec Dart 3.0+
- **State**: Riverpod 2.x (StateNotifier + FutureProvider)
- **Navigation**: go_router 13.x
- **HTTP**: Dio 5.x avec intercepteur JWT auto-refresh
- **Charts**: fl_chart 0.68
- **Stockage sécurisé**: flutter_secure_storage (tokens JWT)
- **Push notifications**: Firebase Cloud Messaging (FCM)
- **Theme**: Material 3, dark/light, police Inter

## Prérequis

- Flutter SDK ≥ 3.16
- Dart SDK ≥ 3.0
- Android Studio / Xcode (pour les émulateurs)
- Firebase project avec Android/iOS apps configurées

## Installation

```bash
cd mobile

# Installer les dépendances
flutter pub get

# Configurer l'env
cp .env.example .env
# Éditer .env avec l'URL de votre API

# Firebase (requis pour les push notifs)
# Placer google-services.json dans android/app/
# Placer GoogleService-Info.plist dans ios/Runner/
```

## Lancer l'app

```bash
# Debug sur Android
flutter run -d android

# Debug sur iOS
flutter run -d ios

# Debug web
flutter run -d chrome

# Release Android APK
flutter build apk --release

# Release Android AAB (Play Store)
flutter build appbundle --release

# Release iOS
flutter build ios --release
```

## Architecture

```
lib/
├── main.dart              # Entry point
├── app.dart               # MaterialApp.router
├── core/
│   ├── constants/         # API paths, storage keys, app constants
│   ├── errors/            # AppException hierarchy
│   ├── network/           # Dio + AuthInterceptor (auto token refresh)
│   ├── router/            # go_router + route guards
│   ├── services/          # StorageService, FcmService
│   ├── theme/             # AppTheme, AppColors
│   └── utils/             # CurrencyFormatter, DateFormatter, Validators
├── data/
│   ├── models/            # Plain Dart classes (fromJson)
│   └── repositories/      # Dio-backed API repositories
├── providers/             # Riverpod providers + StateNotifiers
└── presentation/
    ├── widgets/           # Shared widgets (AppLoading, AppErrorWidget, etc.)
    └── screens/           # Feature screens
        ├── auth/          # Login, Register, MFA, ForgotPassword
        ├── dashboard/     # Dashboard + chart + metrics
        ├── portfolio/     # Portfolio + assets list
        ├── transactions/  # Transaction list + form
        ├── analytics/     # Performance / Diversification / Risk tabs
        ├── intelligence/  # Insights / Predictions / Anomalies
        ├── strategy/      # Planned orders
        ├── reports/       # Report list + generate
        ├── alerts/        # Price alerts
        ├── notes/         # Investment journal
        ├── calendar/      # Financial events
        ├── settings/      # Profile + password + currency
        ├── crowdfunding/  # Crowdfunding projects
        ├── simulations/   # FIRE + DCA calculators
        └── admin/         # Admin stats + users (admin only)
```

## Fonctionnalités

- **Auth complète**: Login, Register, MFA TOTP, Mot de passe oublié
- **JWT auto-refresh**: L'intercepteur renouvelle automatiquement l'access token
- **Dashboard**: Valeur totale, PnL, graphique, métriques Sharpe/Volatilité/Drawdown
- **Portefeuille**: Liste des actifs par portefeuille avec allocation
- **Transactions**: Pagination infinie, filtre par type et portefeuille, formulaire
- **Analytics**: Performance, Diversification, Risque (VaR, Drawdown)
- **Intelligence IA**: Insights, Prédictions, Anomalies
- **Alertes**: Alertes prix configurables
- **Notes**: Journal d'investissement avec tags
- **Calendrier**: Dividendes, loyers, échéances
- **Rapports**: Génération PDF/Excel
- **Crowdfunding**: Suivi des projets
- **Simulations**: FIRE calculator, DCA simulator
- **Admin**: Statistiques et gestion utilisateurs (admin only)
- **Push notifications**: FCM pour alertes et notifications temps réel

## Variables d'environnement

```env
API_BASE_URL=https://api.investai.example.com
ENVIRONMENT=production
```

## Firebase Setup

1. Créez un projet Firebase
2. Activez Cloud Messaging
3. Android: téléchargez `google-services.json` → `android/app/`
4. iOS: téléchargez `GoogleService-Info.plist` → `ios/Runner/`
5. Enregistrez le token FCM auprès de votre API backend pour recevoir des push
