import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/widgets/common/app_empty_state.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _notesProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.notes);
  return r.data as List<dynamic>;
});

class NotesScreen extends ConsumerWidget {
  const NotesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notesAsync = ref.watch(_notesProvider);

    return Scaffold(
      appBar: AppBar(leading: const DrawerMenuButton(), title: const Text('Journal')),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showEditor(context, ref),
        child: const Icon(Icons.add),
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(_notesProvider),
        child: notesAsync.when(
          loading: () => const AppLoading(),
          error: (e, _) => AppErrorWidget(message: e.toString(), onRetry: () => ref.invalidate(_notesProvider)),
          data: (notes) {
            if (notes.isEmpty) {
              return const AppEmptyState(
                message: 'Aucune note',
                description: 'Gardez une trace de vos décisions d\'investissement',
                icon: Icons.note_outlined,
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: notes.length,
              itemBuilder: (_, i) {
                final note = notes[i] as Map<String, dynamic>;
                final tags = (note['tags'] as List<dynamic>?)?.cast<String>() ?? [];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: InkWell(
                    onTap: () => _showEditor(context, ref, note: note),
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(child: Text(note['title'] as String? ?? '', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16), overflow: TextOverflow.ellipsis)),
                              Text(DateFormatter.formatRelative(DateTime.tryParse(note['updated_at'] as String? ?? '') ?? DateTime.now()),
                                  style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(note['content'] as String? ?? '', style: const TextStyle(color: AppColors.textSecondary), maxLines: 2, overflow: TextOverflow.ellipsis),
                          if (tags.isNotEmpty) ...[
                            const SizedBox(height: 8),
                            Wrap(spacing: 4, children: tags.map((t) => Chip(label: Text(t, style: const TextStyle(fontSize: 10)), padding: EdgeInsets.zero, visualDensity: VisualDensity.compact)).toList()),
                          ],
                        ],
                      ),
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

  void _showEditor(BuildContext context, WidgetRef ref, {Map<String, dynamic>? note}) {
    final titleCtrl = TextEditingController(text: note?['title'] as String?);
    final contentCtrl = TextEditingController(text: note?['content'] as String?);
    final isEdit = note != null;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: Container(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: titleCtrl, decoration: const InputDecoration(labelText: 'Titre'), autofocus: true),
              const SizedBox(height: 12),
              TextField(controller: contentCtrl, decoration: const InputDecoration(labelText: 'Contenu'), maxLines: 5),
              const SizedBox(height: 16),
              Row(
                children: [
                  if (isEdit) TextButton(
                    style: TextButton.styleFrom(foregroundColor: AppColors.error),
                    onPressed: () async {
                      await ref.read(dioProvider).delete('${ApiConstants.notes}/${note['id']}');
                      ref.invalidate(_notesProvider);
                      if (ctx.mounted) Navigator.pop(ctx);
                    },
                    child: const Text('Supprimer'),
                  ),
                  const Spacer(),
                  TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: () async {
                      if (isEdit) {
                        await ref.read(dioProvider).put('${ApiConstants.notes}/${note['id']}', data: {'title': titleCtrl.text, 'content': contentCtrl.text});
                      } else {
                        await ref.read(dioProvider).post(ApiConstants.notes, data: {'title': titleCtrl.text, 'content': contentCtrl.text, 'tags': []});
                      }
                      ref.invalidate(_notesProvider);
                      if (ctx.mounted) Navigator.pop(ctx);
                    },
                    child: Text(isEdit ? 'Modifier' : 'Créer'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
