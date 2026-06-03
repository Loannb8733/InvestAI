import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';
import 'package:investai_mobile/core/utils/validators.dart';
import 'package:investai_mobile/providers/auth/auth_provider.dart';

class MfaScreen extends ConsumerStatefulWidget {
  final String tempToken;
  const MfaScreen({super.key, required this.tempToken});

  @override
  ConsumerState<MfaScreen> createState() => _MfaScreenState();
}

class _MfaScreenState extends ConsumerState<MfaScreen> {
  final _codeCtrl = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _codeCtrl.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final code = _codeCtrl.text.trim();
    final error = Validators.mfaCode(code);
    if (error != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error), backgroundColor: AppColors.error),
      );
      return;
    }

    setState(() => _isLoading = true);
    try {
      await ref.read(authProvider.notifier).verifyMFA(widget.tempToken, code);
    } catch (e) {
      if (!mounted) return;
      _codeCtrl.clear();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), backgroundColor: AppColors.error),
      );
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Authentification à deux facteurs')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.security, size: 72, color: AppColors.primary),
              const SizedBox(height: 24),
              const Text(
                'Code MFA requis',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              const Text(
                'Entrez le code à 6 chiffres généré par votre application d\'authentification (Google Authenticator, Authy…)',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary),
              ),
              const SizedBox(height: 40),
              TextFormField(
                controller: _codeCtrl,
                keyboardType: TextInputType.number,
                maxLength: 6,
                textAlign: TextAlign.center,
                autofocus: true,
                style: const TextStyle(fontSize: 28, letterSpacing: 10, fontWeight: FontWeight.bold),
                decoration: const InputDecoration(
                  counterText: '',
                  hintText: '000000',
                  hintStyle: TextStyle(letterSpacing: 8, color: AppColors.textMuted),
                ),
                onChanged: (v) {
                  if (v.length == 6) _verify();
                },
              ),
              const SizedBox(height: 32),
              ElevatedButton(
                onPressed: _isLoading ? null : _verify,
                child: _isLoading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('Vérifier'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
