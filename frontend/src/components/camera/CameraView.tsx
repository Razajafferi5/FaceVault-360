import React, { useEffect, useRef } from 'react';
import { FaceDetectionResult, CameraGuidance, CameraHealth } from '../../types';

interface CameraViewProps {
  faces: FaceDetectionResult[];
  guidance: CameraGuidance | null;
  cameraHealth: CameraHealth | null;
  frameBlob: Blob | null;
  mode?: 'live' | 'enrollment';
}

export const CameraView: React.FC<CameraViewProps> = ({ 
  faces, guidance, cameraHealth, frameBlob, mode = 'live' 
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageCache = useRef<HTMLImageElement>(new Image());

  useEffect(() => {
    if (!frameBlob || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const url = URL.createObjectURL(frameBlob);
    
    imageCache.current.onload = () => {
      // Set canvas size to match image aspect ratio
      const containerWidth = canvas.parentElement?.clientWidth || 640;
      const scale = containerWidth / imageCache.current.width;
      canvas.width = containerWidth;
      canvas.height = imageCache.current.height * scale;

      ctx.drawImage(imageCache.current, 0, 0, canvas.width, canvas.height);

      // Draw target guide zone
      const targetW = canvas.width * 0.42;
      const targetH = canvas.height * 0.60;
      const targetX = (canvas.width - targetW) / 2;
      const targetY = (canvas.height - targetH) * 0.40;

      ctx.save();
      const guideColor = guidance?.severity === 'good' ? '#22c55e' : (guidance?.severity === 'warning' ? '#eab308' : (faces.length > 0 ? '#ef4444' : 'rgba(255, 255, 255, 0.3)'));
      ctx.strokeStyle = guideColor;
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 6]);
      ctx.strokeRect(targetX, targetY, targetW, targetH);
      ctx.restore();

      // Draw bounding boxes
      faces.forEach(face => {
        const rawBox = face.bbox || [0, 0, 0, 0];
        let bx = rawBox[0], by = rawBox[1], bw = rawBox[2], bh = rawBox[3];
        
        let scaledX = bx * scale;
        let scaledY = by * scale;
        let scaledW = bw * scale;
        let scaledH = bh * scale;
        if (bw > bx && bh > by && rawBox[2] > 300) {
          scaledW = (bw - bx) * scale;
          scaledH = (bh - by) * scale;
        }

        // Determine colors based on status
        const isUnknown = !face.authorized || face.status === 'unknown' || face.name === 'Unknown Person';
        const color = isUnknown ? '#ef4444' : '#22c55e';
        const label = isUnknown ? 'UNKNOWN PERSON' : (face.name || 'AUTHORIZED EMPLOYEE');
        const subtext = isUnknown ? 'ACCESS/ATTENDANCE REJECTED' : `MATCH ${Math.round((face.similarity || face.confidence) * 100)}% • ATTENDANCE LOGGED`;

        // Draw bounding box
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(scaledX, scaledY, scaledW, scaledH);

        // Draw label background tag
        const tagHeight = 32;
        const tagWidth = Math.max(scaledW, 230);
        ctx.fillStyle = color;
        ctx.fillRect(scaledX, Math.max(0, scaledY - tagHeight), tagWidth, tagHeight);

        // Draw label text
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText(label, scaledX + 8, Math.max(14, scaledY - tagHeight + 14));

        ctx.font = 'bold 10px sans-serif';
        ctx.fillStyle = isUnknown ? '#fef08a' : '#dcfce7';
        ctx.fillText(subtext, scaledX + 8, Math.max(26, scaledY - tagHeight + 26));
      });

      URL.revokeObjectURL(url);
    };
    
    imageCache.current.src = url;
  }, [frameBlob, faces]);

  return (
    <div className="relative w-full rounded-xl overflow-hidden bg-black/50 border border-[#334155] aspect-video flex items-center justify-center">
      {!frameBlob && (
        <div className="text-slate-500 flex flex-col items-center">
          <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div>
          <p>Waiting for camera feed...</p>
        </div>
      )}
      
      <canvas 
        ref={canvasRef} 
        className="absolute top-0 left-0 w-full h-full object-contain"
      />

      {/* Camera Health Overlay */}
      {cameraHealth && (
        <div className="absolute top-4 right-4 bg-black/60 backdrop-blur-sm px-3 py-2 rounded-lg border border-white/10 text-xs font-mono">
          <div className="flex items-center gap-2 mb-1">
            <div className={`w-2 h-2 rounded-full ${cameraHealth.online ? 'bg-green-500 animate-pulse-glow' : 'bg-red-500'}`}></div>
            <span className="text-slate-300">FPS: <span className="text-white">{cameraHealth.fps.toFixed(1)}</span></span>
          </div>
          <div className="text-slate-400">
            Latency: <span className="text-white">{Math.round(cameraHealth.latency_ms)}ms</span>
          </div>
        </div>
      )}

      {/* Guidance Overlay */}
      {guidance && guidance.message && (
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-full max-w-md pointer-events-none">
          <div className={`
            mx-auto w-fit px-6 py-3 rounded-full text-center font-bold text-lg border shadow-xl backdrop-blur-md
            ${guidance.severity === 'error' ? 'bg-red-500/20 text-red-400 border-red-500/50 animate-pulse' : 
              guidance.severity === 'warning' ? 'bg-amber-500/20 text-amber-400 border-amber-500/50' : 
              'bg-green-500/20 text-green-400 border-green-500/50'}
          `}>
            {guidance.severity === 'error' && '🔴 '}
            {guidance.severity === 'warning' && '🟠 '}
            {guidance.severity === 'good' && '🟢 '}
            {guidance.message}
          </div>
        </div>
      )}

      {/* Unknown Person Alert Banner */}
      {faces.some(f => !f.authorized || f.status === 'unknown' || f.name === 'Unknown Person') && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 pointer-events-none animate-bounce">
          <div className="bg-red-600 text-white backdrop-blur-md px-6 py-2.5 rounded-full border-2 border-red-300 shadow-2xl flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full bg-yellow-300 animate-ping" />
            <span className="font-extrabold text-xs uppercase tracking-wider">
              🚨 UNKNOWN PERSON — ACCESS/ATTENDANCE REJECTED
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
