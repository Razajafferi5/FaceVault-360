import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  Camera,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
  User,
  Building,
  Badge,
  RefreshCw,
  Video,
  Eye,
  AlertCircle
} from 'lucide-react';
import { api, BASE_URL } from '../../services/api';
import { UnknownPersonEvent, RTSPCamera } from '../../types';
import { useAuth } from '../../context/AuthContext';

interface RtspEnrollModalProps {
  event: UnknownPersonEvent | null;
  onClose: () => void;
  onSuccess: () => void;
}

export const RtspEnrollModal: React.FC<RtspEnrollModalProps> = ({ event, onClose, onSuccess }) => {
  const { isOwner } = useAuth();
  const [cameras, setCameras] = useState<RTSPCamera[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<number | undefined>(undefined);
  const [name, setName] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [department, setDepartment] = useState('Operations');
  const [role, setRole] = useState('Employee');

  // Evaluation & Samples state
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [lastEval, setLastEval] = useState<{
    valid: boolean;
    reason?: string;
    face_count: number;
    blur_variance?: number;
    quality_score?: number;
    yaw?: number;
    pitch?: number;
  } | null>(null);

  const [collectedSamples, setCollectedSamples] = useState<number>(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Load available RTSP cameras
  useEffect(() => {
    let isMounted = true;
    api.getCameras().then((res) => {
      if (!isMounted) return;
      if (res && res.items && res.items.length > 0) {
        setCameras(res.items);
        // Default to the camera of the event, or first enabled camera
        const match = res.items.find(c => c.id === event?.camera_id || (c.camera_role || c.mode) === event?.camera_role);
        if (match) {
          setSelectedCameraId(match.id);
        } else {
          setSelectedCameraId(res.items[0].id);
        }
      }
    }).catch(console.error);

    return () => { isMounted = false; };
  }, [event]);

  // Periodic frame quality evaluation when modal is open
  useEffect(() => {
    if (!selectedCameraId) return;

    let active = true;
    const interval = setInterval(async () => {
      if (!active || isSubmitting) return;
      try {
        const evalRes = await api.evaluateRtspFrame({ camera_id: selectedCameraId });
        if (active) {
          setLastEval(evalRes);
          if (evalRes.valid) {
            setCollectedSamples(prev => Math.min(prev + 1, 5));
          }
        }
      } catch {
        // Stream frame not ready or camera offline
      }
    }, 1800);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [selectedCameraId, isSubmitting]);

  const handleManualEvaluate = async () => {
    if (!selectedCameraId) return;
    setIsEvaluating(true);
    setErrorMsg(null);
    try {
      const res = await api.evaluateRtspFrame({ camera_id: selectedCameraId });
      setLastEval(res);
      if (res.valid) {
        setCollectedSamples(prev => Math.min(prev + 1, 5));
      } else {
        setErrorMsg(res.reason || 'Frame quality does not meet enrollment criteria.');
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Failed to analyze frame from camera.');
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleSubmitEnroll = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!event) return;
    if (!name.trim()) {
      setErrorMsg('Full Name is required for enrollment.');
      return;
    }
    if (!isOwner) {
      setErrorMsg('Security restriction: Only authenticated Owner can execute RTSP enrollment.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await api.enrollUnknownFromRtsp(event.id, {
        name: name.trim(),
        employee_id: employeeId.trim() || undefined,
        department: department.trim() || 'General',
        role: role.trim() || 'Employee',
        camera_id: selectedCameraId,
      });

      setSuccessMsg(`Successfully enrolled "${name.trim()}" directly from RTSP camera! Biometric index synchronized.`);
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1600);
    } catch (err: any) {
      setErrorMsg(err.message || 'Direct RTSP Enrollment failed. Please retry.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!event) return null;

  const streamUrl = selectedCameraId ? api.getCameraStreamUrl(selectedCameraId) : null;
  const targetCamera = cameras.find(c => c.id === selectedCameraId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-[#0d1527] border border-slate-700/80 rounded-3xl shadow-2xl shadow-cyan-950/50 flex flex-col">
        {/* Header */}
        <div className="sticky top-0 bg-[#0d1527]/95 backdrop-blur-md px-6 py-4 border-b border-slate-800 flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center shadow-md shadow-cyan-600/30">
              <Camera className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white">Direct RTSP Biometric Enrollment</h3>
                <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" />
                  Owner Only
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Enroll unrecognized visitor into authoritative identity gallery directly from live RTSP stream
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/80 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6 flex-1">
          {/* Messages */}
          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span className="flex-1">{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5">
              <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-400" />
              <span className="flex-1 font-semibold">{successMsg}</span>
            </div>
          )}

          {/* Grid layout: Left = Live Stream & Quality Telemetry; Right = Form & Event context */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Col: Stream Preview & Quality Gauges (7 cols) */}
            <div className="lg:col-span-7 space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Video className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Select Active RTSP Stream</span>
                </label>
                <div className="text-xs text-slate-400">
                  {(targetCamera?.is_connected || targetCamera?.status === 'connected') ? (
                    <span className="text-emerald-400 font-mono flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                      CONNECTED
                    </span>
                  ) : (
                    <span className="text-amber-400 font-mono">CONNECTING / STANDBY</span>
                  )}
                </div>
              </div>

              {/* Camera Selector */}
              <div className="flex gap-2">
                {cameras.map(cam => (
                  <button
                    key={cam.id}
                    type="button"
                    onClick={() => setSelectedCameraId(cam.id)}
                    className={`flex-1 px-3 py-2 rounded-xl text-xs font-medium border transition-all text-left cursor-pointer ${
                      selectedCameraId === cam.id
                        ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-200'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <div className="font-semibold text-white truncate">{cam.name}</div>
                    <div className="text-[10px] text-slate-400 font-mono uppercase">{cam.camera_role || cam.mode}</div>
                  </button>
                ))}
              </div>

              {/* Live MJPEG Stream Display */}
              <div className="relative aspect-video rounded-2xl bg-black border border-slate-800 overflow-hidden flex items-center justify-center group shadow-inner">
                {streamUrl ? (
                  <img
                    src={streamUrl}
                    alt="RTSP Live Stream Preview"
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLElement).style.display = 'none';
                    }}
                  />
                ) : (
                  <div className="text-xs text-slate-500 font-mono">No active camera stream</div>
                )}

                {/* Stream Overlay HUD */}
                <div className="absolute top-2.5 left-2.5 px-2.5 py-1 rounded-md bg-black/60 backdrop-blur-sm border border-white/10 text-[11px] font-mono text-cyan-300 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  <span>RTSP REUSE: NO EXTRA SOCKETS</span>
                </div>

                {/* Quality Overlay Badge */}
                {lastEval && (
                  <div className={`absolute bottom-2.5 left-2.5 px-2.5 py-1 rounded-md backdrop-blur-sm border text-[11px] font-mono flex items-center gap-1.5 ${
                    lastEval.valid
                      ? 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300'
                      : 'bg-rose-950/80 border-rose-500/40 text-rose-300'
                  }`}>
                    {lastEval.valid ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span>QUALITY OK ({(lastEval.quality_score! * 100).toFixed(0)}%)</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                        <span>{lastEval.reason || 'POOR QUALITY'}</span>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Live Quality Diagnostics Grid */}
              <div className="p-3.5 rounded-2xl bg-slate-900/90 border border-slate-800 grid grid-cols-3 gap-3 text-center">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Detected Faces</div>
                  <div className={`text-sm font-bold font-mono mt-0.5 ${
                    lastEval?.face_count === 1 ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {lastEval ? lastEval.face_count : '—'} {lastEval?.face_count === 1 ? '✓ Single' : lastEval?.face_count ? '✗ Reject' : ''}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Sharpness (Blur)</div>
                  <div className={`text-sm font-bold font-mono mt-0.5 ${
                    (lastEval?.blur_variance || 0) >= 50 ? 'text-emerald-400' : 'text-amber-400'
                  }`}>
                    {lastEval?.blur_variance ? Math.round(lastEval.blur_variance) : '—'}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Pose OK</div>
                  <div className={`text-sm font-bold font-mono mt-0.5 ${
                    lastEval?.valid ? 'text-emerald-400' : 'text-slate-400'
                  }`}>
                    {lastEval?.valid ? '✓ Aligned' : 'Analyzing'}
                  </div>
                </div>
              </div>

              {/* Sample Collector Bar */}
              <div className="flex items-center justify-between px-4 py-3 rounded-2xl bg-slate-900/60 border border-slate-800">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-200">Collected High-Quality Frames:</span>
                  <span className="text-xs font-mono font-bold text-cyan-300">{collectedSamples}/5</span>
                </div>
                <button
                  type="button"
                  onClick={handleManualEvaluate}
                  disabled={isEvaluating}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${isEvaluating ? 'animate-spin' : ''}`} />
                  <span>Check Frame</span>
                </button>
              </div>
            </div>

            {/* Right Col: Personnel Form & Snapshot (5 cols) */}
            <div className="lg:col-span-5 space-y-4">
              {/* Event Context Card */}
              <div className="p-3.5 rounded-2xl bg-slate-900/80 border border-slate-800 flex items-center gap-3">
                {event.snapshot_path ? (
                  <img
                    src={`${BASE_URL.replace('/api', '')}/${event.snapshot_path.replace(/^\//, '')}`}
                    alt="Captured Unknown"
                    className="w-16 h-16 rounded-xl object-cover border border-slate-700 shrink-0"
                  />
                ) : (
                  <div className="w-16 h-16 rounded-xl bg-slate-800 flex items-center justify-center text-slate-500 shrink-0">
                    <User className="w-7 h-7" />
                  </div>
                )}
                <div className="min-w-0">
                  <div className="text-[10px] text-slate-400 font-mono uppercase">Reference Snapshot</div>
                  <div className="text-xs font-bold text-white truncate">Unknown #{event.id}</div>
                  <div className="text-[11px] text-slate-400 truncate">{event.camera_name} ({event.camera_role})</div>
                  <div className="text-[10px] text-slate-500">{event.time_str || (event.detected_at ? new Date(event.detected_at).toLocaleTimeString() : '')}</div>
                </div>
              </div>

              {/* Personnel Registration Form */}
              <form onSubmit={handleSubmitEnroll} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Full Name *
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <User className="w-4 h-4" />
                    </div>
                    <input
                      type="text"
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Michael Vance"
                      className="w-full pl-9 pr-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-all"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Employee ID (Optional)
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <Badge className="w-4 h-4" />
                    </div>
                    <input
                      type="text"
                      value={employeeId}
                      onChange={(e) => setEmployeeId(e.target.value)}
                      placeholder="e.g. EMP-1049"
                      className="w-full pl-9 pr-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-all"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Department
                    </label>
                    <input
                      type="text"
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                      placeholder="e.g. Engineering"
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-all"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      Role / Position
                    </label>
                    <input
                      type="text"
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      placeholder="e.g. Security Lead"
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-all"
                    />
                  </div>
                </div>

                {/* Owner Authority Notice */}
                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-300/90 leading-relaxed">
                  <span className="font-bold text-amber-200">Authority Verification:</span> This action registers an authoritative identity directly into the production FAISS biometric database and assigns permanent attendance privileges.
                </div>

                {/* Submit button */}
                <button
                  type="submit"
                  disabled={isSubmitting || !isOwner}
                  className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-blue-600 via-cyan-600 to-blue-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold text-xs uppercase tracking-wider shadow-lg shadow-cyan-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                      <span>Generating 512-D ArcFace Biometrics...</span>
                    </>
                  ) : (
                    <>
                      <ShieldCheck className="w-4 h-4" />
                      <span>Confirm & Enroll from RTSP</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
