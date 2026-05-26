/**
 * ML Pipeline Service
 * Phone-side AI inference chain for glasses frames
 *
 * Pipeline order (Stage 4 of v3 plan):
 *   1. YOLO-Face → blur bystander faces (PRIVACY FIRST)
 *   2. MobileNetV2-Food → classify food item
 *   3. YOLOv8n → detect food area, estimate portion
 *   4. FoodLookup → MFDS/USDA nutrition database
 *   5. Whisper-tiny → STT if audio captured
 *   6. Package → structured JSON event
 */

export interface FoodDetection {
  foodName: string;
  confidence: number;
  boundingBox?: { x: number; y: number; width: number; height: number };
  portionSize: 'small' | 'medium' | 'large';
  portionMultiplier: number;
}

export interface NutritionResult {
  foodName: string;
  sourceDb: 'MFDS' | 'USDA' | 'unknown';
  servingSize: string;
  energyKcal: number | null;
  proteinG: number | null;
  fatG: number | null;
  carbohydrateG: number | null;
  dietaryFiberG: number | null;
  sodiumMg: number | null;
  totalSugarG: number | null;
  cholesterolMg: number | null;
}

export interface PipelineResult {
  eventType: 'meal' | 'drink' | 'medication' | 'exercise' | 'unknown';
  foodDetections: FoodDetection[];
  nutrition: NutritionResult | null;
  totalCalories: number;
  totalNutrients: {
    energyKcal: number;
    proteinG: number;
    fatG: number;
    carbohydrateG: number;
    sodiumMg: number;
  };
  confidenceScore: number;
  needsCloudReview: boolean;
  facesBlurred: number;
  thumbnailBase64: string | null;
  audioTranscript: string | null;
  processingTimeMs: number;
  modelVersions: {
    faceBlur: string;
    foodClassifier: string;
    portionDetector: string;
  };
}

class MLPipelineService {
  private isInitialized = false;

  // Model status tracking
  private models = {
    yoloFace: { loaded: false, version: 'yolo-face-v1.0' },
    mobileNetFood: { loaded: false, version: 'mobilenetv2-food-kr-v1.0' },
    yolov8n: { loaded: false, version: 'yolov8n-food-v1.0' },
    whisperTiny: { loaded: false, version: 'whisper-tiny-v1.0' },
  };

  /**
   * Initialize ML models (load TFLite models into memory)
   * Called once at app startup
   */
  async initialize(): Promise<void> {
    console.log('[MLPipeline] Initializing models...');

    // TODO: Load actual TFLite models
    // In production:
    //   const faceModel = await TFLite.loadModel('models/yolo_face.tflite');
    //   const foodModel = await TFLite.loadModel('models/mobilenetv2_food.tflite');
    //   const portionModel = await TFLite.loadModel('models/yolov8n.tflite');
    //   const whisperModel = await TFLite.loadModel('models/whisper_tiny.tflite');

    // For now, mark as loaded (will use mock inference for testing)
    this.models.yoloFace.loaded = true;
    this.models.mobileNetFood.loaded = true;
    this.models.yolov8n.loaded = true;
    this.models.whisperTiny.loaded = true;
    this.isInitialized = true;

    console.log('[MLPipeline] All models initialized');
  }

  /**
   * Run full inference pipeline on a glasses frame
   * This is the core Stage 4 processing
   */
  async processFrame(
    imageBase64: string,
    audioBase64?: string,
  ): Promise<PipelineResult> {
    const startTime = Date.now();

    if (!this.isInitialized) {
      await this.initialize();
    }

    // Step 1: YOLO-Face blur (PRIVACY FIRST - before any other processing)
    const facesBlurred = await this.blurFaces(imageBase64);
    console.log(`[MLPipeline] Step 1: Blurred ${facesBlurred} faces`);

    // Step 2: MobileNetV2-Food classification
    const foodDetection = await this.classifyFood(imageBase64);
    console.log(`[MLPipeline] Step 2: Detected "${foodDetection.foodName}" (${foodDetection.confidence})`);

    // Step 3: YOLOv8n portion detection
    const portionResult = await this.detectPortion(imageBase64);
    foodDetection.portionSize = portionResult.portionSize;
    foodDetection.portionMultiplier = portionResult.portionMultiplier;
    console.log(`[MLPipeline] Step 3: Portion = ${portionResult.portionSize} (${portionResult.portionMultiplier}x)`);

    // Step 4: Nutrition lookup
    const nutrition = await this.lookupNutrition(foodDetection.foodName, foodDetection.portionMultiplier);
    console.log(`[MLPipeline] Step 4: ${nutrition?.energyKcal ?? 'N/A'} kcal from ${nutrition?.sourceDb ?? 'none'}`);

    // Step 5: Whisper STT (if audio provided)
    let audioTranscript: string | null = null;
    if (audioBase64) {
      audioTranscript = await this.transcribeAudio(audioBase64);
      console.log(`[MLPipeline] Step 5: Transcript = "${audioTranscript?.substring(0, 50)}..."`);
    }

    // Step 6: Generate thumbnail
    const thumbnailBase64 = await this.generateThumbnail(imageBase64);

    // Step 7: Package result
    const confidenceScore = foodDetection.confidence;
    const needsCloudReview = confidenceScore < 0.7;

    const totalNutrients = {
      energyKcal: nutrition?.energyKcal ?? 0,
      proteinG: nutrition?.proteinG ?? 0,
      fatG: nutrition?.fatG ?? 0,
      carbohydrateG: nutrition?.carbohydrateG ?? 0,
      sodiumMg: nutrition?.sodiumMg ?? 0,
    };

    const processingTimeMs = Date.now() - startTime;
    console.log(`[MLPipeline] Complete in ${processingTimeMs}ms | confidence=${confidenceScore} | cloudReview=${needsCloudReview}`);

    return {
      eventType: this.inferEventType(foodDetection),
      foodDetections: [foodDetection],
      nutrition,
      totalCalories: totalNutrients.energyKcal,
      totalNutrients,
      confidenceScore,
      needsCloudReview,
      facesBlurred,
      thumbnailBase64,
      audioTranscript,
      processingTimeMs,
      modelVersions: {
        faceBlur: this.models.yoloFace.version,
        foodClassifier: this.models.mobileNetFood.version,
        portionDetector: this.models.yolov8n.version,
      },
    };
  }

  // ── Individual model inference methods ──

  private async blurFaces(imageBase64: string): Promise<number> {
    // TODO: Real YOLO-Face TFLite inference
    // 1. Decode base64 → pixel array
    // 2. Run YOLO-Face model → get face bounding boxes
    // 3. Apply Gaussian blur to each face region
    // 4. Re-encode to base64
    // Returns: number of faces blurred

    // Mock: return 0-2 faces
    return Math.floor(Math.random() * 3);
  }

  private async classifyFood(imageBase64: string): Promise<FoodDetection> {
    // TODO: Real MobileNetV2-Food TFLite inference
    // 1. Decode base64 → resize to 224x224
    // 2. Normalize pixels to [0, 1]
    // 3. Run MobileNetV2-Food model
    // 4. Get top-1 class + confidence

    // Mock: return realistic food detection
    const mockFoods = [
      { foodName: '김치찌개', confidence: 0.85 },
      { foodName: '비빔밥', confidence: 0.78 },
      { foodName: '삼겹살', confidence: 0.72 },
      { foodName: '된장찌개', confidence: 0.81 },
      { foodName: '불고기', confidence: 0.90 },
      { foodName: '아메리카노', confidence: 0.95 },
    ];

    const mock = mockFoods[Math.floor(Math.random() * mockFoods.length)];
    return {
      foodName: mock.foodName,
      confidence: mock.confidence,
      portionSize: 'medium',
      portionMultiplier: 1.0,
    };
  }

  private async detectPortion(imageBase64: string): Promise<{
    portionSize: 'small' | 'medium' | 'large';
    portionMultiplier: number;
  }> {
    // TODO: Real YOLOv8n TFLite inference
    // 1. Run object detection → get food bounding box area
    // 2. Compare to reference plate/bowl size
    // 3. Estimate portion: small (0.75x), medium (1.0x), large (1.5x)

    // Mock: return medium portion
    const sizes = [
      { portionSize: 'small' as const, portionMultiplier: 0.75 },
      { portionSize: 'medium' as const, portionMultiplier: 1.0 },
      { portionSize: 'large' as const, portionMultiplier: 1.5 },
    ];
    return sizes[Math.floor(Math.random() * sizes.length)];
  }

  private async lookupNutrition(
    foodName: string,
    portionMultiplier: number,
  ): Promise<NutritionResult | null> {
    // TODO: Query local SQLite on phone
    // In production: use react-native-sqlite-storage with MFDS + USDA databases
    //
    // For testing: call our FastAPI backend
    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/food-lookup?query=${encodeURIComponent(foodName)}`,
      );
      if (response.ok) {
        return await response.json();
      }
    } catch {
      // Fallback: return mock nutrition
    }

    // Mock fallback with realistic Korean food data
    const mockNutrition: Record<string, NutritionResult> = {
      '김치찌개': { foodName: '김치찌개', sourceDb: 'MFDS', servingSize: '100g', energyKcal: 61, proteinG: 3.8, fatG: 3.7, carbohydrateG: 3.0, dietaryFiberG: 1.2, sodiumMg: 491, totalSugarG: 1.5, cholesterolMg: 12 },
      '비빔밥': { foodName: '비빔밥', sourceDb: 'MFDS', servingSize: '100g', energyKcal: 142, proteinG: 6.8, fatG: 4.3, carbohydrateG: 18.8, dietaryFiberG: 2.1, sodiumMg: 232, totalSugarG: 3.0, cholesterolMg: 45 },
      '삼겹살': { foodName: '삼겹살', sourceDb: 'MFDS', servingSize: '100g', energyKcal: 316, proteinG: 15.0, fatG: 25.0, carbohydrateG: 8.0, dietaryFiberG: 0, sodiumMg: 50, totalSugarG: 0, cholesterolMg: 72 },
      '된장찌개': { foodName: '된장찌개', sourceDb: 'MFDS', servingSize: '100g', energyKcal: 45, proteinG: 3.2, fatG: 1.8, carbohydrateG: 4.5, dietaryFiberG: 1.5, sodiumMg: 520, totalSugarG: 1.2, cholesterolMg: 5 },
      '불고기': { foodName: '불고기', sourceDb: 'MFDS', servingSize: '100g', energyKcal: 168, proteinG: 17.5, fatG: 8.2, carbohydrateG: 6.8, dietaryFiberG: 0.5, sodiumMg: 380, totalSugarG: 5.2, cholesterolMg: 55 },
      '아메리카노': { foodName: '아메리카노', sourceDb: 'MFDS', servingSize: '100g', energyKcal: 3, proteinG: 0.2, fatG: 0.0, carbohydrateG: 0.6, dietaryFiberG: 0, sodiumMg: 2, totalSugarG: 0, cholesterolMg: 0 },
    };

    const result = mockNutrition[foodName];
    if (result && portionMultiplier !== 1.0) {
      return {
        ...result,
        energyKcal: result.energyKcal ? Math.round(result.energyKcal * portionMultiplier) : null,
        proteinG: result.proteinG ? Math.round(result.proteinG * portionMultiplier * 10) / 10 : null,
        fatG: result.fatG ? Math.round(result.fatG * portionMultiplier * 10) / 10 : null,
        carbohydrateG: result.carbohydrateG ? Math.round(result.carbohydrateG * portionMultiplier * 10) / 10 : null,
        sodiumMg: result.sodiumMg ? Math.round(result.sodiumMg * portionMultiplier) : null,
      };
    }
    return result || null;
  }

  private async transcribeAudio(audioBase64: string): Promise<string | null> {
    // TODO: Real Whisper-tiny TFLite inference
    // 1. Decode base64 → audio samples
    // 2. Run Whisper-tiny model
    // 3. Return Korean text transcription

    // Mock: return null (no transcript)
    return null;
  }

  private async generateThumbnail(imageBase64: string): Promise<string> {
    // TODO: Resize image to 320x240 WebP thumbnail
    // In production: use react-native-image-resizer

    // For now, return original (in testing, images are already small)
    return imageBase64;
  }

  private inferEventType(detection: FoodDetection): PipelineResult['eventType'] {
    const drinks = ['아메리카노', '커피', '주스', '물', 'coffee', 'tea', 'juice', 'water', '맥주', '소주'];
    if (drinks.some(d => detection.foodName.toLowerCase().includes(d))) {
      return 'drink';
    }
    return 'meal';
  }

  getModelStatus(): typeof this.models {
    return { ...this.models };
  }
}

export const mlPipeline = new MLPipelineService();
