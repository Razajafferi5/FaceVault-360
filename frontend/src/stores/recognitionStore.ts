import { create } from 'zustand';
import { FaceDetectionResult, CameraGuidance, CameraHealth } from '../types';

interface RecognitionState {
  faces: FaceDetectionResult[];
  guidance: CameraGuidance | null;
  cameraHealth: CameraHealth | null;
  isConnected: boolean;
  latestFrame: Blob | null;
  setFaces: (faces: FaceDetectionResult[]) => void;
  setGuidance: (guidance: CameraGuidance | null) => void;
  setCameraHealth: (health: CameraHealth | null) => void;
  setConnected: (status: boolean) => void;
  setLatestFrame: (frame: Blob | null) => void;
}

export const useRecognitionStore = create<RecognitionState>((set) => ({
  faces: [],
  guidance: null,
  cameraHealth: null,
  isConnected: false,
  latestFrame: null,
  setFaces: (faces) => set({ faces }),
  setGuidance: (guidance) => set({ guidance }),
  setCameraHealth: (cameraHealth) => set({ cameraHealth }),
  setConnected: (isConnected) => set({ isConnected }),
  setLatestFrame: (latestFrame) => set({ latestFrame }),
}));
