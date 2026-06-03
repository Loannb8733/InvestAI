import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/api_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/date_formatter.dart';
import 'package:investai_mobile/providers/core/dio_provider.dart';
import 'package:investai_mobile/presentation/widgets/common/app_loading.dart';
import 'package:investai_mobile/presentation/widgets/common/app_error_widget.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

final _adminStatsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.adminStats);
  return r.data as Map<String, dynamic>;
});

final _adminUsersProvider = FutureProvider<List<dynamic>>((ref) async {
  final dio = ref.watch(dioProvider);
  final r = await dio.get(ApiConstants.adminUsers);
  return r.data as List<dynamic>;
});

class AdminScreen extends ConsumerStatefulWidget {
  const AdminScreen({super.key});

  @override
  ConsumerState<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends ConsumerState<AdminScreen> with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const DrawerMenuButton(),
        title: const Text('Administration'),
        bottom: TabBar(
          controller: _tabCtrl,
          tabs: const [Tab(text: 'Statistiques'), Tab(text: 'Utilisateurs')],
        ),
      ),
      body: TabBarView(
        controller: _tabCtrl,
        children: [_StatsTab(), _UsersTab()],
      ),
    );
  }
}

class _StatsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statsAsync = ref.watch(_adminStatsProvider);
    return statsAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString(), onRetry: () => ref.invalidate(_adminStatsProvider)),
      data: (stats) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _StatCard(label: 'Utilisateurs total', value: '${stats['total_users'] ?? 0}', icon: Icons.people),
          const SizedBox(height: 8),
          _StatCard(label: 'Utilisateurs actifs', value: '${stats['active_users'] ?? 0}', icon: Icons.person_outline),
          const SizedBox(height: 8),
          _StatCard(label: 'Portefeuilles', value: '${stats['total_portfolios'] ?? 0}', icon: Icons.account_balance_wallet),
          const SizedBox(height: 8),
          _StatCard(label: 'Transactions', value: '${stats['total_transactions'] ?? 0}', icon: Icons.swap_horiz),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  const _StatCard({required this.label, required this.value, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: AppColors.primary),
        title: Text(label, style: const TextStyle(color: AppColors.textSecondary)),
        trailing: Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
      ),
    );
  }
}

class _UsersTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usersAsync = ref.watch(_adminUsersProvider);
    return usersAsync.when(
      loading: () => const AppLoading(),
      error: (e, _) => AppErrorWidget(message: e.toString()),
      data: (users) => ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: users.length,
        itemBuilder: (_, i) {
          final user = users[i] as Map<String, dynamic>;
          final isActive = user['is_active'] as bool? ?? true;
          final role = user['role'] as String? ?? 'user';
          final createdAt = DateTime.tryParse(user['created_at'] as String? ?? '');
          return Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: role == 'admin' ? AppColors.primary.withOpacity(0.2) : AppColors.cardDark,
                child: Text(
                  (user['email'] as String? ?? 'U').substring(0, 1).toUpperCase(),
                  style: TextStyle(color: role == 'admin' ? AppColors.primary : AppColors.textSecondary),
                ),
              ),
              title: Text(user['email'] as String? ?? ''),
              subtitle: Text(
                '${role.toUpperCase()} · ${createdAt != null ? DateFormatter.formatDate(createdAt) : ''}',
                style: const TextStyle(fontSize: 12),
              ),
              trailing: Icon(isActive ? Icons.check_circle : Icons.cancel, color: isActive ? AppColors.success : AppColors.error, size: 20),
            ),
          );
        },
      ),
    );
  }
}
