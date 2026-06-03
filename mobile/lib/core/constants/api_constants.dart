abstract class ApiConstants {
  static const String apiVersion = '/api/v1';

  // Auth
  static const String login = '$apiVersion/auth/login';
  static const String register = '$apiVersion/auth/register';
  static const String refresh = '$apiVersion/auth/refresh';
  static const String logout = '$apiVersion/auth/logout';
  static const String me = '$apiVersion/auth/me';
  static const String forgotPassword = '$apiVersion/auth/forgot-password';
  static const String resetPassword = '$apiVersion/auth/reset-password';
  static const String setupMFA = '$apiVersion/auth/mfa/setup';
  static const String verifyMFA = '$apiVersion/auth/mfa/verify';
  static const String disableMFA = '$apiVersion/auth/mfa/disable';

  // Profile
  static const String profile = '$apiVersion/profile';
  static const String changePassword = '$apiVersion/profile/change-password';

  // Portfolios
  static const String portfolios = '$apiVersion/portfolios';

  // Assets
  static const String assets = '$apiVersion/assets';

  // Transactions
  static const String transactions = '$apiVersion/transactions';

  // Dashboard
  static const String dashboard = '$apiVersion/dashboard';
  static const String portfolioDashboard = '$apiVersion/dashboard/portfolio';
  static const String sparklines = '$apiVersion/dashboard/sparklines';

  // Analytics
  static const String analyticsPerformance = '$apiVersion/analytics/performance';
  static const String analyticsHistorical = '$apiVersion/analytics/historical';
  static const String analyticsDiversification = '$apiVersion/analytics/diversification';
  static const String analyticsCorrelation = '$apiVersion/analytics/correlation';
  static const String analyticsMonteCarlo = '$apiVersion/analytics/monte-carlo';
  static const String analyticsRisk = '$apiVersion/analytics/risk';

  // Intelligence
  static const String insights = '$apiVersion/intelligence/insights';
  static const String predictions = '$apiVersion/intelligence/predictions';
  static const String anomalies = '$apiVersion/intelligence/anomalies';
  static const String sentiment = '$apiVersion/intelligence/sentiment';

  // Strategy
  static const String plannedOrders = '$apiVersion/strategy/planned-orders';
  static const String rebalancing = '$apiVersion/strategy/rebalancing';

  // Alerts
  static const String alerts = '$apiVersion/alerts';

  // Notes
  static const String notes = '$apiVersion/notes';

  // Calendar
  static const String calendarEvents = '$apiVersion/calendar/events';

  // Reports
  static const String reports = '$apiVersion/reports';

  // Notifications
  static const String notifications = '$apiVersion/notifications';
  static const String notificationsUnreadCount = '$apiVersion/notifications/unread-count';

  // Crowdfunding
  static const String crowdfunding = '$apiVersion/crowdfunding/projects';

  // Simulations
  static const String simulationFIRE = '$apiVersion/simulations/fire';
  static const String simulationDCA = '$apiVersion/simulations/dca';
  static const String simulationWhatIf = '$apiVersion/simulations/whatif';

  // Admin
  static const String adminUsers = '$apiVersion/admin/users';
  static const String adminStats = '$apiVersion/admin/stats';
  static const String adminAuditLog = '$apiVersion/admin/audit-log';
}
