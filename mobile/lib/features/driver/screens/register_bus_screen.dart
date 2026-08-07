import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../controllers/driver_controller.dart';

/// Form to register a new bus for admin verification.
class RegisterBusScreen extends StatefulWidget {
  const RegisterBusScreen({super.key});

  @override
  State<RegisterBusScreen> createState() => _RegisterBusScreenState();
}

class _RegisterBusScreenState extends State<RegisterBusScreen> {
  final _numberController = TextEditingController();
  final _nameController = TextEditingController();
  final _rtoController = TextEditingController();
  String _busType = 'govt';
  bool _submitting = false;

  @override
  void dispose() {
    _numberController.dispose();
    _nameController.dispose();
    _rtoController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final loc = context.read<LocalizationController>();
    final number = _numberController.text.trim();
    final rto = _rtoController.text.trim();
    if (number.isEmpty || rto.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('busNumber'))),
      );
      return;
    }
    setState(() => _submitting = true);
    final controller = context.read<DriverController>();
    final ok = await controller.registerBus(
      busNumber: number,
      rtoNumber: rto,
      busType: _busType,
      busName: _nameController.text.trim().isEmpty
          ? null
          : _nameController.text.trim(),
    );
    if (!mounted) return;
    setState(() => _submitting = false);
    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('busRegistered'))),
      );
      Navigator.of(context).pop();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(controller.error ?? loc.t('error'))),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();

    return Scaffold(
      appBar: AppBar(title: Text(loc.t('addBus'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            TextField(
              controller: _numberController,
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                labelText: loc.t('busNumber'),
                prefixIcon: const Icon(Icons.numbers),
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _nameController,
              decoration: InputDecoration(
                labelText: loc.t('busName'),
                prefixIcon: const Icon(Icons.badge_outlined),
              ),
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: _busType,
              decoration: InputDecoration(
                labelText: loc.t('busType'),
                prefixIcon: const Icon(Icons.category_outlined),
              ),
              items: [
                DropdownMenuItem(value: 'govt', child: Text(loc.t('govt'))),
                DropdownMenuItem(value: 'private', child: Text(loc.t('private'))),
              ],
              onChanged: (v) => setState(() => _busType = v ?? 'govt'),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _rtoController,
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                labelText: loc.t('rtoNumber'),
                prefixIcon: const Icon(Icons.confirmation_number_outlined),
              ),
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(loc.t('register')),
            ),
          ],
        ),
      ),
    );
  }
}
