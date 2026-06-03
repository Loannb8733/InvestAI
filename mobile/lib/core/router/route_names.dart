abstract class RouteNames {
  static const String splash = '/';
  static const String login = '/login';
  static const String register = '/register';
  static const String forgotPassword = '/forgot-password';
  static const String mfaVerify = '/mfa';

  // Main tabs
  static const String dashboard = '/dashboard';
  static const String portfolio = '/portfolio';
  static const String transactions = '/transactions';
  static const String analytics = '/analytics';
  static const String intelligence = '/intelligence';
  static const String strategy = '/strategy';
  static const String reports = '/reports';
  static const String alerts = '/alerts';
  static const String notes = '/notes';
  static const String calendar = '/calendar';
  static const String settings = '/settings';
  static const String crowdfunding = '/crowdfunding';
  static const String simulations = '/simulations';
  static const String admin = '/admin';

  // Detail routes
  static const String portfolioDetail = '/portfolio/:id';
  static const String transactionForm = '/transactions/new';
  static const String noteDetail = '/notes/:id';
  static const String crowdfundingDetail = '/crowdfunding/:id';
}
