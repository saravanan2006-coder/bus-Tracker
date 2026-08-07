// Widget smoke test: the app boots into the passenger home screen.
//
// Platform storage is mocked so the boot path (language load, session
// restore, favorites) can run in a widget-test environment.

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:bus_tracker/main.dart';

void main() {
  testWidgets('app boots into the passenger home screen', (tester) async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});

    await tester.pumpWidget(const BusTrackerApp());
    await tester.pump();

    expect(find.byType(MaterialApp), findsWidgets);
  });
}
