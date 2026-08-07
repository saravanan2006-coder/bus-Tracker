import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../controllers/auth_controller.dart';
import 'driver_home_screen.dart';

/// Step 2 of driver login: verify the OTP. Pops the whole login stack on
/// success and lands on the driver home screen.
class OtpScreen extends StatefulWidget {
  const OtpScreen({super.key, required this.phone});

  final String phone;

  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends State<OtpScreen> {
  final _otpController = TextEditingController();
  bool _verifying = false;
  String? _error;
  int _resendIn = 30;

  @override
  void initState() {
    super.initState();
    _startResendCountdown();
  }

  void _startResendCountdown() {
    _resendIn = 30;
    Future.doWhile(() async {
      if (!mounted) return false;
      await Future.delayed(const Duration(seconds: 1));
      if (!mounted) return false;
      setState(() => _resendIn--);
      return _resendIn > 0;
    });
  }

  Future<void> _verify() async {
    final loc = context.read<LocalizationController>();
    final otp = _otpController.text.trim();
    if (otp.length < 4) return;
    setState(() {
      _verifying = true;
      _error = null;
    });
    final auth = context.read<AuthController>();
    final ok = await auth.verifyOtp(widget.phone, otp);
    if (!mounted) return;
    setState(() => _verifying = false);
    if (!ok) {
      setState(() => _error = loc.t('wrongOtp'));
      return;
    }
    // Clear the login stack so back never returns to the OTP screen.
    unawaited(
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const DriverHomeScreen()),
        (route) => false,
      ),
    );
  }

  Future<void> _resend() async {
    if (_resendIn > 0) return;
    await context.read<AuthController>().requestOtp(widget.phone);
    _startResendCountdown();
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();

    return Scaffold(
      appBar: AppBar(title: Text(loc.t('verify'))),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 16),
              Text(
                loc.t('otpSent', args: {'phone': widget.phone}),
                style: const TextStyle(fontSize: 16),
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _otpController,
                keyboardType: TextInputType.number,
                autofocus: true,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 24, letterSpacing: 8, fontWeight: FontWeight.w700),
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(6),
                ],
                onSubmitted: (_) => _verify(),
                decoration: InputDecoration(
                  hintText: '••••••',
                  errorText: _error,
                ),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _verifying ? null : _verify,
                child: _verifying
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(loc.t('verify')),
              ),
              const SizedBox(height: 16),
              Center(
                child: TextButton(
                  onPressed: _resendIn > 0 ? null : _resend,
                  child: Text(
                    _resendIn > 0
                        ? '${loc.t('resendOtp')} ($_resendIn)'
                        : loc.t('resendOtp'),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
