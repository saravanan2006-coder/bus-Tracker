import 'package:flutter/foundation.dart';

import '../storage/app_storage.dart';
import 'app_strings.dart';

/// Loads the user's language preference and provides translated strings.
///
/// Tamil is the default (the app is Tamil-first, with an English toggle).
class LocalizationController extends ChangeNotifier {
  LocalizationController() : _language = 'ta';

  String _language;

  String get language => _language;

  Future<void> load() async {
    _language = await AppStorage.language;
    notifyListeners();
  }

  Future<void> setLanguage(String value) async {
    if (value == _language) return;
    _language = value;
    await AppStorage.setLanguage(value);
    notifyListeners();
  }

  void toggle() => setLanguage(_language == 'ta' ? 'en' : 'ta');

  String t(String key, {Map<String, String>? args}) =>
      AppStrings.resolve(_language, key, args: args);
}
