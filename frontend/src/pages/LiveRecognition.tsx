import React, { useEffect, useState, useRef, useCallback } from 'react';
import { CameraView } from '../components/camera/CameraView';
import { FaceOverlay } from '../components/camera/FaceOverlay';
import { useRecognitionStore } from '../stores/recognitionStore';
import { WebSocketService } from '../services/websocket';
import { api } from '../services/api';
import { Camera, Radio, CheckCircle, ShieldAlert } from 'lucide-react';

export const LiveRecognition: React.FC = () => {
  const { faces, guidance, cameraHealth, latestFrame, setFaces, setGuidance, setCameraHealth, setConnected, setLatestFrame } = useRecognitionStore();
  const [wsService, setWsService] = useState<WebSocketService | null>(null);
  const [sourceMode, setSourceMode] = useState<'backend' | 'browser'>('backend');
  const [attendanceNotice, setAttendanceNotice] = useState<string | null>(null);

  // Browser webcam refs
  const browserVideoRef = useRef<HTMLVideoElement | null>(null);
  const browserCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const browserStreamRef = useRef<MediaStream | null>(null);
  const browserLoopTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isProcessingRef = useRef<boolean>(false);

  // Stop browser webcam
  const stopBrowserCamera = useCallback(() => {
    if (browserLoopTimerRef.current) {
      clearInterval(browserLoopTimerRef.current);
      browserLoopTimerRef.current = null;
    }
    if (browserStreamRef.current) {
      browserStreamRef.current.getTracks().forEach(t => t.stop());
      browserStreamRef.current = null;
    }
  }, []);

  // Process a browser frame
  const processBrowserFrame = useCallback(async () => {
    if (!browserVideoRef.current || !browserCanvasRef.current || isProcessingRef.current) return;
    if (browserVideoRef.current.readyState < 2) return;

    isProcessingRef.current = true;
    try {
      const video = browserVideoRef.current;
      const canvas = browserCanvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      canvas.toBlob(async (blob) => {
        if (blob) setLatestFrame(blob);
      }, 'image/jpeg', 0.85);

      const base64Data = canvas.toDataURL('image/jpeg', 0.80);
      const res = await api.recognizeFrame(base64Data);

      if (res && res.faces) {
        setFaces(res.faces);
        if (res.camera_guidance) setGuidance(res.camera_guidance);

        // Check for newly recognized authorized employee
        const authorizedFace = res.faces.find((f: any) => f.authorized && f.name);
        if (authorizedFace) {
          setAttendanceNotice(`✓ Attendance Logged: ${authorizedFace.name}`);
        }
      }
    } catch (e) {
      // frame processing catch
    } finally {
      isProcessingRef.current = false;
    }
  }, [setFaces, setGuidance, setLatestFrame]);

  // Start browser webcam
  const startBrowserCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' }
      });
      browserStreamRef.current = stream;
      if (browserVideoRef.current) {
        browserVideoRef.current.srcObject = stream;
        browserVideoRef.current.play();
      }

      browserLoopTimerRef.current = setInterval(() => {
        processBrowserFrame();
      }, 250);
    } catch (err) {
      console.error("Browser camera access error:", err);
    }
  }, [processBrowserFrame]);

  // Handle Backend WebSocket mode
  useEffect(() => {
    if (sourceMode === 'backend') {
      stopBrowserCamera();

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = import.meta.env.VITE_WS_URL || `${protocol}//${host}/ws/recognition`;

      const ws = new WebSocketService(
        wsUrl,
        (msg) => {
          if (msg.type === 'recognition_result') {
            setFaces(msg.faces || []);
            setGuidance(msg.camera_guidance || null);
            setCameraHealth(msg.camera_health || null);

            // Check for authorized employee attendance
            const authorizedFace = (msg.faces || []).find((f: any) => f.authorized && f.name);
            if (authorizedFace) {
              setAttendanceNotice(`✓ Attendance Logged: ${authorizedFace.name}`);
            }
          }
        },
        (blob) => {
          setLatestFrame(blob);
        }
      );

      ws.connect();
      setWsService(ws);
      setConnected(true);

      return () => {
        ws.disconnect();
        setConnected(false);
        setFaces([]);
        setGuidance(null);
        setCameraHealth(null);
        setLatestFrame(null);
      };
    } else {
      // Browser webcam mode
      if (wsService) {
        wsService.disconnect();
        setWsService(null);
      }
      startBrowserCamera();

      return () => {
        stopBrowserCamera();
      };
    }
  }, [sourceMode]);

  // Clear attendance notice after 5 seconds
  useEffect(() => {
    if (attendanceNotice) {
      const t = setTimeout(() => setAttendanceNotice(null), 5000);
      return () => clearTimeout(t);
    }
  }, [attendanceNotice]);

  const hasUnknownFace = faces.some(f => !f.authorized || f.status === 'unknown' || f.name === 'Unknown Person');
  const hasAuthorizedFace = faces.some(f => f.authorized);

  return (
    <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-8rem)]">
      {/* Main Camera Area */}
      <div className="flex-grow flex flex-col space-y-4 lg:w-2/3">
        <div className="flex flex-wrap justify-between items-center gap-3">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              Live Attendance & Access Control
              {hasUnknownFace && (
                <span className="text-xs bg-red-600 text-white font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1 animate-pulse">
                  <ShieldAlert className="w-3.5 h-3.5" /> REJECTED
                </span>
              )}
            </h2>
            <p className="text-slate-400 text-sm">Real-time biometric recognition and automated attendance logging</p>
          </div>

          <div className="flex items-center gap-3">
            {/* Camera Source Switcher */}
            <div className="flex items-center bg-slate-900 border border-slate-700 rounded-lg p-1 text-xs">
              <button
                onClick={() => setSourceMode('backend')}
                className={`px-2.5 py-1 rounded flex items-center gap-1.5 font-medium transition-all ${
                  sourceMode === 'backend' 
                    ? 'bg-blue-600 text-white shadow' 
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <Radio className="w-3 h-3" /> Server Stream
              </button>
              <button
                onClick={() => setSourceMode('browser')}
                className={`px-2.5 py-1 rounded flex items-center gap-1.5 font-medium transition-all ${
                  sourceMode === 'browser' 
                    ? 'bg-blue-600 text-white shadow' 
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <Camera className="w-3 h-3" /> Browser Webcam
              </button>
            </div>

            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${
                sourceMode === 'backend' 
                  ? (wsService?.isConnected() ? 'bg-green-500 animate-pulse-glow' : 'bg-red-500')
                  : 'bg-emerald-500 animate-pulse-glow'
              }`}></div>
              <span className="text-xs font-medium text-slate-300">
                {sourceMode === 'backend' ? (wsService?.isConnected() ? 'Connected' : 'Reconnecting...') : 'Webcam Active'}
              </span>
            </div>
          </div>
        </div>

        {/* Unknown Person Rejection Banner */}
        {hasUnknownFace && (
          <div className="bg-red-600/20 border-2 border-red-500/60 text-red-300 px-4 py-3 rounded-xl text-sm flex items-center justify-between shadow-lg shadow-red-500/10 animate-slide-in">
            <div className="flex items-center gap-2.5">
              <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 animate-pulse" />
              <span className="font-extrabold text-white tracking-wide">
                🚨 UNKNOWN PERSON — ACCESS/ATTENDANCE REJECTED
              </span>
            </div>
            <span className="text-xs bg-red-600 text-white font-bold px-2.5 py-1 rounded">
              ATTENDANCE BLOCKED
            </span>
          </div>
        )}

        {/* Real-time Attendance Success Toast */}
        {attendanceNotice && (
          <div className="bg-emerald-500/10 border border-emerald-500/40 text-emerald-300 px-4 py-2.5 rounded-xl text-sm flex items-center justify-between shadow-lg shadow-emerald-500/10 animate-slide-in">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              <span className="font-semibold">{attendanceNotice}</span>
            </div>
            <span className="text-xs bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-mono">
              Recorded in Database
            </span>
          </div>
        )}
        
        <div className="flex-grow rounded-xl overflow-hidden shadow-2xl relative bg-black flex items-center">
          <CameraView 
            faces={faces}
            guidance={guidance}
            cameraHealth={cameraHealth}
            frameBlob={latestFrame}
          />
        </div>

        {/* Hidden elements for browser webcam mode */}
        <video ref={browserVideoRef} playsInline muted className="hidden" />
        <canvas ref={browserCanvasRef} className="hidden" />
      </div>

      {/* Side Panel for Results */}
      <div className="w-full lg:w-96 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-4 shrink-0">
          <h3 className="font-semibold text-white">Live Detections ({faces.length})</h3>
          {hasAuthorizedFace && (
            <span className="text-xs text-emerald-400 font-medium">✓ Employee Recognized</span>
          )}
        </div>
        <div className="flex-grow overflow-y-auto pr-2 space-y-4">
          <FaceOverlay faces={faces} />
        </div>
      </div>
    </div>
  );
};
