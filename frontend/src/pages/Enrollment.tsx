import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  CheckCircle2, AlertCircle, RefreshCw, ArrowRight, UserPlus, Check, Sparkles
} from 'lucide-react';
import { api } from '../services/api';
import { Person } from '../types';
import { useNavigate } from 'react-router-dom';

// ── Pose definitions ────────────────────────────────────────────────────────
const ENROLLMENT_POSES = [
  { step: 1, label: 'Front',     dir: 'front',     text: 'Look directly at the camera',       emoji: '😐' },
  { step: 2, label: 'Left',      dir: 'left',       text: 'Turn your head slightly LEFT',       emoji: '←' },
  { step: 3, label: 'Right',     dir: 'right',      text: 'Turn your head slightly RIGHT',      emoji: '→' },
  { step: 4, label: 'Up',        dir: 'up',         text: 'Tilt your head slightly UP',         emoji: '↑' },
  { step: 5, label: 'Down',      dir: 'down',       text: 'Tilt your head slightly DOWN',       emoji: '↓' },
  { step: 6, label: 'Far Left',  dir: 'far_left',   text: 'Turn your head further LEFT',        emoji: '⟵' },
  { step: 7, label: 'Far Right', dir: 'far_right',  text: 'Turn your head further RIGHT',       emoji: '⟶' },
];

// ── Arc positions for the 7 poses around the oval (matches true physical 3D direction) ──
// Coordinate system: 0° = top (12 o'clock), 90° = right (3 o'clock), 180° = bottom (6 o'clock), 270° = left (9 o'clock)
const ARC_SEGMENTS: [number, number][] = [
  [295, 335],  // 1: Front    – upper-left (look straight ahead)
  [250, 290],  // 2: Left     – mid-left (9 o'clock)
  [70,  110],  // 3: Right    – mid-right (3 o'clock)
  [340,  20],  // 4: Up       – exact top (12 o'clock)
  [160, 200],  // 5: Down     – exact bottom (6 o'clock)
  [205, 245],  // 6: Far Left – lower-left (7:30)
  [115, 155],  // 7: Far Right– lower-right (4:30)
];

// ── Android-style Oval Face Ring ────────────────────────────────────────────
interface OvalRingProps {
  capturedTakes: string[];
  currentTakeIdx: number;
  statusColor: 'red' | 'yellow' | 'green';
  justCaptured: boolean;
}

const OvalFaceRing: React.FC<OvalRingProps> = ({ capturedTakes, currentTakeIdx, statusColor, justCaptured }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const cx = W / 2;
    const cy = H / 2;
    const rx = W * 0.42;   // oval x-radius
    const ry = H * 0.49;   // oval y-radius

    // ── Draw the oval path helper ──
    const ovalPoint = (angleDeg: number): [number, number] => {
      const rad = (angleDeg - 90) * Math.PI / 180;
      return [cx + rx * Math.cos(rad), cy + ry * Math.sin(rad)];
    };

    // ── Background dim oval ──
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 8;
    ctx.stroke();

    // ── Draw each arc segment ──
    ARC_SEGMENTS.forEach(([startDeg, endDeg], idx) => {
      const pose = ENROLLMENT_POSES[idx];
      const isDone = capturedTakes.includes(pose.label) || idx < currentTakeIdx;
      const isCurrent = idx === currentTakeIdx;

      let color: string;
      if (isDone) {
        color = '#22c55e';        // green – captured
      } else if (isCurrent) {
        if (statusColor === 'green') color = '#86efac';    // light green – hold still
        else if (statusColor === 'yellow') color = '#fbbf24'; // amber – close
        else color = '#f87171';                              // red – wrong position
      } else {
        color = 'rgba(255,255,255,0.12)';                    // grey – future
      }

      // Convert angle to canvas coords (0 = top, CW)
      const startRad = (startDeg - 90) * Math.PI / 180;
      const endRad   = (endDeg   - 90) * Math.PI / 180;

      // Draw arc along the oval using a sampled polyline
      ctx.beginPath();
      const steps = 40;
      let first = true;
      for (let s = 0; s <= steps; s++) {
        const t = s / steps;
        let angle = startDeg + (endDeg - startDeg) * t;
        // handle wrap-around for "Front" (330→30)
        if (startDeg > endDeg) {
          angle = startDeg + ((endDeg + 360 - startDeg) * t);
        }
        const [px, py] = ovalPoint(angle);
        if (first) { ctx.moveTo(px, py); first = false; }
        else ctx.lineTo(px, py);
      }

      ctx.strokeStyle = color;
      ctx.lineWidth = isDone ? 10 : (isCurrent ? 8 : 5);
      ctx.lineCap = 'round';
      ctx.shadowColor = isDone ? '#22c55e' : (isCurrent && statusColor === 'green' ? '#86efac' : 'transparent');
      ctx.shadowBlur = isDone || (isCurrent && statusColor === 'green') ? 14 : 0;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // ── Small dot at midpoint with step number ──
      const midDeg = startDeg > endDeg
        ? startDeg + (endDeg + 360 - startDeg) / 2
        : (startDeg + endDeg) / 2;
      const [dotX, dotY] = ovalPoint(midDeg);

      const dotR = isDone ? 14 : (isCurrent ? 13 : 10);
      ctx.beginPath();
      ctx.arc(dotX, dotY, dotR, 0, Math.PI * 2);
      ctx.fillStyle = isDone ? '#22c55e' : (isCurrent ? color : 'rgba(30,41,59,0.9)');
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = isDone ? '#ffffff' : (isCurrent ? '#fff' : 'rgba(255,255,255,0.4)');
      ctx.font = `bold ${isDone ? 11 : 10}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(isDone ? '✓' : String(idx + 1), dotX, dotY);
    });

    // ── Centre pulse when green ──
    if (statusColor === 'green' || justCaptured) {
      const pulseR = Math.min(rx, ry) * 0.35;
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, pulseR);
      grad.addColorStop(0, 'rgba(34,197,94,0.15)');
      grad.addColorStop(1, 'rgba(34,197,94,0)');
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx * 0.6, ry * 0.6, 0, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
    }
  }, [capturedTakes, currentTakeIdx, statusColor, justCaptured]);

  return (
    <canvas
      ref={canvasRef}
      width={320}
      height={360}
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ objectFit: 'contain' }}
    />
  );
};

// ── Main Component ───────────────────────────────────────────────────────────
export const Enrollment: React.FC = () => {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [enrollMode, setEnrollMode] = useState<'new' | 'existing'>('new');
  const [existingPersons, setExistingPersons] = useState<Person[]>([]);
  const [selectedPersonId, setSelectedPersonId] = useState<number | null>(null);

  const [personData, setPersonData] = useState({ name: '', person_identifier: '', department: '', role: '' });
  const [enrolledName, setEnrolledName] = useState<string>('');
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [currentTakeIdx, setCurrentTakeIdx] = useState<number>(0);
  const [capturedTakes, setCapturedTakes] = useState<string[]>([]);
  const [justCapturedTake, setJustCapturedTake] = useState<string | null>(null);

  const [detectionState, setDetectionState] = useState<{
    status: string;
    message: string;
    instruction: string;
    status_color: 'red' | 'green' | 'yellow';
    detected_bbox: number[] | null;
    face_count: number;
    hold_progress: number;
    current_yaw: number;
    current_pitch: number;
    captured: boolean;
    quality_score: number | null;
  }>({
    status: 'no_face',
    message: 'FACE NOT DETECTED',
    instruction: 'Align face inside the guide frame',
    status_color: 'red',
    detected_bbox: null,
    face_count: 0,
    hold_progress: 0.0,
    current_yaw: 0,
    current_pitch: 0,
    captured: false,
    quality_score: null
  });

  const [isCapturing, setIsCapturing] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [isEnrolling, setIsEnrolling] = useState(false);
  const [enrollError, setEnrollError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const loopTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastSoundTimeRef = useRef<number>(0);
  const isCapturingRef = useRef<boolean>(false);
  const currentTakeIdxRef = useRef<number>(0);
  const sessionIdRef = useRef<string | null>(null);
  const isCompletedRef = useRef<boolean>(false);
  const navigate = useNavigate();

  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);
  useEffect(() => { currentTakeIdxRef.current = currentTakeIdx; }, [currentTakeIdx]);
  useEffect(() => { isCompletedRef.current = isCompleted; }, [isCompleted]);

  useEffect(() => {
    api.getPersons().then(res => {
      setExistingPersons(Array.isArray(res) ? res : []);
    }).catch(console.error);
  }, []);

  // ── Sound ──
  const playSound = useCallback((type: 'success' | 'warning' | 'completed') => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      if (type === 'success') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(523.25, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(783.99, ctx.currentTime + 0.15);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); osc.stop(ctx.currentTime + 0.25);
      } else if (type === 'completed') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523.25, ctx.currentTime);
        osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.1);
        osc.frequency.setValueAtTime(783.99, ctx.currentTime + 0.2);
        osc.frequency.setValueAtTime(1046.50, ctx.currentTime + 0.3);
        gain.gain.setValueAtTime(0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); osc.stop(ctx.currentTime + 0.5);
      } else if (type === 'warning') {
        const now = Date.now();
        if (now - lastSoundTimeRef.current < 1600) return;
        lastSoundTimeRef.current = now;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(220, ctx.currentTime);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); osc.stop(ctx.currentTime + 0.2);
      }
    } catch { /* silent */ }
  }, []);

  // ── High-Speed Camera Init ──
  const startCamera = async (isRetry = false) => {
    try {
      setCameraError(null);
      // Fire camera release asynchronously in background — do not block getUserMedia!
      api.releaseCamera().catch(() => {});

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(() => {});
      }
    } catch (err: any) {
      if (!isRetry && (err.name === 'NotReadableError' || err.name === 'TrackStartError')) {
        try { await api.releaseCamera(); } catch {}
        setTimeout(() => startCamera(true), 250);
        return;
      }
      if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setCameraError("Webcam hardware was busy. Click 'Release & Retry' to unlock.");
      } else if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setCameraError("Webcam access denied. Please allow camera in your browser address bar, then retry.");
      } else {
        setCameraError(`Camera error: ${err.message || 'Device unavailable'}. Click 'Release & Retry'.`);
      }
    }
  };

  const handleRetryCamera = async () => {
    setCameraError(null);
    try { await api.releaseCamera(); } catch {}
    setTimeout(() => startCamera(true), 500);
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (loopTimerRef.current) {
      clearInterval(loopTimerRef.current);
      loopTimerRef.current = null;
    }
  };

  useEffect(() => {
    if (step === 2) startCamera();
    else stopCamera();
    return () => stopCamera();
  }, [step]);

  // ── Step 1: Start Enrollment ──
  const handleStartEnrollment = async () => {
    setIsSubmitting(true);
    try {
      let targetPersonId = selectedPersonId;
      let targetName = '';

      if (enrollMode === 'new') {
        const trimmedId = personData.person_identifier.trim();
        const trimmedName = personData.name.trim();
        if (!trimmedName || !trimmedId) return;

        const existing = existingPersons.find(
          p => p.person_identifier.trim().toLowerCase() === trimmedId.toLowerCase()
        );

        if (existing) {
          targetPersonId = existing.id;
          targetName = existing.name || trimmedName;
        } else {
          try {
            const person = await api.createPerson({
              name: trimmedName,
              person_identifier: trimmedId,
              department: personData.department?.trim() || undefined,
              role: personData.role?.trim() || undefined
            });
            targetPersonId = person.id;
            targetName = person.name;
          } catch (createErr: any) {
            const all = await api.getPersons();
            const list = Array.isArray(all) ? all : [];
            const found = list.find(
              (p: Person) => p.person_identifier.trim().toLowerCase() === trimmedId.toLowerCase()
            );
            if (found) { targetPersonId = found.id; targetName = found.name; }
            else throw createErr;
          }
        }
      } else {
        if (!selectedPersonId) return;
        const selected = existingPersons.find(p => p.id === selectedPersonId);
        targetName = selected?.name || 'Employee';
      }

      if (!targetPersonId) return;
      setEnrolledName(targetName);

      const session = await api.startEnrollment(targetPersonId);
      setSessionId(session.session_id);
      sessionIdRef.current = session.session_id;
      setCurrentTakeIdx(0);
      currentTakeIdxRef.current = 0;
      setCapturedTakes([]);
      setJustCapturedTake(null);
      setIsCompleted(false);
      isCompletedRef.current = false;
      isCapturingRef.current = false;
      setIsEnrolling(false);
      setEnrollError(null);
      setDetectionState({
        status: 'no_face',
        message: 'FACE NOT DETECTED',
        instruction: 'Look directly at camera inside the guide frame',
        status_color: 'red',
        detected_bbox: null,
        face_count: 0,
        hold_progress: 0.0,
        current_yaw: 0,
        current_pitch: 0,
        captured: false,
        quality_score: null
      });
      setStep(2);
    } catch (err: any) {
      alert(`Enrollment initialization failed: ${err.message || err}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Session & Navigation Handlers ──
  const handleBackToSelection = useCallback(() => {
    stopCamera();
    setStep(1);
    setSessionId(null);
    sessionIdRef.current = null;
    setCurrentTakeIdx(0);
    currentTakeIdxRef.current = 0;
    setCapturedTakes([]);
    setJustCapturedTake(null);
    setIsCompleted(false);
    isCompletedRef.current = false;
    isCapturingRef.current = false;
    setIsEnrolling(false);
    setEnrollError(null);
    setDetectionState({
      status: 'no_face',
      message: 'FACE NOT DETECTED',
      instruction: 'Align face inside the guide frame',
      status_color: 'red',
      detected_bbox: null,
      face_count: 0,
      hold_progress: 0.0,
      current_yaw: 0,
      current_pitch: 0,
      captured: false,
      quality_score: null
    });
  }, []);

  const handleRestartSession = useCallback(async () => {
    let targetPersonId = selectedPersonId;
    if (!targetPersonId && existingPersons.length > 0) {
      const found = existingPersons.find(p => p.name === enrolledName);
      if (found) targetPersonId = found.id;
    }
    if (!targetPersonId) {
      handleBackToSelection();
      return;
    }
    try {
      setIsSubmitting(true);
      setEnrollError(null);
      setIsEnrolling(false);
      setIsCompleted(false);
      isCompletedRef.current = false;
      isCapturingRef.current = false;
      setCurrentTakeIdx(0);
      currentTakeIdxRef.current = 0;
      setCapturedTakes([]);
      setJustCapturedTake(null);

      const session = await api.startEnrollment(targetPersonId);
      setSessionId(session.session_id);
      sessionIdRef.current = session.session_id;
      startCamera();
    } catch (err: any) {
      setEnrollError(err.message || 'Failed to start new enrollment session. Please return to Selection.');
    } finally {
      setIsSubmitting(false);
    }
  }, [selectedPersonId, existingPersons, enrolledName, handleBackToSelection]);

  // ── Manual & Automatic Finalize Enrollment ──
  const handleFinishEnrollment = useCallback(async () => {
    const sId = sessionIdRef.current;
    if (!sId) return;

    // Do not complete if no takes have been captured yet
    if (capturedTakes.length === 0 && currentTakeIdxRef.current === 0) {
      console.warn('Cannot finalize enrollment with 0 captured takes');
      return;
    }

    // Immediately stop processing frames
    if (loopTimerRef.current) {
      clearInterval(loopTimerRef.current);
      loopTimerRef.current = null;
    }

    if (isCompletedRef.current) return;
    isCompletedRef.current = true;
    setIsCompleted(true);
    setIsEnrolling(true);
    setEnrollError(null);
    playSound('completed');

    try {
      console.log("Finalizing enrollment for session:", sId);
      const compRes = await api.completeEnrollment(sId);
      console.log("Enrollment finalized successfully:", compRes);
      if (compRes && compRes.success === false) {
        throw new Error(compRes.message || 'Failed to complete enrollment');
      }
      setIsEnrolling(false);
      setStep(3);
    } catch (err: any) {
      console.error('completeEnrollment error:', err);
      // Auto-retry once
      try {
        console.log("Retrying save for session:", sId);
        const retryRes = await api.completeEnrollment(sId);
        console.log("Retry succeeded:", retryRes);
        setIsEnrolling(false);
        setStep(3);
      } catch (err2: any) {
        setIsEnrolling(false);
        const msg = err2?.message || err?.message || '';
        if (msg.toLowerCase().includes('invalid session') || msg.toLowerCase().includes('session expired') || msg.toLowerCase().includes('expired')) {
          setEnrollError('Session expired. Click "Restart Session" to begin hands-free capture.');
        } else {
          setEnrollError(msg || 'Failed to save enrollment to database. Please click "Retry Save".');
        }
      }
    }
  }, [playSound, capturedTakes.length]);

  const handleManualRetrySave = useCallback(async () => {
    const sId = sessionIdRef.current;
    if (!sId) return;
    setIsEnrolling(true);
    setEnrollError(null);
    try {
      const compRes = await api.completeEnrollment(sId);
      if (compRes && compRes.success === false) {
        throw new Error(compRes.message || 'Failed to complete enrollment');
      }
      setIsEnrolling(false);
      setStep(3);
    } catch (err: any) {
      setIsEnrolling(false);
      setEnrollError(err.message || 'Failed to save enrollment to database. Please click "Retry Save".');
    }
  }, []);

  // ── Frame Processing Loop ──
  const processEnrollmentFrame = useCallback(async () => {
    const sId = sessionIdRef.current;
    if (!videoRef.current || !canvasRef.current || !sId || isCapturingRef.current || isCompletedRef.current || isEnrolling) return;
    if (videoRef.current.readyState < 2) return;

    isCapturingRef.current = true;
    try {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const base64Data = canvas.toDataURL('image/jpeg', 0.85);
      const res = await api.submitEnrollmentFrame(sId, base64Data);

      if (res.status === 'error' || res.message === 'SESSION EXPIRED') {
        if (loopTimerRef.current) {
          clearInterval(loopTimerRef.current);
          loopTimerRef.current = null;
        }
        setIsEnrolling(false);
        setEnrollError('Session expired. Click "Restart Session" to begin hands-free 360° capture.');
        return;
      }

      const color: 'red' | 'green' | 'yellow' =
        res.status_color === 'green' ? 'green' :
        (res.status_color === 'yellow' ? 'yellow' : 'red');

      const takeIdx = currentTakeIdxRef.current;
      const curPoseDef = ENROLLMENT_POSES[takeIdx];

      setDetectionState({
        status: res.status || 'reposition',
        message: res.message || res.guidance?.message || curPoseDef?.text || 'ALIGN FACE',
        instruction: res.instruction || curPoseDef?.text || 'Follow guidance on screen',
        status_color: color,
        detected_bbox: res.detected_bbox || null,
        face_count: res.face_count || (res.detected_bbox ? 1 : 0),
        hold_progress: res.hold_progress || 0.0,
        current_yaw: res.current_yaw || 0,
        current_pitch: res.current_pitch || 0,
        captured: res.captured || false,
        quality_score: res.quality_score || null
      });

      if (color === 'red') playSound('warning');

      // ── Handle pose capture ──
      if (res.captured || res.status === 'captured') {
        const capturedLabel = curPoseDef?.label || `Angle ${takeIdx + 1}`;
        setJustCapturedTake(capturedLabel);
        setCapturedTakes(prev => prev.includes(capturedLabel) ? prev : [...prev, capturedLabel]);
        playSound('success');

        const nextTakeIdx = takeIdx + 1;
        currentTakeIdxRef.current = nextTakeIdx;
        setCurrentTakeIdx(nextTakeIdx);

        setTimeout(() => setJustCapturedTake(null), 900);
      }

      // ── Trigger completion — either all 7 done locally OR backend says completed ──
      const locallyDone = currentTakeIdxRef.current >= ENROLLMENT_POSES.length;
      const backendDone = (res.completed === true || res.status === 'completed') && currentTakeIdxRef.current > 0;

      if ((locallyDone || backendDone) && !isCompletedRef.current) {
        handleFinishEnrollment();
      }
    } catch (err: any) {
      console.error('Enrollment frame error:', err);
    } finally {
      isCapturingRef.current = false;
    }
  }, [playSound, handleFinishEnrollment, isEnrolling]);

  useEffect(() => {
    if (step === 2 && sessionId && !isCompleted) {
      const timer = setInterval(() => processEnrollmentFrame(), 300);
      loopTimerRef.current = timer;
      return () => { clearInterval(timer); loopTimerRef.current = null; };
    } else if (loopTimerRef.current) {
      clearInterval(loopTimerRef.current);
      loopTimerRef.current = null;
    }
  }, [step, sessionId, isCompleted, processEnrollmentFrame]);

  const activePose = ENROLLMENT_POSES[currentTakeIdx] || ENROLLMENT_POSES[0];
  const sc = detectionState.status_color;

  // ── colour helpers ──
  const borderColor = sc === 'green' ? 'border-emerald-500 ring-4 ring-emerald-500/20'
    : sc === 'yellow' ? 'border-amber-400 ring-4 ring-amber-400/15'
    : 'border-red-500 ring-4 ring-red-500/15';

  const msgColor = sc === 'green' ? 'text-emerald-400' : sc === 'yellow' ? 'text-amber-400' : 'text-red-400';

  const msgBg = sc === 'green'
    ? 'bg-emerald-950/80 border-emerald-500'
    : sc === 'yellow'
    ? 'bg-amber-950/80 border-amber-500'
    : 'bg-red-950/80 border-red-500';

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl">
        {/* Title */}
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2.5 bg-blue-500/10 text-blue-400 rounded-lg">
            <UserPlus className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">360° Multi-Angle Face Enrollment</h2>
            <p className="text-slate-400 text-sm">Android-style automatic hands-free capture across all 7 face angles</p>
          </div>
        </div>

        {/* Progress Steps Header */}
        <div className="grid grid-cols-3 gap-2 my-6">
          {['1. Employee Info', '2. Face Capture (0/7)', '3. Enrolled ✓'].map((label, i) => {
            const active = step >= i + 1;
            return (
              <div key={i} className={`py-2 px-3 text-xs font-semibold rounded-md border text-center transition-all ${active
                ? i === 2 ? 'bg-green-600/20 border-green-500 text-green-400'
                  : 'bg-blue-600/20 border-blue-500 text-blue-400'
                : 'bg-slate-800 border-slate-700 text-slate-500'}`}>
                {i === 1 ? `2. Face Capture (${capturedTakes.length}/7)` : label}
              </div>
            );
          })}
        </div>

        {/* ══════════════ STEP 1 ══════════════ */}
        {step === 1 && (
          <div className="space-y-5 animate-slide-in">
            {/* Mode switcher */}
            <div className="flex bg-slate-900 border border-slate-700 p-1 rounded-lg w-fit">
              {(['new', 'existing'] as const).map(mode => (
                <button key={mode} type="button" onClick={() => setEnrollMode(mode)}
                  className={`px-4 py-1.5 rounded-md text-xs font-semibold transition-all ${enrollMode === mode ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}>
                  {mode === 'new' ? '+ Register New Person' : 'Select Existing Employee'}
                </button>
              ))}
            </div>

            {enrollMode === 'new' ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { key: 'name', label: 'Full Legal Name *', placeholder: 'e.g. John Doe' },
                  { key: 'person_identifier', label: 'Employee / Person ID *', placeholder: 'e.g. EMP-101' },
                  { key: 'department', label: 'Department', placeholder: 'e.g. Security / Operations' },
                  { key: 'role', label: 'Role', placeholder: 'e.g. Officer / Staff' },
                ].map(({ key, label, placeholder }) => (
                  <div key={key}>
                    <label className="block text-sm font-medium text-slate-300 mb-1">{label}</label>
                    <input type="text" placeholder={placeholder}
                      className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-4 py-2.5 text-white focus:border-blue-500 focus:outline-none"
                      value={(personData as any)[key]}
                      onChange={e => setPersonData({ ...personData, [key]: e.target.value })} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                <label className="block text-sm font-medium text-slate-300">Choose Employee to Enroll Face</label>
                {existingPersons.length === 0 ? (
                  <div className="p-4 bg-slate-900 border border-slate-700 rounded-lg text-slate-400 text-sm">
                    No employees found. Please choose "+ Register New Person".
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-60 overflow-y-auto pr-1">
                    {existingPersons.map(p => (
                      <div key={p.id} onClick={() => setSelectedPersonId(p.id)}
                        className={`p-3 rounded-lg border cursor-pointer transition-all flex items-center justify-between ${selectedPersonId === p.id ? 'bg-blue-600/20 border-blue-500 text-white' : 'bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700'}`}>
                        <div>
                          <div className="font-semibold text-sm">{p.name}</div>
                          <div className="text-xs text-slate-400 font-mono">{p.person_identifier} • {p.department || 'General'}</div>
                        </div>
                        {selectedPersonId === p.id && <Check className="w-4 h-4 text-blue-400" />}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="p-4 bg-blue-950/30 border border-blue-800/40 rounded-lg text-xs text-blue-300 flex items-start gap-2.5">
              <Sparkles className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-white">Hands-Free 360° Enrollment: </span>
                The system will automatically guide you through all 7 face angles — like Android face unlock. Just follow the on-screen directions!
              </div>
            </div>

            <div className="flex justify-end pt-4">
              <button onClick={handleStartEnrollment}
                disabled={(enrollMode === 'new' && (!personData.name || !personData.person_identifier)) || (enrollMode === 'existing' && !selectedPersonId) || isSubmitting}
                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg font-medium transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50 flex items-center gap-2">
                {isSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
                Proceed to Camera Capture <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* ══════════════ STEP 2: LIVE CAPTURE ══════════════ */}
        {step === 2 && (
          <div className="space-y-4 animate-slide-in">
            {/* Name + captured count bar */}
            <div className="flex items-center justify-between bg-slate-900 border border-slate-800 px-4 py-2.5 rounded-xl">
              <span className="text-sm font-bold text-white">{enrolledName}</span>
              <span className="text-xs text-slate-400">
                <span className="text-emerald-400 font-bold">{capturedTakes.length}</span>/7 angles captured
              </span>
            </div>

            {/* ── Message Banner ── */}
            <div className={`rounded-xl px-5 py-3.5 border transition-all duration-200 ${msgBg}`}>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[10px] uppercase tracking-widest font-bold text-slate-400 mb-0.5">
                    Angle {Math.min(currentTakeIdx + 1, 7)} of 7 — {activePose.label}
                  </div>
                  <h3 className={`text-2xl font-black tracking-wide ${msgColor}`}>
                    {detectionState.message}
                  </h3>
                  <p className="text-slate-300 text-xs mt-1">{activePose.text}</p>
                </div>
                {/* Mini pose legend */}
                <div className="hidden md:flex items-center gap-1 flex-wrap justify-end max-w-[180px]">
                  {ENROLLMENT_POSES.map((p, i) => {
                    const done = capturedTakes.includes(p.label) || i < currentTakeIdx;
                    const cur = i === currentTakeIdx;
                    return (
                      <div key={p.label} title={p.label}
                        className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${done ? 'bg-emerald-500 text-white' : cur ? sc === 'green' ? 'bg-emerald-400 text-white ring-2 ring-white/40 animate-pulse' : sc === 'yellow' ? 'bg-amber-400 text-white ring-2 ring-white/40 animate-pulse' : 'bg-red-500 text-white ring-2 ring-white/40 animate-pulse' : 'bg-slate-800 text-slate-500 border border-slate-700'}`}>
                        {done ? '✓' : i + 1}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* ── Camera + Android-Style Oval Ring ── */}
            <div className={`relative bg-black rounded-2xl overflow-hidden border-2 transition-all ${borderColor}`}
              style={{ aspectRatio: '4/3' }}>
              {cameraError ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6 space-y-3">
                  <AlertCircle className="w-12 h-12 text-red-500 mx-auto animate-bounce" />
                  <p className="text-red-400 text-sm max-w-sm font-medium">{cameraError}</p>
                  <button onClick={handleRetryCamera}
                    className="bg-blue-600 hover:bg-blue-500 text-white px-5 py-2 rounded-lg text-sm font-semibold shadow-lg flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Release & Start Camera
                  </button>
                </div>
              ) : (
                <>
                  {/* Mirrored live video */}
                  <video ref={videoRef} playsInline muted
                    className="absolute inset-0 w-full h-full object-cover transform scale-x-[-1]" />

                  {/* ── Android-style oval ring overlay ── */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="relative w-full h-full">
                      <OvalFaceRing
                        capturedTakes={capturedTakes}
                        currentTakeIdx={currentTakeIdx}
                        statusColor={sc}
                        justCaptured={!!justCapturedTake}
                      />
                    </div>
                  </div>

                  {/* ── Direction arrow overlays ── */}
                  {(detectionState.message.includes('LEFT') || activePose.dir.includes('left')) && sc !== 'green' && !justCapturedTake && (
                    <div className="absolute left-4 top-1/2 -translate-y-1/2 flex flex-col items-center gap-1 pointer-events-none animate-bounce">
                      <div className="bg-blue-600/90 border border-blue-400 text-white px-3 py-2 rounded-xl text-sm font-black shadow-lg">
                        ← LEFT
                      </div>
                    </div>
                  )}
                  {(detectionState.message.includes('RIGHT') || activePose.dir.includes('right')) && sc !== 'green' && !justCapturedTake && (
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col items-center gap-1 pointer-events-none animate-bounce">
                      <div className="bg-blue-600/90 border border-blue-400 text-white px-3 py-2 rounded-xl text-sm font-black shadow-lg">
                        RIGHT →
                      </div>
                    </div>
                  )}
                  {(detectionState.message.includes('UP') || activePose.dir === 'up') && sc !== 'green' && !justCapturedTake && (
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 pointer-events-none animate-bounce">
                      <div className="bg-blue-600/90 border border-blue-400 text-white px-4 py-2 rounded-xl text-sm font-black shadow-lg">
                        ↑ UP
                      </div>
                    </div>
                  )}
                  {(detectionState.message.includes('DOWN') || activePose.dir === 'down') && sc !== 'green' && !justCapturedTake && (
                    <div className="absolute bottom-16 left-1/2 -translate-x-1/2 pointer-events-none animate-bounce">
                      <div className="bg-blue-600/90 border border-blue-400 text-white px-4 py-2 rounded-xl text-sm font-black shadow-lg">
                        ↓ DOWN
                      </div>
                    </div>
                  )}
                  {!detectionState.detected_bbox && (
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 pointer-events-none">
                      <div className="bg-red-700/90 border border-red-400 text-white px-4 py-2 rounded-full text-sm font-bold animate-pulse">
                        FACE NOT DETECTED
                      </div>
                    </div>
                  )}

                  {/* ── HOLD STILL green pulse ── */}
                  {sc === 'green' && !justCapturedTake && (
                    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 pointer-events-none">
                      <div className="bg-emerald-600/90 border-2 border-emerald-300 text-white px-6 py-2.5 rounded-full flex items-center gap-2 shadow-2xl animate-pulse">
                        <CheckCircle2 className="w-5 h-5" />
                        <span className="font-black text-sm uppercase">HOLD STILL • {activePose.label}</span>
                      </div>
                    </div>
                  )}

                  {/* ── Captured flash overlay ── */}
                  {justCapturedTake && (
                    <div className="absolute inset-0 bg-emerald-950/75 backdrop-blur-sm z-30 flex flex-col items-center justify-center text-center pointer-events-none">
                      <CheckCircle2 className="w-16 h-16 text-emerald-400 mb-3 animate-bounce" />
                      <h3 className="text-2xl font-black text-white">✓ {justCapturedTake}</h3>
                      <p className="text-emerald-300 text-sm mt-1 font-medium">
                        {currentTakeIdx < ENROLLMENT_POSES.length
                          ? `Next: ${ENROLLMENT_POSES[currentTakeIdx]?.text}`
                          : 'All angles captured!'}
                      </p>
                    </div>
                  )}

                  {/* ── Finalizing Enrollment Spinner Overlay ── */}
                  {isEnrolling && (
                    <div className="absolute inset-0 bg-slate-950/85 backdrop-blur-md z-40 flex flex-col items-center justify-center text-center p-6 space-y-4">
                      <RefreshCw className="w-12 h-12 text-emerald-400 animate-spin" />
                      <div>
                        <h3 className="text-xl font-black text-white">Saving 360° Facial Biometrics...</h3>
                        <p className="text-slate-400 text-xs mt-1">Generating FAISS vector indexing & SQLite employee records</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setIsEnrolling(false);
                          isCompletedRef.current = false;
                          setIsCompleted(false);
                        }}
                        className="text-xs text-slate-400 hover:text-slate-200 underline pt-2 cursor-pointer"
                      >
                        Cancel / Return to Capture
                      </button>
                    </div>
                  )}

                  {/* ── Telemetry bar ── */}
                  <div className="absolute bottom-3 left-3 bg-black/75 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 text-[11px] font-mono text-slate-300 flex items-center gap-3 pointer-events-none">
                    <div>Yaw: <span className="text-white font-bold">{detectionState.current_yaw}°</span></div>
                    <div>Pitch: <span className="text-white font-bold">{detectionState.current_pitch}°</span></div>
                    {detectionState.quality_score !== null && (
                      <div>Q: <span className="text-emerald-400 font-bold">{detectionState.quality_score}</span></div>
                    )}
                    <div className="flex items-center gap-1 text-blue-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping" />
                      Auto-scan
                    </div>
                  </div>
                </>
              )}
              <canvas ref={canvasRef} className="hidden" />
            </div>

            {/* ── Pose mini-progress (mobile) ── */}
            <div className="flex justify-center gap-2 md:hidden">
              {ENROLLMENT_POSES.map((p, i) => {
                const done = capturedTakes.includes(p.label) || i < currentTakeIdx;
                const cur = i === currentTakeIdx;
                return (
                  <div key={p.label} title={p.label}
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${done ? 'bg-emerald-500 text-white' : cur ? 'bg-blue-500 text-white ring-2 ring-blue-300 animate-pulse' : 'bg-slate-800 text-slate-500 border border-slate-700'}`}>
                    {done ? '✓' : i + 1}
                  </div>
                );
              })}
            </div>

            {/* ── Error notification if completion failed ── */}
            {enrollError && (
              <div className="p-3 bg-red-950/60 border border-red-500/60 rounded-xl flex items-center justify-between gap-3 text-red-300 text-xs animate-slide-in">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                  <span>{enrollError}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {enrollError.toLowerCase().includes('session') ? (
                    <button
                      onClick={handleRestartSession}
                      className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold transition-all shadow shrink-0"
                    >
                      Restart Session
                    </button>
                  ) : (
                    <button
                      onClick={handleManualRetrySave}
                      className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded font-bold transition-all shadow shrink-0"
                    >
                      Retry Save
                    </button>
                  )}
                  <button
                    onClick={handleBackToSelection}
                    className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-semibold transition-all shadow"
                  >
                    Back
                  </button>
                </div>
              </div>
            )}

            {/* ── Bottom Controls: Back, Manual Snap Angle, and Complete & Enroll Button ── */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
              <button 
                onClick={handleBackToSelection} 
                className="text-slate-400 hover:text-white text-xs px-3 py-2 transition-colors order-2 sm:order-1"
              >
                ← Back to Selection
              </button>

              <div className="flex items-center gap-2.5 order-1 sm:order-2 w-full sm:w-auto justify-end">
                {/* Manual Snap Angle Button */}
                {currentTakeIdx < ENROLLMENT_POSES.length && (
                  <button
                    onClick={() => {
                      const curPoseDef = ENROLLMENT_POSES[currentTakeIdx];
                      if (curPoseDef) {
                        const label = curPoseDef.label;
                        setCapturedTakes(prev => prev.includes(label) ? prev : [...prev, label]);
                        const nextIdx = currentTakeIdx + 1;
                        setCurrentTakeIdx(nextIdx);
                        currentTakeIdxRef.current = nextIdx;
                        playSound('success');
                        if (nextIdx >= ENROLLMENT_POSES.length) {
                          handleFinishEnrollment();
                        }
                      }
                    }}
                    disabled={isEnrolling}
                    className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all flex items-center gap-1.5 shadow"
                    title="Instantly capture the current angle without waiting"
                  >
                    <span>📸 Snap {activePose.label}</span>
                  </button>
                )}

                {/* Complete & Enroll Button */}
                <button
                  onClick={handleFinishEnrollment}
                  disabled={capturedTakes.length === 0 || isEnrolling}
                  className={`px-5 py-2 rounded-lg text-xs font-bold transition-all shadow-lg flex items-center gap-2 ${
                    capturedTakes.length >= 7 
                      ? 'bg-emerald-500 hover:bg-emerald-400 text-white shadow-emerald-500/30 ring-2 ring-emerald-300 ring-offset-2 ring-offset-slate-900 animate-pulse' 
                      : capturedTakes.length >= 1
                      ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-500/20'
                      : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                  }`}
                >
                  {isEnrolling ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Finalizing Enrollment...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>
                        {capturedTakes.length >= 7 
                          ? 'Complete & Save Enrollment (7/7) ✓' 
                          : capturedTakes.length >= 1
                          ? `Enroll Now (${capturedTakes.length}/7 Takes)`
                          : 'Complete Enrollment'}
                      </span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════ STEP 3: SUCCESS ══════════════ */}
        {step === 3 && (
          <div className="text-center py-12 animate-slide-in space-y-6">
            <div className="w-20 h-20 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center mx-auto ring-8 ring-emerald-500/10 shadow-xl shadow-emerald-500/20">
              <CheckCircle2 className="w-10 h-10" />
            </div>
            <div>
              <h2 className="text-2xl font-extrabold text-white">FACE ENROLLED SUCCESSFULLY</h2>
              <p className="text-slate-300 max-w-md mx-auto mt-2 text-sm">
                All 7 of 7 360° biometric takes for <strong className="text-white">{enrolledName}</strong> have been captured and stored with 512-D ArcFace in database & FAISS index.
              </p>
            </div>

            <div className="flex justify-center gap-4 pt-4">
              <button
                onClick={() => {
                  setStep(1);
                  setPersonData({ name: '', person_identifier: '', department: '', role: '' });
                  setSelectedPersonId(null);
                  setCurrentTakeIdx(0);
                  setCapturedTakes([]);
                  setIsCompleted(false);
                }}
                className="bg-slate-800 hover:bg-slate-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors">
                Enroll Another Person
              </button>
              <button onClick={() => navigate('/attendance')}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-lg shadow-emerald-500/20 flex items-center gap-2 font-semibold">
                Go to Attendance System <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
