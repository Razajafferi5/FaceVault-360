import React from 'react';
import { FaceDetectionResult } from '../../types';
import { StatusBadge } from '../ui/StatusBadge';
import { ConfidenceMeter } from '../ui/ConfidenceMeter';

interface FaceOverlayProps {
  faces: FaceDetectionResult[];
}

export const FaceOverlay: React.FC<FaceOverlayProps> = ({ faces }) => {
  if (faces.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-slate-500 p-6 border-2 border-dashed border-[#334155] rounded-xl">
        <p>No faces detected in view</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {faces.map((face, idx) => {
        const isUnknown = !face.authorized || face.status === 'unknown' || face.name === 'Unknown Person';
        return (
          <div 
            key={idx} 
            className={`border rounded-xl p-4 shadow-lg animate-slide-in transition-all ${
              isUnknown 
                ? 'bg-red-950/25 border-red-500/50 shadow-red-500/10' 
                : 'bg-[#1e293b] border-emerald-500/40 shadow-emerald-500/10'
            }`}
          >
            <div className="flex justify-between items-start mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className={`text-lg font-bold mb-0.5 ${isUnknown ? 'text-red-300' : 'text-white'}`}>
                    {isUnknown ? 'Unknown Person' : (face.name || 'Employee')}
                  </h3>
                  {isUnknown && (
                    <span className="text-[10px] uppercase font-bold bg-red-500 text-white px-1.5 py-0.5 rounded">
                      Unregistered
                    </span>
                  )}
                </div>
                <StatusBadge status={isUnknown ? 'denied' : face.status} />
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-400">Match Score</div>
                <div className={`text-xl font-mono font-bold ${isUnknown ? 'text-red-400' : 'text-emerald-400'}`}>
                  {Math.round(face.similarity * 100)}%
                </div>
              </div>
            </div>

            {isUnknown ? (
              <div className="p-2.5 bg-red-900/40 border border-red-500/50 rounded-lg text-xs text-red-200 mt-2 font-semibold flex items-center gap-1.5">
                <span>🚨</span>
                <span>UNKNOWN PERSON — ACCESS/ATTENDANCE REJECTED</span>
              </div>
            ) : (
              <div className="p-2 bg-emerald-900/30 border border-emerald-500/40 rounded-lg text-xs text-emerald-300 mt-2 flex items-center justify-between font-semibold">
                <span>✓ Verified Enrolled Employee</span>
                <span className="text-emerald-400">Attendance Logged</span>
              </div>
            )}

            <div className="space-y-3 mt-4">
              <ConfidenceMeter value={face.confidence} label="Detection Confidence" />
              <ConfidenceMeter value={face.liveness_score} label="Liveness Score" />
              
              <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t border-[#334155]">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Pose</div>
                  <div className="text-sm text-slate-300 capitalize">{face.pose_label}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Quality</div>
                  <div className="text-sm text-slate-300">{face.quality_score.toFixed(2)}</div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
