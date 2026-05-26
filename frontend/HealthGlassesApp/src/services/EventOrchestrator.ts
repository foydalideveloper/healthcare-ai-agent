/**
 * Event Orchestrator
 * The main controller that ties everything together:
 *   Glasses → ML Pipeline → Supabase Upload → User Notification
 *
 * This is the brain of the companion app.
 */

import { glassesService, GlassesFrame } from './GlassesConnection';
import { mlPipeline, PipelineResult } from './MLPipeline';
import { supabaseUploader } from './SupabaseUploader';

export interface ProcessedEvent {
  eventId: number | null;
  result: PipelineResult;
  uploadSuccess: boolean;
  thumbnailUrl: string | null;
  timestamp: string;
}

type EventCallback = (event: ProcessedEvent) => void;

class EventOrchestrator {
  private userId: string | null = null;
  private eventCallbacks: EventCallback[] = [];
  private todayEvents: ProcessedEvent[] = [];
  private isProcessing = false;

  /**
   * Start the orchestrator
   * 1. Initialize ML models
   * 2. Connect to glasses
   * 3. Listen for incoming frames
   */
  async start(userId: string, glassesProvider: 'meta_rayban' | 'mentra_live' | 'simulator' = 'simulator'): Promise<void> {
    this.userId = userId;

    console.log('[Orchestrator] Starting...');

    // Initialize ML pipeline (loads TFLite models)
    await mlPipeline.initialize();
    console.log('[Orchestrator] ML models loaded');

    // Connect to glasses
    const connected = await glassesService.connect(glassesProvider);
    if (!connected) {
      throw new Error('Failed to connect to glasses');
    }
    console.log(`[Orchestrator] Connected to glasses (${glassesProvider})`);

    // Register frame handler
    glassesService.onFrame(async (frame) => {
      await this.handleFrame(frame);
    });

    console.log('[Orchestrator] Ready - waiting for glasses events');
  }

  /**
   * Register callback for processed events (for UI updates)
   */
  onEvent(callback: EventCallback): void {
    this.eventCallbacks.push(callback);
  }

  /**
   * Handle an incoming frame from glasses
   * This is the main processing loop
   */
  private async handleFrame(frame: GlassesFrame): Promise<void> {
    if (this.isProcessing) {
      console.log('[Orchestrator] Already processing, skipping frame');
      return;
    }
    if (!this.userId) {
      console.log('[Orchestrator] No user ID set');
      return;
    }

    this.isProcessing = true;
    console.log(`[Orchestrator] Processing frame (trigger: ${frame.triggerType})`);

    try {
      // Stage 4: Run ML pipeline on phone
      const result = await mlPipeline.processFrame(
        frame.imageData,
        frame.audioData,
      );

      // Stage 5: Upload to Supabase
      const uploadResult = await supabaseUploader.uploadEvent(
        this.userId,
        result,
        frame.deviceInfo.provider === 'meta_rayban' ? 'meta_rayban_gen2' : frame.deviceInfo.provider,
      );

      // Upload thumbnail if event was created
      let thumbnailUrl: string | null = null;
      if (uploadResult.success && uploadResult.eventId && result.thumbnailBase64) {
        thumbnailUrl = await supabaseUploader.uploadThumbnail(
          this.userId,
          uploadResult.eventId,
          result.thumbnailBase64,
        );
      }

      // Build processed event
      const processedEvent: ProcessedEvent = {
        eventId: uploadResult.eventId ?? null,
        result,
        uploadSuccess: uploadResult.success,
        thumbnailUrl,
        timestamp: frame.timestamp,
      };

      this.todayEvents.push(processedEvent);

      // Notify UI
      for (const cb of this.eventCallbacks) {
        cb(processedEvent);
      }

      // Log
      const food = result.foodDetections[0]?.foodName ?? 'unknown';
      const cal = result.totalCalories;
      console.log(
        `[Orchestrator] Event processed: ${food} (${cal} kcal) | ` +
        `confidence=${result.confidenceScore} | uploaded=${uploadResult.success} | ` +
        `eventId=${uploadResult.eventId}`
      );

      // If low confidence, mark for cloud review
      if (result.needsCloudReview) {
        console.log('[Orchestrator] Low confidence - needs user confirmation');
      }

    } catch (err) {
      console.error('[Orchestrator] Frame processing error:', err);
    } finally {
      this.isProcessing = false;
    }
  }

  /**
   * Get today's nutrition summary
   */
  async getDailySummary() {
    if (!this.userId) return null;
    return supabaseUploader.getDailySummary(this.userId);
  }

  /**
   * Submit user correction for a food detection
   */
  async correctEvent(eventId: number, correctedFood: string, correctedCalories: number): Promise<boolean> {
    return supabaseUploader.submitCorrection(eventId, correctedFood, correctedCalories);
  }

  /**
   * Save daily lifestyle aggregation to Supabase
   */
  async saveDailyAggregation(): Promise<boolean> {
    if (!this.userId) return false;
    const summary = await supabaseUploader.getDailySummary(this.userId);
    return supabaseUploader.uploadDailyLifestyle(this.userId, summary);
  }

  /**
   * Get today's processed events (local cache)
   */
  getTodayEvents(): ProcessedEvent[] {
    return [...this.todayEvents];
  }

  /**
   * Get system status
   */
  getStatus() {
    return {
      userId: this.userId,
      glassesConnected: glassesService.getState().isConnected,
      glassesProvider: glassesService.getState().provider,
      glassesBattery: glassesService.getState().batteryPercent,
      modelsLoaded: mlPipeline.getModelStatus(),
      todayEventCount: this.todayEvents.length,
      isProcessing: this.isProcessing,
    };
  }

  /**
   * Stop the orchestrator
   */
  stop(): void {
    glassesService.disconnect();
    this.userId = null;
    this.todayEvents = [];
    console.log('[Orchestrator] Stopped');
  }
}

export const orchestrator = new EventOrchestrator();
