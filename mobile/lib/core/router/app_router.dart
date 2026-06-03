import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:investai_mobile/core/router/route_names.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';
import 'package:investai_mobile/presentation/screens/auth/login_screen.dart';
import 'package:investai_mobile/presentation/screens/auth/register_screen.dart';
import 'package:investai_mobile/presentation/screens/auth/forgot_password_screen.dart';
import 'package:investai_mobile/presentation/screens/auth/mfa_screen.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';
import 'package:investai_mobile/presentation/screens/dashboard/dashboard_screen.dart';
import 'package:investai_mobile/presentation/screens/portfolio/portfolio_screen.dart';
import 'package:investai_mobile/presentation/screens/transactions/transactions_screen.dart';
import 'package:investai_mobile/presentation/screens/transactions/transaction_form_screen.dart';
import 'package:investai_mobile/presentation/screens/analytics/analytics_screen.dart';
import 'package:investai_mobile/presentation/screens/intelligence/intelligence_screen.dart';
import 'package:investai_mobile/presentation/screens/strategy/strategy_screen.dart';
import 'package:investai_mobile/presentation/screens/reports/reports_screen.dart';
import 'package:investai_mobile/presentation/screens/alerts/alerts_screen.dart';
import 'package:investai_mobile/presentation/screens/notes/notes_screen.dart';
import 'package:investai_mobile/presentation/screens/calendar/calendar_screen.dart';
import 'package:investai_mobile/presentation/screens/settings/settings_screen.dart';
import 'package:investai_mobile/presentation/screens/crowdfunding/crowdfunding_screen.dart';
import 'package:investai_mobile/presentation/screens/simulations/simulations_screen.dart';
import 'package:investai_mobile/presentation/screens/admin/admin_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();
final _shellNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: RouteNames.dashboard,
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final isLoading = authState.isLoading;

      if (isLoading) return null;

      final isAuthRoute = state.matchedLocation == RouteNames.login ||
          state.matchedLocation == RouteNames.register ||
          state.matchedLocation == RouteNames.forgotPassword ||
          state.matchedLocation == RouteNames.mfaVerify;

      if (!isAuthenticated && !isAuthRoute) return RouteNames.login;
      if (isAuthenticated && isAuthRoute) return RouteNames.dashboard;
      return null;
    },
    routes: [
      // Auth routes
      GoRoute(
        path: RouteNames.login,
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: RouteNames.register,
        builder: (_, __) => const RegisterScreen(),
      ),
      GoRoute(
        path: RouteNames.forgotPassword,
        builder: (_, __) => const ForgotPasswordScreen(),
      ),
      GoRoute(
        path: RouteNames.mfaVerify,
        builder: (_, state) {
          final tempToken = state.uri.queryParameters['token'] ?? '';
          return MfaScreen(tempToken: tempToken);
        },
      ),

      // Main shell with bottom nav
      ShellRoute(
        navigatorKey: _shellNavigatorKey,
        builder: (_, __, child) => MainShell(child: child),
        routes: [
          GoRoute(
            path: RouteNames.dashboard,
            builder: (_, __) => const DashboardScreen(),
          ),
          GoRoute(
            path: RouteNames.portfolio,
            builder: (_, __) => const PortfolioScreen(),
          ),
          GoRoute(
            path: RouteNames.transactions,
            builder: (_, __) => const TransactionsScreen(),
            routes: [
              GoRoute(
                path: 'new',
                parentNavigatorKey: _rootNavigatorKey,
                builder: (_, __) => const TransactionFormScreen(),
              ),
            ],
          ),
          GoRoute(
            path: RouteNames.analytics,
            builder: (_, __) => const AnalyticsScreen(),
          ),
          GoRoute(
            path: RouteNames.intelligence,
            builder: (_, __) => const IntelligenceScreen(),
          ),
          GoRoute(
            path: RouteNames.strategy,
            builder: (_, __) => const StrategyScreen(),
          ),
          GoRoute(
            path: RouteNames.reports,
            builder: (_, __) => const ReportsScreen(),
          ),
          GoRoute(
            path: RouteNames.alerts,
            builder: (_, __) => const AlertsScreen(),
          ),
          GoRoute(
            path: RouteNames.notes,
            builder: (_, __) => const NotesScreen(),
          ),
          GoRoute(
            path: RouteNames.calendar,
            builder: (_, __) => const CalendarScreen(),
          ),
          GoRoute(
            path: RouteNames.settings,
            builder: (_, __) => const SettingsScreen(),
          ),
          GoRoute(
            path: RouteNames.crowdfunding,
            builder: (_, __) => const CrowdfundingScreen(),
          ),
          GoRoute(
            path: RouteNames.simulations,
            builder: (_, __) => const SimulationsScreen(),
          ),
          GoRoute(
            path: RouteNames.admin,
            builder: (_, __) => const AdminScreen(),
          ),
        ],
      ),
    ],
  );
});
