import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../controllers/auth_controller.dart';
import 'otp_screen.dart';

/// Step 1 of driver login: enter the mobile number, receive an OTP.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phoneController = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _sendOtp() async {
    final loc = context.read<LocalizationController>();
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('driverPhoneHint'))),
      );
      return;
    }
    setState(() => _submitting = true);
    final auth = context.read<AuthController>();
    final ok = await auth.requestOtp(phone);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('error'))),
      );
      return;
    }
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => OtpScreen(phone: phone)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();

    return Scaffold(
      appBar: AppBar(title: Text(loc.t('driverLogin'))),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 24),
              Icon(
                Icons.directions_bus,
                size: 64,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: 16),
              Text(
                loc.t('driverPhoneHint'),
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _phoneController,
                keyboardType: TextInputType.phone,
                autofocus: true,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(13),
                ],
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.phone_android),
                  hintText: '+91 98765 43210',
                ),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _submitting ? null : _sendOtp,
                child: _submitting
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(loc.t('sendOtp')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
