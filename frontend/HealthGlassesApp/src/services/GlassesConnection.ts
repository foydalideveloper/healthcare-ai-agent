/**
 * Glasses Connection Service
 * Handles BLE connection to AI glasses (Meta Ray-Ban Gen 2 or Mentra Live)
 *
 * Architecture:
 *   Glasses camera → BLE → This service → ML Pipeline → Supabase
 *
 * For Meta Ray-Ban Gen 2:
 *   Uses Meta Wearables Device Access Toolkit SDK
 *   Camera frames arrive as JPEG buffers via BLE streaming
 *
 * For Mentra Live (production):
 *   Uses MentraOS SDK (session.camera.requestPhoto())
 *   Camera frames arrive as raw buffers
 */

export type GlassesProvider = 'meta_rayban' | 'mentra_live' | 'simulator';

export interface GlassesFrame {
  imageData: string; // base64 JPEG
  audioData?: string; // base64 Opus audio clip
  timestamp: string; // ISO 8601
  triggerType: 'button_tap' | 'wake_word' | 'imu_motion' | 'scheduled' | 'manual';
  deviceInfo: {
    provider: GlassesProvider;
    batteryPercent: number;
    bleSignalStrength: number;
  };
}

export interface GlassesConnectionState {
  isConnected: boolean;
  provider: GlassesProvider;
  batteryPercent: number;
  lastFrameAt: string | null;
  framesReceived: number;
}

type FrameCallback = (frame: GlassesFrame) => void;

class GlassesConnectionService {
  private state: GlassesConnectionState = {
    isConnected: false,
    provider: 'simulator',
    batteryPercent: 100,
    lastFrameAt: null,
    framesReceived: 0,
  };

  private frameCallbacks: FrameCallback[] = [];

  /**
   * Connect to glasses via BLE
   * For testing: use 'simulator' mode which accepts manual photo input
   */
  async connect(provider: GlassesProvider = 'simulator'): Promise<boolean> {
    this.state.provider = provider;

    switch (provider) {
      case 'meta_rayban':
        return this.connectMetaRayBan();
      case 'mentra_live':
        return this.connectMentraLive();
      case 'simulator':
        this.state.isConnected = true;
        console.log('[Glasses] Simulator mode - send frames manually');
        return true;
    }
  }

  private async connectMetaRayBan(): Promise<boolean> {
    // TODO: Integrate Meta Wearables Device Access Toolkit
    // 1. Initialize MetaWearablesSDK
    // 2. Scan for nearby Meta Ray-Ban glasses
    // 3. Pair via BLE
    // 4. Request camera + microphone permissions
    // 5. Register frame callback
    //
    // Pseudo-code (actual SDK not yet publicly documented):
    // const device = await MetaWearables.scan();
    // await device.connect();
    // await device.requestPermission('camera');
    // device.onCameraFrame((frame) => this.handleFrame(frame));

    console.log('[Glasses] Meta Ray-Ban connection - SDK integration pending');
    console.log('[Glasses] For now, use simulator mode or phone camera fallback');
    this.state.isConnected = true;
    this.state.provider = 'meta_rayban';
    return true;
  }

  private async connectMentraLive(): Promise<boolean> {
    // TODO: Integrate MentraOS SDK
    // Uses TypeScript SDK: session.camera.requestPhoto()
    // Returns photo.buffer (raw image data)

    console.log('[Glasses] Mentra Live connection - MentraOS SDK integration pending');
    this.state.isConnected = true;
    this.state.provider = 'mentra_live';
    return true;
  }

  /**
   * Register callback for incoming frames from glasses
   */
  onFrame(callback: FrameCallback): void {
    this.frameCallbacks.push(callback);
  }

  /**
   * Manually inject a frame (for testing without glasses hardware)
   * In production, this is called by the BLE frame handler
   */
  injectFrame(frame: GlassesFrame): void {
    this.state.framesReceived++;
    this.state.lastFrameAt = frame.timestamp;

    for (const cb of this.frameCallbacks) {
      cb(frame);
    }
  }

  /**
   * Request a photo from glasses (pull mode)
   * Glasses takes a photo on demand
   */
  async requestCapture(triggerType: GlassesFrame['triggerType'] = 'manual'): Promise<void> {
    if (!this.state.isConnected) {
      throw new Error('Glasses not connected');
    }

    switch (this.state.provider) {
      case 'meta_rayban':
        // Meta SDK: request camera frame
        // await metaDevice.capturePhoto();
        console.log('[Glasses] Requesting capture from Meta Ray-Ban...');
        break;
      case 'mentra_live':
        // MentraOS: session.camera.requestPhoto()
        console.log('[Glasses] Requesting capture from Mentra Live...');
        break;
      case 'simulator':
        console.log('[Glasses] Simulator: inject frame manually via injectFrame()');
        break;
    }
  }

  getState(): GlassesConnectionState {
    return { ...this.state };
  }

  disconnect(): void {
    this.state.isConnected = false;
    this.frameCallbacks = [];
    console.log('[Glasses] Disconnected');
  }
}

export const glassesService = new GlassesConnectionService();
