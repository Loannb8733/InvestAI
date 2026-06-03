abstract class AppConstants {
  static const String appName = 'InvestAI';
  static const String appVersion = '1.0.0';

  static const int defaultPageSize = 50;
  static const int notificationRefreshInterval = 60; // seconds

  static const List<String> supportedCurrencies = ['EUR', 'USD', 'CHF', 'GBP'];
  static const String defaultCurrency = 'EUR';

  static const Map<String, String> currencySymbols = {
    'EUR': '€',
    'USD': '\$',
    'CHF': 'CHF',
    'GBP': '£',
  };

  static const List<String> portfolioPeriods = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

  static const List<String> assetTypes = [
    'crypto',
    'stock',
    'etf',
    'real_estate',
    'bond',
    'cash',
    'other',
  ];

  static const Map<String, String> assetTypeLabels = {
    'crypto': 'Crypto',
    'stock': 'Action',
    'etf': 'ETF',
    'real_estate': 'Immobilier',
    'bond': 'Obligation',
    'cash': 'Liquidités',
    'other': 'Autre',
  };
}
