import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/currency_formatter.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _calendarProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final now = DateTime.now();
  final r = await dio.get(ApiConstants.calendarEvents, queryParameters: {
    'start_date': DateTime(now.year, now.month, 1).toIso8601String().substring(0, 10),
    'end_date': DateTime(now.year, now.month + 3, 0).toIso8601String().substring(0, 10),
  });
  return r.data as List<dynamic>;
});

class CalendarScreen extends ConsumerWidget {
  const CalendarScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eventsAsync = ref.watch(_calendarProvider);

    return Scaffold(
      appBar: AppBar(leading: const DrawerMenuButton(), title: const Text('Calendrier financier')),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_calendarProvider),
        child: eventsAsync.when(
          loading: () => const AppLoading(),
          error: (_, __) => const AppEmptyState(message: 'Erreur de chargement', icon: Icons.calendar_today),
          data: (events) {
            if (events.isEmpty) {
              return const AppEmptyState(
                message: 'Aucun événement',
                description: 'Dividendes, loyers et échéances apparaîtront ici',
                icon: Icons.calendar_today_outlined,
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: events.length,
              itemBuilder: (_, i) {
                final event = events[i] as Map<String, dynamic>;
                final date = DateTime.tryParse(event['event_date'] as String? ?? '') ?? DateTime.now();
                final amount = (event['amount'] as num?)?.toDouble();
                final currency = event['currency'] as String? ?? 'EUR';
                const typeColors = {'dividend': AppColors.success, 'rent': AppColors.info, 'tax': AppColors.error, 'maturity': AppColors.warning};
                final eventType = event['event_type'] as String? ?? 'other';
                final color = typeColors[eventType] ?? AppColors.primary;
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: color.withOpacity(0.2),
                      child: Text(DateFormatter.formatShort(date).substring(0, 2), style: TextStyle(color: color, fontWeight: FontWeight.bold)),
                    ),
                    title: Text(event['title'] as String? ?? ''),
                    subtitle: Text('${DateFormatter.formatDate(date)} · ${_typeLabel(eventType)}'),
                    trailing: amount != null ? Text(CurrencyFormatter.format(amount, currency: currency), style: const TextStyle(fontWeight: FontWeight.w600)) : null,
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  String _typeLabel(String type) {
    const labels = {'dividend': 'Dividende', 'rent': 'Loyer', 'interest': 'Intérêts', 'tax': 'Impôt', 'earning': 'Résultats', 'maturity': 'Échéance'};
    return labels[type] ?? type;
  }
}
