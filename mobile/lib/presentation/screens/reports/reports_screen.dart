import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _reportsProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.reports);
  return r.data as List<dynamic>;
});

class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reportsAsync = ref.watch(_reportsProvider);

    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: const Text('Rapports'),
        actions: [
          IconButton(icon: const Icon(Icons.add), onPressed: () => _showGenerateDialog(context, ref)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_reportsProvider),
        child: reportsAsync.when(
          loading: () => const AppLoading(),
          error: (_, __) => const AppEmptyState(message: 'Erreur de chargement', icon: Icons.description_outlined),
          data: (reports) {
            if (reports.isEmpty) {
              return AppEmptyState(
                message: 'Aucun rapport',
                description: 'Générez des rapports PDF ou Excel',
                icon: Icons.description_outlined,
                actionLabel: 'Générer un rapport',
                onAction: () => _showGenerateDialog(context, ref),
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: reports.length,
              itemBuilder: (_, i) {
                final report = reports[i] as Map<String, dynamic>;
                final createdAt = DateTime.tryParse(report['created_at'] as String? ?? '');
                final format = report['format'] as String? ?? 'pdf';
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: Icon(format == 'pdf' ? Icons.picture_as_pdf : Icons.table_chart, color: format == 'pdf' ? AppColors.error : AppColors.success),
                    title: Text(report['name'] as String? ?? 'Rapport'),
                    subtitle: createdAt != null ? Text(DateFormatter.formatDateTime(createdAt)) : null,
                    trailing: IconButton(
                      icon: const Icon(Icons.download_outlined),
                      onPressed: () async {
                        final url = report['download_url'] as String?;
                        if (url != null && await canLaunchUrl(Uri.parse(url))) {
                          await launchUrl(Uri.parse(url));
                        }
                      },
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  void _showGenerateDialog(BuildContext context, WidgetRef ref) {
    String type = 'performance';
    String format = 'pdf';
    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Générer un rapport'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                value: type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: 'performance', child: Text('Performance')),
                  DropdownMenuItem(value: 'tax', child: Text('Fiscalité 2086')),
                  DropdownMenuItem(value: 'portfolio', child: Text('Portefeuille')),
                ],
                onChanged: (v) => setState(() => type = v ?? 'performance'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: format,
                decoration: const InputDecoration(labelText: 'Format'),
                items: const [
                  DropdownMenuItem(value: 'pdf', child: Text('PDF')),
                  DropdownMenuItem(value: 'excel', child: Text('Excel')),
                ],
                onChanged: (v) => setState(() => format = v ?? 'pdf'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
            ElevatedButton(
              onPressed: () async {
                await ref.read(dioProvider).post(ApiConstants.reports, data: {'report_type': type, 'format': format});
                ref.invalidate(_reportsProvider);
                if (ctx.mounted) {
                  Navigator.pop(ctx);
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Rapport en cours de génération...')));
                }
              },
              child: const Text('Générer'),
            ),
          ],
        ),
      ),
    );
  }
}
