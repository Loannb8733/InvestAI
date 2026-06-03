import 'package:flutter/material.dart';
import 'package:investai_mobile/core/theme/app_colors.dart';

class AppLoading extends StatelessWidget {
  final String? message;
  const AppLoading({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(color: AppColors.primary),
          if (message != null) ...[
            const SizedBox(height: 16),
            Text(message!, style: const TextStyle(color: AppColors.textSecondary)),
          ],
        ],
      ),
    );
  }
}

class AppLoadingOverlay extends StatelessWidget {
  final Widget child;
  final bool isLoading;
  const AppLoadingOverlay({super.key, required this.child, required this.isLoading});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        child,
        if (isLoading)
          Container(
            color: Colors.black45,
            child: const AppLoading(),
          ),
      ],
    );
  }
}
