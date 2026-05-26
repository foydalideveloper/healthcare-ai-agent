/**
 * Healthcare AI Glasses - Companion App
 * Triple-H Co., Ltd. | Patent No. 10-2025-0145274
 *
 * This app connects to AI glasses (Meta Ray-Ban Gen 2 / Mentra Live),
 * runs food recognition ML on phone, and uploads health data to Supabase.
 */

import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';

function App() {
  return (
    <SafeAreaProvider>
      <HomeScreen />
    </SafeAreaProvider>
  );
}

export default App;
