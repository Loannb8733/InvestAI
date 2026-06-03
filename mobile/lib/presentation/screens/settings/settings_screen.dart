import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/constants/app_constants.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/validators.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';
import 'package:investai_mobile/presentation/screens/main_shell.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late TextEditingController _firstNameCtrl;
  late TextEditingController _lastNameCtrl;
  String? _selectedCurrency;
  bool _isSavingProfile = false;
  bool _isSavingPwd = false;
  final _currentPwdCtrl = TextEditingController();
  final _newPwdCtrl = TextEditingController();
  final _confirmPwdCtrl = TextEditingController();
  final _pwdFormKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    final user = ref.read(authProvider).user;
    _firstNameCtrl = TextEditingController(text: user?.firstName);
    _lastNameCtrl = TextEditingController(text: user?.lastName);
    _selectedCurrency = user?.preferredCurrency ?? 'EUR';
  }

  @override
  void dispose() {
    _firstNameCtrl.dispose();
    _lastNameCtrl.dispose();
    _currentPwdCtrl.dispose();
    _newPwdCtrl.dispose();
    _confirmPwdCtrl.dispose();
    super.dispose();
  }

  Future<void> _saveProfile() async {
    setState(() => _isSavingProfile = true);
    try {
      await ref.read(authRepositoryProvider).updateProfile(
        firstName: _firstNameCtrl.text.trim().isEmpty ? null : _firstNameCtrl.text.trim(),
        lastName: _lastNameCtrl.text.trim().isEmpty ? null : _lastNameCtrl.text.trim(),
        preferredCurrency: _selectedCurrency,
      );
      await ref.read(authProvider.notifier).refreshUser();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Profil mis à jour'), backgroundColor: AppColors.success));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()), backgroundColor: AppColors.error));
    } finally {
      if (mounted) setState(() => _isSavingProfile = false);
    }
  }

  Future<void> _changePassword() async {
    if (!_pwdFormKey.currentState!.validate()) return;
    setState(() => _isSavingPwd = true);
    try {
      await ref.read(authRepositoryProvider).changePassword(_currentPwdCtrl.text, _newPwdCtrl.text);
      _currentPwdCtrl.clear();
      _newPwdCtrl.clear();
      _confirmPwdCtrl.clear();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Mot de passe modifié'), backgroundColor: AppColors.success));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()), backgroundColor: AppColors.error));
    } finally {
      if (mounted) setState(() => _isSavingPwd = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider).user;

    return Scaffold(
      appBar: AppBar(leading: const DrawerMenuButton(), title: const Text('Paramètres')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Profile section
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(children: [Icon(Icons.person_outline), SizedBox(width: 8), Text('Profil', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600))]),
                  const SizedBox(height: 16),
                  TextField(
                    enabled: false,
                    decoration: InputDecoration(labelText: 'Email', hintText: user?.email),
                    controller: TextEditingController(text: user?.email),
                  ),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(child: TextField(controller: _firstNameCtrl, decoration: const InputDecoration(labelText: 'Prénom'))),
                    const SizedBox(width: 12),
                    Expanded(child: TextField(controller: _lastNameCtrl, decoration: const InputDecoration(labelText: 'Nom'))),
                  ]),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    value: _selectedCurrency,
                    decoration: const InputDecoration(labelText: 'Devise préférée'),
                    items: AppConstants.supportedCurrencies.map((c) => DropdownMenuItem(value: c, child: Text('$c (${AppConstants.currencySymbols[c] ?? c})'))).toList(),
                    onChanged: (v) => setState(() => _selectedCurrency = v),
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _isSavingProfile ? null : _saveProfile,
                    child: _isSavingProfile ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('Enregistrer'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Password section
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: _pwdFormKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(children: [Icon(Icons.lock_outline), SizedBox(width: 8), Text('Sécurité', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600))]),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _currentPwdCtrl,
                      obscureText: true,
                      decoration: const InputDecoration(labelText: 'Mot de passe actuel'),
                      validator: (v) => v?.isEmpty == true ? 'Requis' : null,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _newPwdCtrl,
                      obscureText: true,
                      decoration: const InputDecoration(labelText: 'Nouveau mot de passe'),
                      validator: Validators.password,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _confirmPwdCtrl,
                      obscureText: true,
                      decoration: const InputDecoration(labelText: 'Confirmer'),
                      validator: (v) => v != _newPwdCtrl.text ? 'Ne correspond pas' : null,
                    ),
                    const SizedBox(height: 16),
                    ElevatedButton(
                      onPressed: _isSavingPwd ? null : _changePassword,
                      child: _isSavingPwd ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('Changer le mot de passe'),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Logout
          Card(
            child: ListTile(
              leading: const Icon(Icons.logout, color: AppColors.error),
              title: const Text('Déconnexion', style: TextStyle(color: AppColors.error)),
              onTap: () => ref.read(authProvider.notifier).logout(),
            ),
          ),
          const SizedBox(height: 80),
        ],
      ),
    );
  }
}
