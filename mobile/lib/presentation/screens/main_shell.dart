import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:investai_mobile/core/router/route_names.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';
import 'package:investai_mobile/providers/core/scaffold_key_provider.dart';

class MainShell extends ConsumerWidget {
  final Widget child;
  const MainShell({super.key, required this.child});

  static const _tabs = [
    _TabItem(icon: Icons.dashboard_outlined, activeIcon: Icons.dashboard, label: 'Dashboard', route: RouteNames.dashboard),
    _TabItem(icon: Icons.account_balance_wallet_outlined, activeIcon: Icons.account_balance_wallet, label: 'Portefeuille', route: RouteNames.portfolio),
    _TabItem(icon: Icons.swap_horiz_outlined, activeIcon: Icons.swap_horiz, label: 'Transactions', route: RouteNames.transactions),
    _TabItem(icon: Icons.bar_chart_outlined, activeIcon: Icons.bar_chart, label: 'Analytics', route: RouteNames.analytics),
    _TabItem(icon: Icons.more_horiz, activeIcon: Icons.more_horiz, label: 'Plus', route: ''),
  ];

  int _currentIndex(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    if (location.startsWith(RouteNames.dashboard)) return 0;
    if (location.startsWith(RouteNames.portfolio)) return 1;
    if (location.startsWith(RouteNames.transactions)) return 2;
    if (location.startsWith(RouteNames.analytics)) return 3;
    return 4;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentIndex = _currentIndex(context);
    final user = ref.watch(authProvider).user;

    return Scaffold(
      body: Builder(
        builder: (ctx) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            ref.read(drawerOpenerProvider.notifier).state =
                () => Scaffold.of(ctx).openDrawer();
          });
          return child;
        },
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: currentIndex > 3 ? 3 : currentIndex,
        items: _tabs.take(4).map((t) => BottomNavigationBarItem(
          icon: Icon(t.icon),
          activeIcon: Icon(t.activeIcon),
          label: t.label,
        )).toList(),
        onTap: (i) {
          switch (i) {
            case 0: context.go(RouteNames.dashboard);
            case 1: context.go(RouteNames.portfolio);
            case 2: context.go(RouteNames.transactions);
            case 3: context.go(RouteNames.analytics);
          }
        },
      ),
      drawer: AppDrawer(user: user),
    );
  }
}

class _TabItem {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  final String route;
  const _TabItem({required this.icon, required this.activeIcon, required this.label, required this.route});
}

class AppDrawer extends ConsumerWidget {
  final dynamic user;
  const AppDrawer({super.key, this.user});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Drawer(
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(color: AppColors.primary),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                const CircleAvatar(
                  radius: 24,
                  backgroundColor: Colors.white24,
                  child: Icon(Icons.person, color: Colors.white),
                ),
                const SizedBox(height: 8),
                Text(
                  user?.displayName ?? 'InvestAI',
                  style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                ),
                Text(
                  user?.email ?? '',
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ),
          _DrawerItem(icon: Icons.dashboard, label: 'Dashboard', route: RouteNames.dashboard),
          _DrawerItem(icon: Icons.account_balance_wallet, label: 'Portefeuille', route: RouteNames.portfolio),
          _DrawerItem(icon: Icons.swap_horiz, label: 'Transactions', route: RouteNames.transactions),
          _DrawerItem(icon: Icons.bar_chart, label: 'Analytics', route: RouteNames.analytics),
          _DrawerItem(icon: Icons.psychology, label: 'Intelligence IA', route: RouteNames.intelligence),
          _DrawerItem(icon: Icons.account_tree, label: 'Stratégie', route: RouteNames.strategy),
          _DrawerItem(icon: Icons.description, label: 'Rapports', route: RouteNames.reports),
          _DrawerItem(icon: Icons.notifications, label: 'Alertes', route: RouteNames.alerts),
          _DrawerItem(icon: Icons.note, label: 'Notes', route: RouteNames.notes),
          _DrawerItem(icon: Icons.calendar_today, label: 'Calendrier', route: RouteNames.calendar),
          _DrawerItem(icon: Icons.business, label: 'Crowdfunding', route: RouteNames.crowdfunding),
          _DrawerItem(icon: Icons.calculate, label: 'Simulations', route: RouteNames.simulations),
          if (user?.isAdmin == true)
            _DrawerItem(icon: Icons.admin_panel_settings, label: 'Administration', route: RouteNames.admin),
          const Divider(),
          _DrawerItem(icon: Icons.settings, label: 'Paramètres', route: RouteNames.settings),
          ListTile(
            leading: const Icon(Icons.logout, color: AppColors.error),
            title: const Text('Déconnexion', style: TextStyle(color: AppColors.error)),
            onTap: () {
              Navigator.pop(context);
              ref.read(authProvider.notifier).logout();
            },
          ),
        ],
      ),
    );
  }
}

class _DrawerItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String route;
  const _DrawerItem({required this.icon, required this.label, required this.route});

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    final isActive = location.startsWith(route) && route.isNotEmpty;

    return ListTile(
      leading: Icon(icon, color: isActive ? AppColors.primary : null),
      title: Text(label, style: TextStyle(color: isActive ? AppColors.primary : null, fontWeight: isActive ? FontWeight.w600 : null)),
      selected: isActive,
      onTap: () {
        Navigator.pop(context);
        if (route.isNotEmpty) context.go(route);
      },
    );
  }
}

class DrawerMenuButton extends ConsumerWidget {
  const DrawerMenuButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return IconButton(
      icon: const Icon(Icons.menu),
      onPressed: () => ref.read(drawerOpenerProvider)?.call(),
    );
  }
}
