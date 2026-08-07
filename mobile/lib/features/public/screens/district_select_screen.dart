import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/geo/detector.dart';
import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../shared_widgets/error_view.dart';
import '../../../shared_widgets/loading_indicator.dart';
import '../controllers/public_controller.dart';

/// Step 1 of the passenger flow: pick a district (auto-detect or manual).
class DistrictSelectScreen extends StatefulWidget {
  const DistrictSelectScreen({super.key, this.onSelected});

  final ValueChanged<District>? onSelected;

  @override
  State<DistrictSelectScreen> createState() => _DistrictSelectScreenState();
}

class _DistrictSelectScreenState extends State<DistrictSelectScreen> {
  bool _detecting = false;
  String? _detectMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final controller = context.read<PublicController>();
      if (controller.districts.isEmpty) controller.loadDistricts();
    });
  }

  Future<void> _autoDetect() async {
    final loc = context.read<LocalizationController>();
    setState(() {
      _detecting = true;
      _detectMessage = null;
    });
    final name = await DistrictDetector.detectDistrict();
    if (!mounted) return;
    final controller = context.read<PublicController>();
    setState(() {
      _detecting = false;
    });
    if (name == null) {
      setState(() => _detectMessage = loc.t('detectFailed'));
      return;
    }
    final match = controller.districts
        .where((d) => d.name.toLowerCase() == name.toLowerCase())
        .firstOrNull;
    if (match == null) {
      setState(() => _detectMessage = loc.t('detectFailed'));
      return;
    }
    controller.selectDistrict(match);
    widget.onSelected?.call(match);
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<PublicController>();

    return Scaffold(
      appBar: AppBar(title: Text(loc.t('selectDistrict'))),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: OutlinedButton.icon(
                onPressed: _detecting ? null : _autoDetect,
                icon: _detecting
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.my_location),
                label: Text(loc.t('autoDetect')),
              ),
            ),
            if (_detectMessage != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  _detectMessage!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            Expanded(
              child: controller.loadingDistricts
                  ? const LoadingIndicator()
                  : controller.error != null
                      ? ErrorView(
                          message: loc.t('error'),
                          onRetry: controller.loadDistricts,
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.all(16),
                          itemCount: controller.districts.length,
                          itemBuilder: (context, index) {
                            final district = controller.districts[index];
                            return Card(
                              margin: const EdgeInsets.only(bottom: 10),
                              child: ListTile(
                                title: Text(
                                  loc.language == 'ta' &&
                                          district.nameTa != null
                                      ? district.nameTa!
                                      : district.name,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w700),
                                ),
                                subtitle: Text(
                                  '${district.talukCount} taluks · '
                                  '${district.villageCount} villages',
                                ),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () {
                                  controller.selectDistrict(district);
                                  widget.onSelected?.call(district);
                                },
                              ),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }
}
