/**
 * Home Screen — Main dashboard for glasses testing
 * Shows: connection status, today's events, daily nutrition summary
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  Alert, RefreshControl, StatusBar,
} from 'react-native';
import { orchestrator, ProcessedEvent } from '../services/EventOrchestrator';
import { glassesService } from '../services/GlassesConnection';

const HomeScreen: React.FC = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<ProcessedEvent[]>([]);
  const [dailySummary, setDailySummary] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<any>(null);

  // Refresh daily summary
  const refreshSummary = useCallback(async () => {
    setIsLoading(true);
    try {
      const summary = await orchestrator.getDailySummary();
      setDailySummary(summary);
      setEvents(orchestrator.getTodayEvents());
      setStatus(orchestrator.getStatus());
    } catch (err) {
      console.log('Refresh error:', err);
    }
    setIsLoading(false);
  }, []);

  // Connect to glasses
  const connectGlasses = async (provider: 'meta_rayban' | 'simulator') => {
    try {
      // TODO: Replace with actual user ID from login
      const testUserId = 'test-user-glasses-001';
      await orchestrator.start(testUserId, provider);

      // Listen for new events
      orchestrator.onEvent((event) => {
        setEvents(prev => [event, ...prev]);
        refreshSummary();

        // Show notification for food detection
        if (event.result.foodDetections.length > 0) {
          const food = event.result.foodDetections[0];
          const cal = event.result.totalCalories;
          if (event.result.needsCloudReview) {
            Alert.alert(
              'Food Detected (Low Confidence)',
              `${food.foodName}? (${cal} kcal)\nIs this correct?`,
              [
                { text: 'Correct', onPress: () => handleCorrection(event) },
                { text: 'Yes', style: 'cancel' },
              ]
            );
          } else {
            Alert.alert('Food Detected', `${food.foodName} — ${cal} kcal`);
          }
        }
      });

      setIsConnected(true);
      refreshSummary();
    } catch (err) {
      Alert.alert('Connection Error', String(err));
    }
  };

  // Handle user correction
  const handleCorrection = async (event: ProcessedEvent) => {
    // TODO: Show food search/correction UI
    // For now, just mark as needing correction
    if (event.eventId) {
      Alert.prompt?.(
        'Correct Food',
        'What food is this?',
        async (correctedFood: string) => {
          await orchestrator.correctEvent(event.eventId!, correctedFood, 0);
        }
      );
    }
  };

  // Manual capture trigger (simulates glasses button tap)
  const triggerCapture = async () => {
    if (!isConnected) {
      Alert.alert('Not Connected', 'Connect to glasses first');
      return;
    }

    // In simulator mode, inject a mock frame
    glassesService.injectFrame({
      imageData: '', // Empty for mock
      timestamp: new Date().toISOString(),
      triggerType: 'button_tap',
      deviceInfo: {
        provider: glassesService.getState().provider,
        batteryPercent: 85,
        bleSignalStrength: -45,
      },
    });
  };

  // Save daily aggregation
  const saveDailyReport = async () => {
    const success = await orchestrator.saveDailyAggregation();
    Alert.alert(
      success ? 'Saved' : 'Error',
      success ? 'Daily nutrition saved to Supabase' : 'Failed to save'
    );
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#1B5E20" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Healthcare AI Glasses</Text>
        <Text style={styles.headerSubtitle}>Triple-H Co., Ltd.</Text>
      </View>

      <ScrollView
        style={styles.content}
        refreshControl={
          <RefreshControl refreshing={isLoading} onRefresh={refreshSummary} />
        }
      >
        {/* Connection Status */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Glasses Connection</Text>
          <View style={styles.statusRow}>
            <View style={[styles.statusDot, isConnected ? styles.statusGreen : styles.statusRed]} />
            <Text style={styles.statusText}>
              {isConnected
                ? `Connected (${status?.glassesProvider || 'unknown'})`
                : 'Not connected'}
            </Text>
          </View>
          {!isConnected && (
            <View style={styles.buttonRow}>
              <TouchableOpacity
                style={styles.button}
                onPress={() => connectGlasses('meta_rayban')}
              >
                <Text style={styles.buttonText}>Connect Meta Gen 2</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.button, styles.buttonSecondary]}
                onPress={() => connectGlasses('simulator')}
              >
                <Text style={styles.buttonTextSecondary}>Simulator Mode</Text>
              </TouchableOpacity>
            </View>
          )}
          {isConnected && (
            <TouchableOpacity style={styles.captureButton} onPress={triggerCapture}>
              <Text style={styles.captureButtonText}>Capture Food Photo</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Daily Summary */}
        {dailySummary && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Today's Nutrition</Text>
            <View style={styles.nutritionGrid}>
              <NutritionBox label="Calories" value={`${dailySummary.totalCalories}`} unit="kcal" color="#E53935" />
              <NutritionBox label="Protein" value={`${dailySummary.totalProteinG}`} unit="g" color="#1E88E5" />
              <NutritionBox label="Fat" value={`${dailySummary.totalFatG}`} unit="g" color="#FDD835" />
              <NutritionBox label="Carbs" value={`${dailySummary.totalCarbG}`} unit="g" color="#43A047" />
            </View>
            <Text style={styles.mealCount}>
              Meals: {dailySummary.mealCount} | Events: {dailySummary.totalEvents}
            </Text>
            <TouchableOpacity style={styles.saveButton} onPress={saveDailyReport}>
              <Text style={styles.saveButtonText}>Save Daily Report to Supabase</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Event Feed */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Today's Events ({events.length})</Text>
          {events.length === 0 && (
            <Text style={styles.emptyText}>No events yet. Capture food photos to start.</Text>
          )}
          {events.map((event, index) => (
            <EventCard key={index} event={event} />
          ))}
        </View>

        {/* Model Status */}
        {status && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>System Status</Text>
            <Text style={styles.statusDetail}>Models loaded: {Object.values(status.modelsLoaded || {}).filter((m: any) => m.loaded).length}/4</Text>
            <Text style={styles.statusDetail}>Events today: {status.todayEventCount}</Text>
            <Text style={styles.statusDetail}>Processing: {status.isProcessing ? 'Yes' : 'Idle'}</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
};

// Sub-components
const NutritionBox: React.FC<{ label: string; value: string; unit: string; color: string }> = ({ label, value, unit, color }) => (
  <View style={styles.nutritionBox}>
    <Text style={[styles.nutritionValue, { color }]}>{value}</Text>
    <Text style={styles.nutritionUnit}>{unit}</Text>
    <Text style={styles.nutritionLabel}>{label}</Text>
  </View>
);

const EventCard: React.FC<{ event: ProcessedEvent }> = ({ event }) => {
  const food = event.result.foodDetections[0];
  const cal = event.result.totalCalories;
  const conf = event.result.confidenceScore;
  const time = new Date(event.timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });

  return (
    <View style={[styles.eventCard, event.result.needsCloudReview && styles.eventCardWarning]}>
      <View style={styles.eventHeader}>
        <Text style={styles.eventType}>{event.result.eventType.toUpperCase()}</Text>
        <Text style={styles.eventTime}>{time}</Text>
      </View>
      {food && (
        <>
          <Text style={styles.eventFood}>{food.foodName}</Text>
          <Text style={styles.eventDetail}>
            {cal} kcal | Confidence: {(conf * 100).toFixed(0)}% | Portion: {food.portionSize}
          </Text>
        </>
      )}
      {event.result.needsCloudReview && (
        <Text style={styles.eventWarning}>Low confidence — needs review</Text>
      )}
      <Text style={styles.eventUpload}>
        {event.uploadSuccess ? `Uploaded (ID: ${event.eventId})` : 'Upload failed'}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F5F5F5' },
  header: { backgroundColor: '#1B5E20', paddingTop: 48, paddingBottom: 16, paddingHorizontal: 20 },
  headerTitle: { color: '#fff', fontSize: 22, fontWeight: 'bold' },
  headerSubtitle: { color: '#A5D6A7', fontSize: 13, marginTop: 2 },
  content: { flex: 1, padding: 16 },
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 16, elevation: 2 },
  cardTitle: { fontSize: 16, fontWeight: '700', color: '#333', marginBottom: 12 },
  statusRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  statusDot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  statusGreen: { backgroundColor: '#4CAF50' },
  statusRed: { backgroundColor: '#F44336' },
  statusText: { fontSize: 14, color: '#666' },
  buttonRow: { flexDirection: 'row', gap: 8 },
  button: { flex: 1, backgroundColor: '#1B5E20', borderRadius: 8, padding: 12, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 13 },
  buttonSecondary: { backgroundColor: '#E8F5E9', borderWidth: 1, borderColor: '#1B5E20' },
  buttonTextSecondary: { color: '#1B5E20', fontWeight: '600', fontSize: 13 },
  captureButton: { backgroundColor: '#E53935', borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 8 },
  captureButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  nutritionGrid: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  nutritionBox: { alignItems: 'center', flex: 1 },
  nutritionValue: { fontSize: 24, fontWeight: 'bold' },
  nutritionUnit: { fontSize: 11, color: '#999' },
  nutritionLabel: { fontSize: 12, color: '#666', marginTop: 2 },
  mealCount: { textAlign: 'center', color: '#888', fontSize: 13, marginTop: 4 },
  saveButton: { backgroundColor: '#1B5E20', borderRadius: 8, padding: 10, alignItems: 'center', marginTop: 10 },
  saveButtonText: { color: '#fff', fontWeight: '600' },
  emptyText: { color: '#aaa', fontStyle: 'italic', textAlign: 'center', paddingVertical: 20 },
  eventCard: { borderLeftWidth: 3, borderLeftColor: '#4CAF50', backgroundColor: '#F9FBE7', borderRadius: 8, padding: 12, marginBottom: 8 },
  eventCardWarning: { borderLeftColor: '#FF9800', backgroundColor: '#FFF3E0' },
  eventHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  eventType: { fontSize: 11, fontWeight: '700', color: '#1B5E20' },
  eventTime: { fontSize: 11, color: '#999' },
  eventFood: { fontSize: 16, fontWeight: '600', color: '#333' },
  eventDetail: { fontSize: 12, color: '#666', marginTop: 2 },
  eventWarning: { fontSize: 11, color: '#E65100', fontWeight: '600', marginTop: 4 },
  eventUpload: { fontSize: 10, color: '#999', marginTop: 4 },
  statusDetail: { fontSize: 13, color: '#666', marginBottom: 4 },
});

export default HomeScreen;
