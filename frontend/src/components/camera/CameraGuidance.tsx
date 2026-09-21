import React from 'react';
import { CameraGuidance as CameraGuidanceType } from '../../types';
import { AlertCircle, CheckCircle2, AlertTriangle } from 'lucide-react';

interface CameraGuidanceProps {
  guidance: CameraGuidanceType | null;
}

export const CameraGuidance: React.FC<CameraGuidanceProps> = ({ guidance }) => {
  if (!guidance) return null;

  const getIcon = () => {
    switch (guidance.severity) {
      case 'error': return <AlertCircle className="w-8 h-8 text-red-500" />;
      case 'warning': return <AlertTriangle className="w-8 h-8 text-amber-500" />;
      case 'good': return <CheckCircle2 className="w-8 h-8 text-green-500" />;
    }
  };

  const getColors = () => {
    switch (guidance.severity) {
      case 'error': return 'bg-red-500/10 border-red-500/20 text-red-400';
      case 'warning': return 'bg-amber-500/10 border-amber-500/20 text-amber-400';
      case 'good': return 'bg-green-500/10 border-green-500/20 text-green-400';
    }
  };

  return (
    <div className={`flex items-center gap-4 p-4 rounded-xl border ${getColors()}`}>
      <div className={guidance.severity === 'error' ? 'animate-pulse' : ''}>
        {getIcon()}
      </div>
      <div>
        <h4 className="font-bold text-lg">{guidance.message}</h4>
        <p className="text-sm opacity-80">
          {!guidance.face_detected ? 'No face found in frame' : 
            guidance.position_ok ? 'Position is optimal' : 'Adjust position for better recognition'}
        </p>
      </div>
    </div>
  );
};
