import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Play,
  Pause,
  Edit3,
  Wifi,
  WifiOff,
  Radio,
  Sliders,
  Shield,
  Clock,
  LogIn,
  LogOut,
  MapPin,
  ExternalLink,
  UserCheck,
  Zap,
  Sparkles,
  Info,
  Power,
  Activity,
  Terminal,
  Server,
  ChevronDown,
  ChevronUp,
  RotateCw,
  Plus,
  Trash2
} from 'lucide-react';
import { api } from '../services/api';
import { RTSPCamera, RTSPCameraCreate, RTSPCameraDiagnostics } from '../types';

export const Cameras: React.FC = () => {
  const [cameras, setCameras] = useState<RTSPCamera[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Independent action states per camera mode
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [cardTestResult, setCardTestResult] = useState<Record<string, any>>({});
  const [showDiagnostics, setShowDiagnostics] = useState<Record<string, boolean>>({
    'CHECK-IN': true,
    'CHECK-OUT': true
  });

  // Stable stream keys with dynamic timestamp to ensure fresh HTTP streaming sockets
  const [streamKeys, setStreamKeys] = useState<Record<string, number>>(() => ({
    'CHECK-IN': Date.now(),
    'CHECK-OUT': Date.now() + 1
  }));

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [modalTargetMode, setModalTargetMode] = useState<'CHECK-IN' | 'CHECK-OUT'>('CHECK-IN');
  const [editingCameraId, setEditingCameraId] = useState<number | null>(null);

  // Form State
  const [formData, setFormData] = useState<RTSPCameraCreate>({
    name: '',
    rtsp_url: '',
    username: '',
    password: '',
    location: '',
    mode: 'CHECK-IN',
    enabled: true
  });

  // Modal Connection Test State
  const [isTestingConnection, setIsTestingConnection] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message?: string;
    error?: string;
    resolution?: string;
    fps?: number;
    latency_ms?: number;
    diagnostics?: RTSPCameraDiagnostics;
  } | null>(null);

  // Auto-refresh interval and lifecycle refs
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isFetchingRef = useRef<boolean>(false);
  const [isPageMounted, setIsPageMounted] = useState<boolean>(true);

  const fetchCameras = useCallback(async (isSilent: boolean = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    if (!isSilent) setIsRefreshing(true);
    try {
      const res = await api.getCameras(false);
      if (res && res.items) {
        setCameras(res.items);
      }
      setErrorMessage(null);
    } catch (err: any) {
      if (!isSilent) {
        setErrorMessage(err.message || 'Failed to load RTSP cameras');
      }
    } finally {
      setIsLoading(false);
      if (!isSilent) setIsRefreshing(false);
      isFetchingRef.current = false;
    }
  }, []);

  // Handle Tab Switch and Window Minimize/Restore Auto-Reconnection
  useEffect(() => {
    const handleVisibilityOrFocus = () => {
      if (document.visibilityState === 'visible') {
        // Tab restored or window focused: refresh stream keys to reattach MJPEG sockets immediately
        setStreamKeys({
          'CHECK-IN': Date.now(),
          'CHECK-OUT': Date.now() + 1
        });
        fetchCameras(true);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityOrFocus);
    window.addEventListener('focus', handleVisibilityOrFocus);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
      window.removeEventListener('focus', handleVisibilityOrFocus);
    };
  }, [fetchCameras]);

  useEffect(() => {
    setIsPageMounted(true);
    fetchCameras(false);

    // Poll status every 3 seconds for real-time telemetry & rolling FPS updates
    pollTimerRef.current = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      fetchCameras(true);
    }, 3000);

    return () => {
      setIsPageMounted(false);
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [fetchCameras]);

  // Open Configure Modal for specific mode
  const handleOpenConfigureFor = (mode: 'CHECK-IN' | 'CHECK-OUT') => {
    const existing = cameras.find(c => c.mode === mode);
    setModalTargetMode(mode);
    setTestResult(null);

    if (existing) {
      setEditingCameraId(existing.id);
      setFormData({
        name: existing.name,
        rtsp_url: existing.rtsp_url,
        username: existing.username || '',
        password: '',
        location: existing.location || (mode === 'CHECK-IN' ? 'Main Entrance' : 'Turnstile Exit Gate'),
        mode: mode,
        enabled: existing.enabled
      });
    } else {
      setEditingCameraId(null);
      setFormData({
        name: mode === 'CHECK-IN' ? 'Entrance Check-In Camera' : 'Exit Check-Out Camera',
        rtsp_url: '',
        username: '',
        password: '',
        location: mode === 'CHECK-IN' ? 'Main Entrance' : 'Turnstile Exit Gate',
        mode: mode,
        enabled: true
      });
    }
    setIsModalOpen(true);
  };

  // Independent Manual Connect
  const handleConnectCamera = async (mode: 'CHECK-IN' | 'CHECK-OUT') => {
    setActionLoading(prev => ({ ...prev, [`connect_${mode}`]: true }));
    try {
      if (mode === 'CHECK-IN') {
        await api.connectCheckinCamera();
      } else {
        await api.connectCheckoutCamera();
      }
      await fetchCameras(true);
    } catch (err: any) {
      alert(`Connect error: ${err.message || 'Failed to connect camera'}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [`connect_${mode}`]: false }));
    }
  };

  // Independent Manual Disconnect
  const handleDisconnectCamera = async (mode: 'CHECK-IN' | 'CHECK-OUT') => {
    setActionLoading(prev => ({ ...prev, [`disconnect_${mode}`]: true }));
    try {
      if (mode === 'CHECK-IN') {
        await api.disconnectCheckinCamera();
      } else {
        await api.disconnectCheckoutCamera();
      }
      await fetchCameras(true);
    } catch (err: any) {
      alert(`Disconnect error: ${err.message || 'Failed to disconnect camera'}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [`disconnect_${mode}`]: false }));
    }
  };

  // Independent Manual Reconnect
  const handleReconnectCamera = async (mode: 'CHECK-IN' | 'CHECK-OUT') => {
    setActionLoading(prev => ({ ...prev, [`reconnect_${mode}`]: true }));
    try {
      if (mode === 'CHECK-IN') {
        await api.reconnectCheckinCamera();
      } else {
        await api.reconnectCheckoutCamera();
      }
      // Force browser MJPEG player to drop stale connection and reconnect immediately
      setStreamKeys(prev => ({ ...prev, [mode]: Date.now() }));
      await fetchCameras(true);
    } catch (err: any) {
      alert(`Reconnect error: ${err.message || 'Failed to trigger reconnection'}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [`reconnect_${mode}`]: false }));
    }
  };

  // Toggle Camera Enable/Disable
  const handleToggleCamera = async (mode: 'CHECK-IN' | 'CHECK-OUT', camera?: RTSPCamera) => {
    if (!camera) return;
    setActionLoading(prev => ({ ...prev, [`toggle_${mode}`]: true }));
    try {
      if (mode === 'CHECK-IN') {
        await api.toggleCheckinCamera();
      } else {
        await api.toggleCheckoutCamera();
      }
      await fetchCameras(true);
    } catch (err: any) {
      alert(`Toggle error: ${err.message || 'Failed to toggle camera state'}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [`toggle_${mode}`]: false }));
    }
  };

  // Delete Camera
  const handleDeleteCamera = async (mode: 'CHECK-IN' | 'CHECK-OUT', camera?: RTSPCamera) => {
    if (!camera) return;
    if (!window.confirm(`Are you sure you want to delete ${camera.name}? Attendance tracking for this gate will be paused.`)) {
      return;
    }
    setActionLoading(prev => ({ ...prev, [`delete_${mode}`]: true }));
    try {
      if (mode === 'CHECK-IN') {
        await api.deleteCheckinCamera();
      } else {
        await api.deleteCheckoutCamera();
      }
      if (isModalOpen) setIsModalOpen(false);
      await fetchCameras(false);
    } catch (err: any) {
      alert(`Delete error: ${err.message || 'Failed to delete camera'}`);
    } finally {
      setActionLoading(prev => ({ ...prev, [`delete_${mode}`]: false }));
    }
  };

  // Reload Feed with fresh key
  const handleReloadStreams = () => {
    setStreamKeys({
      'CHECK-IN': Date.now(),
      'CHECK-OUT': Date.now() + 1
    });
    fetchCameras(false);
  };

  // Independent Card-Level Test Connection
  const handleCardTestConnection = async (mode: 'CHECK-IN' | 'CHECK-OUT', url?: string) => {
    if (!url) {
      alert('No RTSP URL configured to test');
      return;
    }
    setActionLoading(prev => ({ ...prev, [`test_${mode}`]: true }));
    setCardTestResult(prev => ({ ...prev, [mode]: null }));
    try {
      const res = await api.testCameraConnection({ rtsp_url: url });
      setCardTestResult(prev => ({ ...prev, [mode]: res }));
    } catch (err: any) {
      setCardTestResult(prev => ({
        ...prev,
        [mode]: {
          success: false,
          error: err.message || 'Connection test failed',
          message: err.message
        }
      }));
    } finally {
      setActionLoading(prev => ({ ...prev, [`test_${mode}`]: false }));
    }
  };

  // Modal Test Connection
  const handleTestConnection = async () => {
    if (!formData.rtsp_url.trim()) {
      alert('Please enter an RTSP URL first');
      return;
    }
    if (formData.rtsp_url.trim() === '0' || formData.rtsp_url.trim().length <= 2) {
      alert('Local device indexes (e.g. 0) are not allowed. Please enter an actual RTSP stream URL (e.g. rtsp://...).');
      return;
    }

    setIsTestingConnection(true);
    setTestResult(null);
    try {
      const res = await api.testCameraConnection({
        rtsp_url: formData.rtsp_url,
        username: formData.username || undefined,
        password: formData.password || undefined
      });
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        success: false,
        error: err.message || 'Failed to connect to RTSP stream'
      });
    } finally {
      setIsTestingConnection(false);
    }
  };

  // Save / Submit Camera
  const handleSaveCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.rtsp_url.trim()) {
      alert('Camera Name and RTSP URL are required');
      return;
    }
    if (formData.rtsp_url.trim() === '0' || formData.rtsp_url.trim().length <= 2) {
      alert('Local device indexes (e.g. 0) are prohibited. Please provide a valid IP camera stream URL (rtsp://...).');
      return;
    }

    try {
      if (modalTargetMode === 'CHECK-IN') {
        await api.configureCheckinCamera(formData);
      } else {
        await api.configureCheckoutCamera(formData);
      }
      setIsModalOpen(false);
      setStreamKeys(prev => ({ ...prev, [modalTargetMode]: Date.now() }));
      fetchCameras(false);
    } catch (err: any) {
      alert(err.message || 'Error saving camera');
    }
  };

  // Identify Check-In and Check-Out cameras
  const checkinCamera = cameras.find(c => c.mode === 'CHECK-IN');
  const checkoutCamera = cameras.find(c => c.mode === 'CHECK-OUT');

  // Helper renderer for each camera section
  const renderCameraSection = (
    mode: 'CHECK-IN' | 'CHECK-OUT',
    camera: RTSPCamera | undefined
  ) => {
    const isCheckin = mode === 'CHECK-IN';
    const title = isCheckin ? 'Check-In Camera' : 'Check-Out Camera';
    const defaultName = isCheckin ? 'Entrance RTSP Camera' : 'Exit RTSP Camera';
    const defaultLocation = isCheckin ? 'Main Entrance Gate' : 'Turnstile Exit Gate';
    const streamUrl = isCheckin ? api.getCheckinStreamUrl() : api.getCheckoutStreamUrl();
    const liveStatus = camera?.live_status || camera?.status || 'disconnected';
    const isEnabled = camera ? camera.enabled : false;
    const actualFps = camera?.actual_fps || 0;
    const isReceiving = camera?.is_receiving_frames || false;
    const isConnected = liveStatus === 'connected' || liveStatus === 'connected_no_frames';
    const isConnecting = liveStatus === 'connecting';
    const isReconnecting = liveStatus === 'reconnecting';
    const isOffline = !isConnected && !isConnecting && !isReconnecting;
    const recentEvents = camera?.recent_events || [];
    const latestEvent = recentEvents.length > 0 ? recentEvents[0] : null;
    const diag = camera?.diagnostics || {};
    const testRes = cardTestResult[mode];
    const isDiagOpen = showDiagnostics[mode] !== false;

    // Accurate status pill logic
    let statusLabel = 'OFFLINE';
    let statusBadgeClass = 'bg-red-500/10 text-red-400 border-red-500/20';
    let dotClass = 'bg-red-400';

    if (camera && !camera.enabled) {
      statusLabel = 'DISABLED';
      statusBadgeClass = 'bg-slate-800 text-slate-400 border-slate-700';
      dotClass = 'bg-slate-500';
    } else if (isConnected) {
      if (isReceiving && actualFps > 0) {
        statusLabel = `LIVE ${actualFps.toFixed(1)} FPS`;
        statusBadgeClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
        dotClass = 'bg-emerald-400 animate-pulse';
      } else {
        statusLabel = 'CONNECTED (BUFFERING)';
        statusBadgeClass = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
        dotClass = 'bg-amber-400';
      }
    } else if (isConnecting) {
      statusLabel = 'CONNECTING...';
      statusBadgeClass = 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 animate-pulse';
      dotClass = 'bg-cyan-400 animate-ping';
    } else if (isReconnecting) {
      statusLabel = `RECONNECTING (${camera?.reconnect_attempt || 1})`;
      statusBadgeClass = 'bg-amber-500/10 text-amber-400 border-amber-500/20 animate-pulse';
      dotClass = 'bg-amber-400 animate-ping';
    }

    return (
      <div className="bg-[#0a0f1d] border border-slate-800 rounded-2xl overflow-hidden flex flex-col shadow-2xl transition-all duration-200 hover:border-slate-700">
        {/* Section Header */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3 min-w-0">
            <div className="relative shrink-0">
              <div className={`p-2.5 rounded-xl border ${
                isConnected && isReceiving
                  ? isCheckin ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-purple-500/10 border-purple-500/30 text-purple-400'
                  : isReconnecting || isConnecting
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                  : 'bg-red-500/10 border-red-500/30 text-red-400'
              }`}>
                {isCheckin ? <LogIn className="w-5 h-5" /> : <LogOut className="w-5 h-5" />}
              </div>
              {isConnected && isReceiving && (
                <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                  <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isCheckin ? 'bg-emerald-400' : 'bg-purple-400'} opacity-75`}></span>
                  <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isCheckin ? 'bg-emerald-500' : 'bg-purple-500'}`}></span>
                </span>
              )}
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base font-bold text-white tracking-wide truncate">
                  {camera?.name || defaultName}
                </h2>
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                  isCheckin
                    ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/40'
                    : 'bg-purple-950/60 text-purple-400 border-purple-800/40'
                }`}>
                  {mode} ONLY
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5 truncate">
                <MapPin className="w-3 h-3 text-slate-500 shrink-0" />
                <span className="shrink-0">{camera?.location || defaultLocation}</span>
                <span className="text-slate-600">•</span>
                <span className="font-mono text-cyan-400/90 truncate" title={camera?.redacted_url || camera?.rtsp_url}>
                  {camera?.redacted_url || camera?.rtsp_url || 'No RTSP URL configured'}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Real-time Status Badge */}
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-lg flex items-center gap-1.5 border font-mono ${statusBadgeClass}`}>
              <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`} />
              <span className="hidden sm:inline">{statusLabel}</span>
              <span className="sm:hidden">{isConnected ? 'LIVE' : isReconnecting || isConnecting ? 'CON' : 'OFF'}</span>
            </span>

            <button
              onClick={() => handleOpenConfigureFor(mode)}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition"
              title={`Configure ${title} RTSP URL`}
            >
              <Sliders className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Live Stream Viewport (15 FPS MJPEG) with Stable Key */}
        <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden border-b border-slate-800/80 group">
          {isPageMounted && camera && camera.enabled ? (
            <img
              key={`${mode}-${streamKeys[mode] || 1}`}
              src={`${streamUrl}?k=${streamKeys[mode] || 1}`}
              alt={camera.name}
              className="w-full h-full object-contain select-none"
              onError={() => {
                setTimeout(() => {
                  if (isPageMounted) {
                    setStreamKeys(prev => ({ ...prev, [mode]: Date.now() }));
                  }
                }, 1200);
              }}
            />
          ) : camera && !camera.enabled ? (
            <div className="flex flex-col items-center justify-center text-slate-500 space-y-3 p-6 text-center">
              <div className="p-4 rounded-2xl bg-slate-800 text-slate-400 border border-slate-700">
                <Power className="w-8 h-8" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-slate-300">
                  {camera.name} is Disabled
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  This camera stream is paused. Click Enable to resume.
                </p>
              </div>
              <button
                onClick={() => handleToggleCamera(mode, camera)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-md transition"
              >
                <Power className="w-3.5 h-3.5" />
                <span>Enable Camera</span>
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-slate-500 space-y-3 p-6 text-center">
              <div className={`p-4 rounded-2xl ${isCheckin ? 'bg-emerald-500/10 text-emerald-400' : 'bg-purple-500/10 text-purple-400'} border border-slate-800`}>
                {isCheckin ? <LogIn className="w-8 h-8" /> : <LogOut className="w-8 h-8" />}
              </div>
              <div>
                <h4 className="text-sm font-bold text-slate-300">
                  {`No ${title} Configured`}
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  Enter your phone/camera RTSP stream URL to start automated {isCheckin ? 'Check-In' : 'Check-Out'}
                </p>
              </div>
              <button
                onClick={() => handleOpenConfigureFor(mode)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md transition"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>Configure RTSP URL</span>
              </button>
            </div>
          )}

          {/* High-Tech HUD Scanline Overlay */}
          <div className="absolute inset-0 pointer-events-none bg-gradient-to-b from-transparent via-cyan-500/[0.02] to-transparent bg-[length:100%_4px]" />

          {/* Stream Watermark / Info Pill */}
          <div className="absolute bottom-2.5 left-2.5 flex items-center gap-2 pointer-events-none flex-wrap">
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/80 backdrop-blur-md text-slate-300 border border-slate-700/60 flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${actualFps > 0 ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
              <span>STR: {(camera?.stream_fps ?? actualFps).toFixed(1)} FPS</span>
              <span className="text-slate-600">|</span>
              <span>DISP: {(camera?.display_fps ?? (actualFps > 0 ? 15 : 0)).toFixed(1)} FPS</span>
              <span className="text-slate-600">|</span>
              <span className="text-cyan-400">AI: {(camera?.ai_fps ?? 0).toFixed(1)} FPS</span>
            </span>
            {camera?.active_persons ? (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/80 backdrop-blur-md text-emerald-300 border border-emerald-700/60 flex items-center gap-1">
                <UserCheck className="w-3 h-3" />
                {camera.active_persons} in view
              </span>
            ) : null}
          </div>
        </div>

        {/* Independent Manual Camera Controls Toolbar */}
        <div className="px-4 py-2.5 bg-[#090e1c] border-b border-slate-800/80 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Connect / Disconnect Buttons */}
            {camera && camera.enabled && (
              isOffline ? (
                <button
                  onClick={() => handleConnectCamera(mode)}
                  disabled={actionLoading[`connect_${mode}`]}
                  className="text-xs px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                >
                  <Power className="w-3.5 h-3.5" />
                  <span>{actionLoading[`connect_${mode}`] ? 'Connecting...' : 'Connect'}</span>
                </button>
              ) : (
                <button
                  onClick={() => handleDisconnectCamera(mode)}
                  disabled={actionLoading[`disconnect_${mode}`]}
                  className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-red-900/40 text-slate-300 hover:text-red-300 border border-slate-700 hover:border-red-700 transition flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Power className="w-3.5 h-3.5 text-red-400" />
                  <span>{actionLoading[`disconnect_${mode}`] ? 'Disconnecting...' : 'Disconnect'}</span>
                </button>
              )
            )}

            {/* Reconnect Button */}
            {camera && camera.enabled && (
              <button
                onClick={() => handleReconnectCamera(mode)}
                disabled={actionLoading[`reconnect_${mode}`]}
                className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center gap-1.5 disabled:opacity-50"
                title="Force immediate reconnection attempt"
              >
                <RotateCw className={`w-3.5 h-3.5 text-amber-400 ${actionLoading[`reconnect_${mode}`] ? 'animate-spin' : ''}`} />
                <span>Reconnect</span>
              </button>
            )}

            {/* Test Connection Button */}
            {camera && (
              <button
                onClick={() => handleCardTestConnection(mode, camera?.rtsp_url)}
                disabled={actionLoading[`test_${mode}`] || !camera?.rtsp_url}
                className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 transition flex items-center gap-1.5 disabled:opacity-50"
                title="Probe TCP port and frame grab without interrupting stream"
              >
                <Zap className={`w-3.5 h-3.5 ${actionLoading[`test_${mode}`] ? 'animate-bounce text-amber-400' : ''}`} />
                <span>{actionLoading[`test_${mode}`] ? 'Testing...' : 'Test Connection'}</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Enable / Disable Toggle */}
            {camera && (
              <button
                onClick={() => handleToggleCamera(mode, camera)}
                disabled={actionLoading[`toggle_${mode}`]}
                className={`text-xs px-2.5 py-1.5 rounded-lg border font-semibold transition flex items-center gap-1.5 ${
                  camera.enabled
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20'
                    : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700'
                }`}
                title={camera.enabled ? 'Click to Disable Camera' : 'Click to Enable Camera'}
              >
                <Power className="w-3.5 h-3.5" />
                <span>{camera.enabled ? 'Enabled' : 'Disabled'}</span>
              </button>
            )}

            {/* Edit URL */}
            <button
              onClick={() => handleOpenConfigureFor(mode)}
              className="text-xs px-2.5 py-1.5 rounded-lg bg-blue-600/20 border border-blue-500/40 text-blue-400 hover:bg-blue-600/30 transition flex items-center gap-1.5 font-medium"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit URL</span>
            </button>

            {/* Delete Camera */}
            {camera && (
              <button
                onClick={() => handleDeleteCamera(mode, camera)}
                disabled={actionLoading[`delete_${mode}`]}
                className="text-xs p-1.5 rounded-lg bg-slate-800 hover:bg-red-950/60 text-slate-400 hover:text-red-400 border border-slate-700 hover:border-red-800/40 transition"
                title="Delete Camera"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Card Test Result Inline Banner (if triggered) */}
        {testRes && (
          <div className={`mx-4 mt-3 p-3 rounded-xl border text-xs flex items-start justify-between gap-3 ${
            testRes.success
              ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
              : 'bg-red-950/40 border-red-500/30 text-red-300'
          }`}>
            <div className="flex items-start gap-2">
              {testRes.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              )}
              <div>
                <span className="font-bold">{testRes.success ? 'RTSP Test Succeeded' : 'RTSP Test Failed'}: </span>
                <span>{testRes.message || testRes.error}</span>
                {testRes.diagnostics?.hint && (
                  <p className="mt-1 text-[11px] text-slate-400 font-mono">
                    Hint: {testRes.diagnostics.hint}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => setCardTestResult(prev => ({ ...prev, [mode]: null }))}
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
        )}

        {/* Diagnostic Telemetry Panel */}
        <div className="p-4 bg-[#080d1a] space-y-3">
          {/* Diagnostics Accordion Header */}
          <div
            onClick={() => setShowDiagnostics(prev => ({ ...prev, [mode]: !isDiagOpen }))}
            className="flex items-center justify-between cursor-pointer select-none group"
          >
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-bold text-slate-200 uppercase tracking-wide group-hover:text-white transition">
                Connection Diagnostics
              </span>
            </div>
            <div className="flex items-center gap-1 text-[10px] text-slate-400">
              <span>{isDiagOpen ? 'Hide' : 'Show Details'}</span>
              {isDiagOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </div>
          </div>

          {/* Diagnostic Details Grid */}
          {isDiagOpen && (
            <div className="space-y-2.5">
              <div className="p-3 rounded-xl bg-[#0d1424] border border-slate-800 text-xs font-mono space-y-2">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-[11px]">
                  <div>
                    <span className="text-slate-500 block text-[10px]">RTSP HOST</span>
                    <span className="text-slate-200 font-bold">{diag.host || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">RTSP PORT</span>
                    <span className="text-slate-200 font-bold">{diag.port || 8554}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">RTSP PATH</span>
                    <span className="text-cyan-400 font-bold">{diag.path || '/live'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">STREAM FPS (INCOMING)</span>
                    <span className={`font-bold ${(camera?.stream_fps ?? actualFps) > 0 ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {(camera?.stream_fps ?? actualFps).toFixed(1)} FPS
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">DISPLAY FPS (RENDERED)</span>
                    <span className="font-bold text-cyan-400">
                      {(camera?.display_fps ?? (actualFps > 0 ? 15.0 : 0.0)).toFixed(1)} FPS
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">AI INFERENCE FPS</span>
                    <span className="font-bold text-purple-400">
                      {(camera?.ai_fps ?? diag.ai_fps ?? 0.0).toFixed(1)} FPS
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">AVG INFERENCE TIME</span>
                    <span className="font-bold text-amber-300">
                      {camera?.avg_inference_ms ? `${camera.avg_inference_ms.toFixed(0)} ms` : (diag.avg_inference_ms ? `${diag.avg_inference_ms.toFixed(0)} ms` : '—')}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">PIPELINE LATENCY</span>
                    <span className="font-bold text-emerald-300">
                      {camera?.latency_ms ? `${camera.latency_ms.toFixed(0)} ms` : (diag.latency_ms ? `${diag.latency_ms.toFixed(0)} ms` : '—')}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">DROPPED (STALE) FRAMES</span>
                    <span className="text-slate-300 font-bold">
                      {camera?.dropped_frames ?? diag.dropped_frames ?? 0}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">FRAME QUEUE SIZE</span>
                    <span className="text-emerald-400 font-bold">
                      {camera?.queue_size ?? diag.queue_size ?? (actualFps > 0 ? 1 : 0)} (Latest-Frame)
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">TRACKED FACES</span>
                    <span className="text-cyan-300 font-bold">
                      {diag.faces_detected ?? camera?.active_persons ?? 0} in view
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">CONFIRMED / TOO SMALL</span>
                    <span className="text-slate-300 font-bold">
                      <span className="text-emerald-400">{diag.faces_recognized ?? 0}</span> / <span className="text-amber-400">{diag.too_small_count ?? 0}</span>
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">RECONNECT COUNT</span>
                    <span className="text-amber-400 font-bold">
                      {camera?.reconnect_attempt || diag.reconnect_count || 0} attempts
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">LAST FRAME RECEIVED</span>
                    <span className="text-slate-300">
                      {camera?.last_frame_time ? new Date(camera.last_frame_time).toLocaleTimeString() : (diag.last_frame && diag.last_frame !== 'Never' ? new Date(diag.last_frame).toLocaleTimeString() : 'Never')}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">BACKEND LOCAL IP</span>
                    <span className="text-blue-300 font-bold">
                      {diag.backend_local_ip || '192.168.0.191'}
                    </span>
                  </div>
                </div>

                {/* Last Error Field */}
                {diag.last_error && (
                  <div className="pt-1.5 border-t border-slate-800/80 text-[11px]">
                    <span className="text-red-400 font-bold">Last Error: </span>
                    <span className="text-red-300 break-all">{diag.last_error}</span>
                  </div>
                )}

                {/* Redacted URL */}
                <div className="pt-1.5 border-t border-slate-800/80 text-[11px]">
                  <span className="text-slate-500">RTSP Stream: </span>
                  <span className="text-cyan-300/90 break-all">
                    {diag.redacted_url || camera?.redacted_url || camera?.rtsp_url || 'None'}
                  </span>
                </div>

                {/* Diagnostic Guidance / Subnet Hint */}
                {diag.hint && (
                  <div className="mt-2 p-2.5 rounded-lg bg-amber-950/40 border border-amber-700/50 text-[11px] text-amber-200 font-sans">
                    <strong className="text-amber-300 font-bold">Network Diagnostic: </strong>
                    <span>{diag.hint}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Last Detected Attendance Subject */}
          {latestEvent ? (
            <div className="p-3 rounded-xl bg-[#0f172a] border border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-[10px] uppercase font-mono tracking-wider text-slate-400">Last Attendance Event</p>
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-bold text-white">{latestEvent.employee_name}</h4>
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                    latestEvent.employee_name === 'Unknown'
                      ? 'bg-red-950/50 text-red-400 border-red-800/40'
                      : isCheckin
                      ? 'bg-emerald-950/50 text-emerald-400 border-emerald-800/40'
                      : 'bg-purple-950/50 text-purple-400 border-purple-800/40'
                  }`}>
                    {latestEvent.action}
                  </span>
                </div>
              </div>

              <div className="text-right">
                <span className="text-[10px] font-mono text-slate-400 block">{latestEvent.time}</span>
                {latestEvent.score && (
                  <span className="text-xs font-bold font-mono text-cyan-400">
                    {Math.round(parseFloat(latestEvent.score) * 100)}% Match
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div className="py-2.5 px-3 rounded-xl bg-[#0f172a]/60 border border-dashed border-slate-800/80 text-center">
              <p className="text-xs text-slate-500">
                Awaiting face detection on {isCheckin ? 'Check-In' : 'Check-Out'} stream...
              </p>
            </div>
          )}

          {/* Footer Link */}
          <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between">
            <span className="text-[11px] text-slate-500 font-mono">
              ArcFace 512-D • Attendance Logged Live
            </span>

            <Link
              to="/attendance"
              className="text-xs text-cyan-400 hover:text-cyan-300 font-medium flex items-center gap-1"
            >
              <span>View Attendance Log →</span>
            </Link>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto animate-fade-in">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-800/80 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-blue-600/20 to-cyan-500/10 border border-blue-500/30 text-blue-400 shadow-lg shadow-blue-500/10">
              <Radio className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-black tracking-wide text-white">
                  RTSP CAMERAS
                </h1>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono font-bold">
                  CHECK-IN & CHECK-OUT
                </span>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30 font-mono font-bold">
                  INDEPENDENT STREAMS
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Two independent RTSP streams (Phone 1 → Check-In, Phone 2 → Check-Out). Laptop webcam is strictly for Enrollment.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Add RTSP Camera */}
          <button
            onClick={() => handleOpenConfigureFor('CHECK-IN')}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white text-xs font-bold shadow-lg shadow-blue-500/20 transition"
          >
            <Plus className="w-4 h-4" />
            <span>Add RTSP Camera</span>
          </button>

          <Link
            to="/attendance"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs font-semibold text-slate-300 hover:text-white transition"
          >
            <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Attendance Page</span>
          </Link>

          <button
            onClick={handleReloadStreams}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs font-semibold text-slate-300 hover:text-white transition active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-blue-400' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Network Diagnostic & Help Banner */}
      <div className="bg-[#0b1120] border border-blue-500/20 rounded-xl p-4 flex items-start gap-3.5">
        <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 shrink-0 mt-0.5">
          <Info className="w-5 h-5" />
        </div>
        <div className="space-y-1 text-xs">
          <h4 className="font-bold text-slate-200">RTSP Connection Troubleshooting Guide</h4>
          <p className="text-slate-400 leading-relaxed">
            • <strong>Backend Server IP:</strong> <code className="text-cyan-400">192.168.0.191</code> on your local Wi-Fi subnet <code className="text-slate-300">192.168.0.x</code>.<br />
            • <strong>Phones on Same Wi-Fi:</strong> Ensure both phones are connected to this same Wi-Fi network and keep their RTSP Camera apps open and awake.<br />
            • <strong>IP Address Changes:</strong> If your phone disconnects or reconnects, its DHCP IP may change. Check the IP shown on your phone's screen and click <strong>[Change RTSP URL]</strong> to update it.<br />
            • <strong>Independent Operation:</strong> Disconnecting or reconnecting Phone 1 will never affect Phone 2.
          </p>
        </div>
      </div>

      {/* Main Two Clearly Separated Camera Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Section 1: Check-In Camera */}
        {renderCameraSection('CHECK-IN', checkinCamera)}

        {/* Section 2: Check-Out Camera */}
        {renderCameraSection('CHECK-OUT', checkoutCamera)}
      </div>

      {/* Configure Camera Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#0f172a] border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className={`p-2 rounded-lg ${modalTargetMode === 'CHECK-IN' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-purple-500/10 text-purple-400'}`}>
                  {modalTargetMode === 'CHECK-IN' ? <LogIn className="w-5 h-5" /> : <LogOut className="w-5 h-5" />}
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">
                    Configure {modalTargetMode === 'CHECK-IN' ? 'Check-In Camera (Entrance)' : 'Check-Out Camera (Exit)'}
                  </h3>
                  <p className="text-xs text-slate-400">Set RTSP stream URL and network credentials</p>
                </div>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <form onSubmit={handleSaveCamera} className="p-5 space-y-4">
              {/* Camera Name */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Camera Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder={modalTargetMode === 'CHECK-IN' ? 'Entrance Check-In Camera' : 'Exit Check-Out Camera'}
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* RTSP Stream URL */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  RTSP Stream URL <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="rtsp://192.168.0.172:8554/live"
                  value={formData.rtsp_url}
                  onChange={(e) => setFormData({ ...formData, rtsp_url: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-sm text-white font-mono text-xs focus:outline-none focus:border-blue-500"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Example: <code className="text-cyan-400">rtsp://192.168.0.172:8554/live</code>. Laptop webcam is strictly prohibited.
                </p>
              </div>

              {/* Credentials Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">Username (Optional)</label>
                  <input
                    type="text"
                    placeholder="admin"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Password (Optional)
                    {editingCameraId && <span className="text-[10px] text-slate-500 ml-1 font-normal">(keep empty to preserve)</span>}
                  </label>
                  <input
                    type="password"
                    placeholder="••••••••"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Location */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">Camera Location</label>
                <input
                  type="text"
                  placeholder={modalTargetMode === 'CHECK-IN' ? 'Main Entrance Gate' : 'Turnstile Exit Gate'}
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Test Connection Button & Result */}
              <div className="pt-2 border-t border-slate-800/80">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400">Verify Stream Connection</span>
                  <button
                    type="button"
                    onClick={handleTestConnection}
                    disabled={isTestingConnection || !formData.rtsp_url.trim()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition disabled:opacity-50"
                  >
                    <Zap className={`w-3.5 h-3.5 ${isTestingConnection ? 'animate-bounce text-amber-400' : 'text-amber-400'}`} />
                    <span>{isTestingConnection ? 'Testing Socket & Frame...' : 'Test Connection'}</span>
                  </button>
                </div>

                {testResult && (
                  <div className={`p-3 rounded-xl border text-xs ${
                    testResult.success
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                      : 'bg-red-500/10 border-red-500/30 text-red-300'
                  }`}>
                    <div className="flex items-center gap-2 font-bold mb-1">
                      {testResult.success ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-red-400" />}
                      <span>{testResult.success ? 'Stream Reachable ✓' : 'Connection Failed'}</span>
                    </div>
                    <p className="text-[11px] opacity-90 leading-relaxed">
                      {testResult.message || testResult.error}
                    </p>
                    {testResult.diagnostics?.hint && (
                      <p className="mt-1 text-[11px] text-slate-300 font-mono">
                        Hint: {testResult.diagnostics.hint}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Form Actions */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                <div>
                  {editingCameraId && (
                    <button
                      type="button"
                      onClick={() => {
                        const existing = cameras.find(c => c.id === editingCameraId);
                        if (existing) handleDeleteCamera(modalTargetMode, existing);
                      }}
                      className="px-3.5 py-2 rounded-xl bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/40 text-xs font-semibold transition flex items-center gap-1.5"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Delete Camera</span>
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-xs font-bold text-white shadow-lg shadow-blue-500/30 transition"
                  >
                    Save {modalTargetMode === 'CHECK-IN' ? 'Check-In' : 'Check-Out'} Camera
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
