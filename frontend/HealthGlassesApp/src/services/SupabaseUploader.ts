/**
 * Supabase Upload Service
 * Uploads glasses pipeline results to Supabase backend
 *
 * Tables written to:
 *   - user_activity_event (individual meal/drink/medication events)
 *   - user_lifestyle (daily aggregated nutrition)
 *   - user_multimodal (if audio transcript stored)
 *
 * Storage:
 *   - thumbnails/ bucket (WebP thumbnails for every event)
 *   - clips/ bucket (full photos only when confidence < 0.7)
 */

import { PipelineResult } from './MLPipeline';

const SUPABASE_URL = 'https://oqotdxlmdgjieukyzegj.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xb3RkeGxtZGdqaWV1a3l6ZWdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwNTY4MDYsImV4cCI6MjA5MTYzMjgwNn0.p2X5MKiGAalnQ0trit7nP7obEQzIcvoG4Ubu1X_kQFw';

interface UploadResult {
  success: boolean;
  eventId?: number;
  error?: string;
}

interface DailySummary {
  date: string;
  mealCount: number;
  totalEvents: number;
  totalCalories: number;
  totalProteinG: number;
  totalFatG: number;
  totalCarbG: number;
  totalSodiumMg: number;
}

class SupabaseUploaderService {
  private headers: Record<string, string>;

  constructor() {
    this.headers = {
      'apikey': SUPABASE_ANON_KEY,
      'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
      'Content-Type': 'application/json',
      'Prefer': 'return=representation',
    };
  }

  /**
   * Upload a pipeline result as an activity event
   */
  async uploadEvent(
    userId: string,
    result: PipelineResult,
    sourceDevice: string = 'meta_rayban_gen2',
  ): Promise<UploadResult> {
    const payload = {
      user_id: userId,
      event_type: result.eventType,
      source_device: sourceDevice,
      confidence_score: result.confidenceScore,
      structured_data: {
        food_items: result.foodDetections.map(d => ({
          name: d.foodName,
          confidence: d.confidence,
          portion: d.portionSize,
          portion_multiplier: d.portionMultiplier,
        })),
        nutrients: result.totalNutrients,
        processing_time_ms: result.processingTimeMs,
        faces_blurred: result.facesBlurred,
        audio_transcript: result.audioTranscript,
      },
      edge_model_version: result.modelVersions.foodClassifier,
      verified: false,
      processing_status: result.needsCloudReview ? 'needs_cloud_review' : 'edge_only',
    };

    try {
      const resp = await fetch(`${SUPABASE_URL}/rest/v1/user_activity_event`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        return { success: false, error: `HTTP ${resp.status}: ${errText}` };
      }

      const data = await resp.json();
      return { success: true, eventId: data[0]?.event_id };
    } catch (err) {
      return { success: false, error: String(err) };
    }
  }

  /**
   * Upload thumbnail to Supabase Storage
   */
  async uploadThumbnail(
    userId: string,
    eventId: number,
    thumbnailBase64: string,
  ): Promise<string | null> {
    const filePath = `${userId}/${eventId}_thumb.webp`;
    const binaryData = this.base64ToBytes(thumbnailBase64);

    try {
      const resp = await fetch(
        `${SUPABASE_URL}/storage/v1/object/thumbnails/${filePath}`,
        {
          method: 'POST',
          headers: {
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
            'Content-Type': 'image/webp',
          },
          body: binaryData,
        },
      );

      if (resp.ok) {
        return `${SUPABASE_URL}/storage/v1/object/public/thumbnails/${filePath}`;
      }
    } catch (err) {
      console.log('[Upload] Thumbnail upload failed:', err);
    }
    return null;
  }

  /**
   * Get daily nutrition summary for a user
   */
  async getDailySummary(userId: string): Promise<DailySummary> {
    const today = new Date().toISOString().split('T')[0];

    try {
      const resp = await fetch(
        `${SUPABASE_URL}/rest/v1/user_activity_event?user_id=eq.${userId}&detected_at=gte.${today}T00:00:00&order=detected_at.desc`,
        { headers: this.headers },
      );

      const events = await resp.json();
      const meals = events.filter((e: any) => e.event_type === 'meal');

      let totalCal = 0, totalProtein = 0, totalFat = 0, totalCarb = 0, totalSodium = 0;

      for (const meal of meals) {
        const nutrients = meal.structured_data?.nutrients || {};
        totalCal += nutrients.energyKcal || 0;
        totalProtein += nutrients.proteinG || 0;
        totalFat += nutrients.fatG || 0;
        totalCarb += nutrients.carbohydrateG || 0;
        totalSodium += nutrients.sodiumMg || 0;
      }

      return {
        date: today,
        mealCount: meals.length,
        totalEvents: events.length,
        totalCalories: Math.round(totalCal),
        totalProteinG: Math.round(totalProtein),
        totalFatG: Math.round(totalFat),
        totalCarbG: Math.round(totalCarb),
        totalSodiumMg: Math.round(totalSodium),
      };
    } catch (err) {
      console.log('[Upload] Failed to get daily summary:', err);
      return {
        date: today, mealCount: 0, totalEvents: 0,
        totalCalories: 0, totalProteinG: 0, totalFatG: 0,
        totalCarbG: 0, totalSodiumMg: 0,
      };
    }
  }

  /**
   * Submit user correction for an event (active learning)
   */
  async submitCorrection(
    eventId: number,
    correctedFood: string,
    correctedCalories: number,
  ): Promise<boolean> {
    try {
      const resp = await fetch(
        `${SUPABASE_URL}/rest/v1/user_activity_event?event_id=eq.${eventId}`,
        {
          method: 'PATCH',
          headers: this.headers,
          body: JSON.stringify({
            verified: true,
            processing_status: 'user_verified',
            correction_data: {
              corrected_food: correctedFood,
              corrected_calories: correctedCalories,
              corrected_at: new Date().toISOString(),
            },
          }),
        },
      );
      return resp.ok;
    } catch {
      return false;
    }
  }

  /**
   * Upload daily lifestyle aggregation
   */
  async uploadDailyLifestyle(userId: string, summary: DailySummary): Promise<boolean> {
    try {
      const resp = await fetch(`${SUPABASE_URL}/rest/v1/user_lifestyle`, {
        method: 'POST',
        headers: this.headers,
        body: JSON.stringify({
          user_id: userId,
          recorded_date: summary.date,
          total_calories: summary.totalCalories,
          protein_g: summary.totalProteinG,
          fat_g: summary.totalFatG,
          carb_g: summary.totalCarbG,
          sodium_mg: summary.totalSodiumMg,
          meal_count: summary.mealCount,
          data_source: 'ai_glasses',
        }),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  private base64ToBytes(base64: string): Uint8Array {
    const binaryString = atob(base64.replace(/^data:.*,/, ''));
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
  }
}

export const supabaseUploader = new SupabaseUploaderService();
