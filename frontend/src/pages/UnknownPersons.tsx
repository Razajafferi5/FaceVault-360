import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  UserPlus,
  Trash2,
  RefreshCw,
  Eye,
  Camera,
  Clock,
  Calendar,
  AlertTriangle,
  Lock,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Filter,
  Check,
  X,
  ShieldCheck
} from 'lucide-react';
import { api, BASE_URL } from '../services/api';
import { UnknownPersonEvent, UnknownPersonStats } from '../types';
import { useAuth } from '../context/AuthContext';
import { RtspEnrollModal } from '../components/unknowns/RtspEnrollModal';


export const UnknownPersons: React.FC = () => {
  const navigate = useNavigate();
  const [events, setEvents] = useState<UnknownPersonEvent[]>([]);
  const [stats, setStats] = useState<UnknownPersonStats>({
    total_today: 0,
    pending_count: 0,
    approved_count: 0,
    denied_count: 0,
    enrolled_count: 0
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const { user: authUser, isOwner: authIsOwner } = useAuth();
  const [currentUser, setCurrentUser] = useState<any>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [cameraFilter, setCameraFilter] = useState<string>('all');
  const [dateFilter, setDateFilter] = useState<string>(new Date().toISOString().split('T')[0]);

  // Modals & Action States
  const [selectedSnapshot, setSelectedSnapshot] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<number | null>(null);
  const [enrollModalEvent, setEnrollModalEvent] = useState<UnknownPersonEvent | null>(null);
  const [rtspEnrollModalEvent, setRtspEnrollModalEvent] = useState<UnknownPersonEvent | null>(null);

  const isOwner = authIsOwner || currentUser?.is_owner === true || currentUser?.role?.toLowerCase() === 'owner';


  // Load current authenticated user details
  const loadUser = useCallback(async () => {
    try {
      const user = await api.getMe();
      setCurrentUser(user);
    } catch (e) {
      console.warn('Could not load user details:', e);
    }
  }, []);

  // Load events and today stats
  const loadData = useCallback(async () => {
    try {
      setIsRefreshing(true);
      const [eventsResp, statsResp] = await Promise.all([
        api.getUnknownPersons({
          limit: 100,
          date: dateFilter === 'all' ? undefined : dateFilter,
          status: statusFilter === 'all' ? undefined : statusFilter,
          camera_role: cameraFilter === 'all' ? undefined : cameraFilter
        }),
        api.getUnknownStats()
      ]);

      setEvents(eventsResp.items || []);
      setStats(statsResp);
    } catch (err: any) {
      console.error('Failed to load unknown persons data:', err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [dateFilter, statusFilter, cameraFilter]);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh every 5 seconds for live visitor detection
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadData();
    }, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadData]);

  // Actions
  const handleApprove = async (event: UnknownPersonEvent) => {
    if (!isOwner) {
      alert('Access Denied: Only Syed Raza Abbas (Owner) has authorization to approve visitors.');
      return;
    }
    setActionInProgress(event.id);
    try {
      await api.approveUnknownPerson(event.id);
      await loadData();
    } catch (err: any) {
      alert(`Approval failed: ${err.message || err}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDeny = async (event: UnknownPersonEvent) => {
    if (!isOwner) {
      alert('Access Denied: Only Syed Raza Abbas (Owner) has authorization to deny visitors.');
      return;
    }
    setActionInProgress(event.id);
    try {
      await api.denyUnknownPerson(event.id);
      await loadData();
    } catch (err: any) {
      alert(`Denial failed: ${err.message || err}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDelete = async (event: UnknownPersonEvent) => {
    if (!isOwner) {
      alert('Access Denied: Only Syed Raza Abbas (Owner) has authorization to delete unknown logs.');
      return;
    }
    if (!confirm(`Permanently delete unknown person record #${event.id} and snapshot?`)) return;

    setActionInProgress(event.id);
    try {
      await api.deleteUnknownPerson(event.id);
      setEvents((prev) => prev.filter((item) => item.id !== event.id));
      await loadData();
    } catch (err: any) {
      alert(`Delete failed: ${err.message || err}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleEnrollRedirect = (event: UnknownPersonEvent) => {
    // Closes confirmation modal and navigates to enrollment
    setEnrollModalEvent(null);
    navigate('/enroll');
  };

  const getSnapshotFullUrl = (url?: string | null) => {
    if (!url) return '';
    if (url.startsWith('http')) return url;
    // In dev mode, prepend backend origin http://127.0.0.1:8000
    const origin = typeof window !== 'undefined' && window.location.port === '5173'
      ? `http://${window.location.hostname}:8000`
      : '';
    return `${origin}${url}`;
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <ShieldAlert className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
                Unknown Visitors & Access Approval
                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono border border-amber-500/30">
                  OWNER ONLY
                </span>
              </h1>
              <p className="text-sm text-slate-400">
                Live facial detection log for unrecognized visitors across Check-In and Check-Out cameras
              </p>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#111827] border border-slate-800 text-xs text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-slate-700 bg-slate-800 text-amber-500 focus:ring-0"
            />
            <span>Auto-refresh (5s)</span>
          </label>

          <button
            onClick={loadData}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Role Authorization Notice Banner */}
      <div
        className={`p-4 rounded-xl border flex items-center justify-between gap-3 text-sm transition-all ${
          isOwner
            ? 'bg-gradient-to-r from-emerald-950/40 via-slate-900 to-amber-950/20 border-emerald-500/30 text-emerald-300'
            : 'bg-gradient-to-r from-slate-900 to-blue-950/30 border-slate-800 text-slate-300'
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-lg ${
              isOwner ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-800 text-slate-400'
            }`}
          >
            {isOwner ? <Sparkles className="w-5 h-5" /> : <Lock className="w-5 h-5" />}
          </div>
          <div>
            <div className="font-semibold text-white flex items-center gap-2">
              {isOwner ? (
                <>
                  <span>Authenticated as Owner: Syed Raza Abbas</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono">
                    FULL ACCESS
                  </span>
                </>
              ) : (
                <>
                  <span>Viewing as Staff: {currentUser?.name || 'Authorized Operator'}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 font-mono">
                    READ ONLY
                  </span>
                </>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {isOwner
                ? 'You have complete authorization to Approve visitor entry, Deny entry, Enroll unknown faces, or delete log records.'
                : 'Approval and Denial controls are strictly restricted to Syed Raza Abbas (Owner). Direct API calls by non-owners are rejected with HTTP 403 Forbidden.'}
            </p>
          </div>
        </div>

        <div className="hidden sm:flex items-center gap-2 font-mono text-xs text-slate-400">
          <span>Role:</span>
          <span className="px-2 py-1 rounded bg-black/40 border border-slate-800 text-white uppercase font-bold">
            {currentUser?.role || 'Staff'}
          </span>
        </div>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-[#0f172a]/90 border border-slate-800 shadow-lg relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Today's Unknowns</span>
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Camera className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 text-3xl font-black text-white">{stats.total_today}</div>
          <p className="text-xs text-slate-500 mt-1">Total unrecognized faces detected today</p>
        </div>

        <div className="p-5 rounded-2xl bg-[#0f172a]/90 border border-amber-500/30 shadow-lg shadow-amber-500/5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-400">Awaiting Owner Review</span>
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 text-3xl font-black text-amber-300">{stats.pending_count}</div>
          <p className="text-xs text-amber-400/80 mt-1">Pending approval or denial action</p>
        </div>

        <div className="p-5 rounded-2xl bg-[#0f172a]/90 border border-emerald-500/30 shadow-lg shadow-emerald-500/5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">Allowed Entry</span>
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 text-3xl font-black text-emerald-400">{stats.approved_count}</div>
          <p className="text-xs text-emerald-400/80 mt-1">Approved for single visitor access</p>
        </div>

        <div className="p-5 rounded-2xl bg-[#0f172a]/90 border border-red-500/30 shadow-lg shadow-red-500/5 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-red-400">Denied Access</span>
            <div className="p-2 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20">
              <XCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 text-3xl font-black text-red-400">{stats.denied_count}</div>
          <p className="text-xs text-red-400/80 mt-1">Rejected by Owner</p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="p-4 rounded-xl bg-[#0f172a]/80 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        {/* Status Filters */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <span className="text-xs font-semibold text-slate-400 mr-1 flex items-center gap-1">
            <Filter className="w-3.5 h-3.5" /> Status:
          </span>
          {['all', 'PENDING', 'APPROVED', 'DENIED', 'ENROLLED'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                statusFilter === st
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {st === 'all' ? 'All Records' : st}
            </button>
          ))}
        </div>

        {/* Camera & Date Filter */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-700 text-xs">
            <Camera className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={cameraFilter}
              onChange={(e) => setCameraFilter(e.target.value)}
              className="bg-transparent text-slate-200 border-none outline-none text-xs cursor-pointer"
            >
              <option value="all">All Cameras</option>
              <option value="CHECK-IN">Check-In Camera</option>
              <option value="CHECK-OUT">Check-Out Camera</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-700 text-xs">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <input
              type="date"
              value={dateFilter === 'all' ? '' : dateFilter}
              onChange={(e) => setDateFilter(e.target.value || 'all')}
              className="bg-transparent text-slate-200 border-none outline-none text-xs"
            />
            {dateFilter !== 'all' && (
              <button
                onClick={() => setDateFilter('all')}
                className="text-[10px] text-blue-400 hover:underline ml-1"
              >
                All Dates
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Visitor Events Grid */}
      {loading ? (
        <div className="p-16 text-center text-slate-400 bg-[#0f172a] border border-slate-800 rounded-2xl flex flex-col items-center justify-center">
          <RefreshCw className="w-8 h-8 animate-spin text-amber-400 mb-3" />
          <p className="font-semibold text-white">Loading unknown person event records...</p>
        </div>
      ) : events.length === 0 ? (
        <div className="p-16 text-center text-slate-400 bg-[#0f172a] border border-slate-800 rounded-2xl space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-slate-800/80 flex items-center justify-center mx-auto text-slate-500">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-white">No Unknown Persons Detected</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            When an unrecognized person walks in front of either Check-In or Check-Out RTSP camera,
            an automated snapshot is captured and recorded here for owner review.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {events.map((event) => {
            const isApproved = event.access_status === 'APPROVED';
            const isDenied = event.access_status === 'DENIED';
            const isEnrolled = event.access_status === 'ENROLLED';
            const isPending = event.access_status === 'PENDING';
            const isCurrentActing = actionInProgress === event.id;

            return (
              <div
                key={event.id}
                className={`rounded-2xl border transition-all overflow-hidden flex flex-col bg-[#0f172a] ${
                  isPending
                    ? 'border-amber-500/40 shadow-lg shadow-amber-500/5 hover:border-amber-500/60'
                    : isApproved
                    ? 'border-emerald-500/30'
                    : isDenied
                    ? 'border-red-500/30'
                    : 'border-slate-800'
                }`}
              >
                {/* Card Top / Snapshot & Badges */}
                <div className="p-4 flex gap-4 items-start">
                  {/* Snapshot Thumbnail */}
                  <div
                    onClick={() => event.snapshot_url && setSelectedSnapshot(getSnapshotFullUrl(event.snapshot_url))}
                    className="w-28 h-28 rounded-xl bg-slate-900 border border-slate-700/80 relative overflow-hidden shrink-0 cursor-pointer group shadow-inner"
                  >
                    {event.snapshot_url ? (
                      <>
                        <img
                          src={getSnapshotFullUrl(event.snapshot_url)}
                          alt={`Unknown Face #${event.id}`}
                          className="w-full h-full object-cover transition-transform group-hover:scale-110"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
                          <Eye className="w-5 h-5" />
                        </div>
                      </>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-slate-500 text-[10px] p-2 text-center">
                        <Camera className="w-6 h-6 mb-1 opacity-50" />
                        <span>No Snapshot</span>
                      </div>
                    )}

                    {/* Camera Mode Pill Overlay */}
                    <span
                      className={`absolute bottom-1 left-1 text-[9px] font-mono font-bold px-1.5 py-0.5 rounded shadow ${
                        event.camera_role === 'CHECK-IN'
                          ? 'bg-blue-600 text-white'
                          : 'bg-purple-600 text-white'
                      }`}
                    >
                      {event.camera_role}
                    </span>
                  </div>

                  {/* Metadata Info */}
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-slate-400">ID #{event.id}</span>
                        {(event.detection_count && event.detection_count > 1) ? (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                            {event.detection_count} detections
                          </span>
                        ) : null}
                      </div>

                      {/* Access Status Badge */}
                      {isPending && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping"></span>
                          Pending Review
                        </span>
                      )}
                      {isApproved && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                          <CheckCircle className="w-3 h-3" />
                          Approved
                        </span>
                      )}
                      {isDenied && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/40">
                          <XCircle className="w-3 h-3" />
                          Denied
                        </span>
                      )}
                      {isEnrolled && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/40">
                          <Check className="w-3 h-3" />
                          Enrolled
                        </span>
                      )}
                    </div>

                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-bold text-white truncate">
                        Unidentified Visitor
                      </h4>
                      {event.duration_seconds && event.duration_seconds > 0 ? (
                        <span className="text-[10px] font-mono text-cyan-400 font-semibold bg-cyan-950/40 px-1.5 py-0.5 rounded border border-cyan-800/40">
                          Stay: {event.duration_seconds < 60 ? `${event.duration_seconds}s` : `${Math.floor(event.duration_seconds / 60)}m ${event.duration_seconds % 60}s`}
                        </span>
                      ) : null}
                    </div>

                    <div className="space-y-1 text-xs text-slate-400">
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                        <span className="truncate">
                          {event.last_seen_time_str && event.last_seen_time_str !== (event.first_seen_time_str || event.time_str) ? (
                            <span>{event.first_seen_time_str || event.time_str} → {event.last_seen_time_str}</span>
                          ) : (
                            <span>{event.time_str} ({event.date_str})</span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Camera className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                        <span className="truncate">{event.camera_name}</span>
                      </div>
                    </div>

                    {/* Face Detection & Quality Confidence */}
                    <div className="pt-1 flex items-center gap-2">
                      <div className="flex-1 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-blue-500 to-cyan-400 h-full rounded-full"
                          style={{ width: `${Math.min(100, Math.round(event.face_confidence * 100))}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-mono text-cyan-400 font-semibold">
                        {(event.face_confidence * 100).toFixed(0)}% Face
                      </span>
                    </div>
                  </div>
                </div>

                {/* Audit & Decision Log Details */}
                {(isApproved || isDenied) && (
                  <div className="px-4 py-2 bg-black/30 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
                    <span>
                      {isApproved ? 'Approved by' : 'Denied by'}:{' '}
                      <strong className="text-slate-200">{event.approved_by_name || 'Syed Raza Abbas'}</strong>
                    </span>
                    <span className="font-mono text-slate-500">
                      {event.approved_at ? new Date(event.approved_at).toLocaleTimeString() : ''}
                    </span>
                  </div>
                )}

                {/* Enrollment Audit Details */}
                {isEnrolled && (
                  <div className="px-4 py-2 bg-blue-950/20 border-t border-slate-800/80 text-[11px] text-blue-300 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Method: <strong className="font-mono text-cyan-300">{event.enrollment_method || 'WEBCAM'}</strong></span>
                    </span>
                    <span className="text-slate-400">
                      By: <strong className="text-slate-200">{event.enrolled_by || 'Owner'}</strong>
                    </span>
                  </div>
                )}

                {/* Card Action Buttons (Footer) */}
                <div className="mt-auto p-3 bg-slate-950/60 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2">
                  {isOwner ? (
                    <>
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Approve Button */}
                        {isPending && (
                          <button
                            onClick={() => handleApprove(event)}
                            disabled={isCurrentActing}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-md shadow-emerald-600/20 disabled:opacity-50"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>Allow Entry</span>
                          </button>
                        )}

                        {/* Deny Button */}
                        {isPending && (
                          <button
                            onClick={() => handleDeny(event)}
                            disabled={isCurrentActing}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-600/80 hover:bg-red-600 text-white text-xs font-bold transition-all disabled:opacity-50"
                          >
                            <X className="w-3.5 h-3.5" />
                            <span>Deny</span>
                          </button>
                        )}

                        {/* Direct RTSP Enroll Button (Owner Only) */}
                        {!isEnrolled && (
                          <button
                            onClick={() => setRtspEnrollModalEvent(event)}
                            disabled={isCurrentActing}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold shadow-md shadow-cyan-600/20 transition-all cursor-pointer"
                            title="Directly enroll visitor from RTSP camera samples"
                          >
                            <Camera className="w-3.5 h-3.5" />
                            <span>Enroll via RTSP</span>
                          </button>
                        )}

                        {/* Webcam Enrollment Button */}
                        {!isEnrolled && (
                          <button
                            onClick={() => setEnrollModalEvent(event)}
                            disabled={isCurrentActing}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium transition-all"
                            title="Register face using laptop webcam (Multi-Angle 360°)"
                          >
                            <UserPlus className="w-3.5 h-3.5 text-blue-400" />
                            <span>Webcam 360°</span>
                          </button>
                        )}
                      </div>

                      {/* Delete Event Button */}
                      <button
                        onClick={() => handleDelete(event)}
                        disabled={isCurrentActing}
                        title="Delete unknown person record"
                        className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors ml-auto cursor-pointer"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </>
                  ) : (
                    /* Non-Owner View-Only Notice */
                    <div className="w-full flex items-center justify-between text-xs text-slate-500">
                      <span className="flex items-center gap-1 text-[11px]">
                        <Lock className="w-3.5 h-3.5 text-slate-600" />
                        Approval requires Owner permission
                      </span>
                      <span className="text-[10px] text-slate-600 font-mono">View Only</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Snapshot Lightbox / Fullscreen Modal */}
      {selectedSnapshot && (
        <div
          onClick={() => setSelectedSnapshot(null)}
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 cursor-pointer"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="max-w-2xl w-full bg-[#0f172a] border border-slate-800 rounded-2xl overflow-hidden shadow-2xl relative"
          >
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Camera className="w-4 h-4 text-cyan-400" />
                Captured Face Snapshot
              </h3>
              <button
                onClick={() => setSelectedSnapshot(null)}
                className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-6 flex items-center justify-center bg-black/50">
              <img
                src={selectedSnapshot}
                alt="Captured Snapshot"
                className="max-h-[70vh] rounded-xl object-contain border border-slate-800 shadow-2xl"
              />
            </div>
          </div>
        </div>
      )}

      {/* Webcam Enrollment Confirmation Modal */}
      {enrollModalEvent && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-[#0f172a] border border-blue-500/40 rounded-2xl p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30">
                <UserPlus className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Enroll Unidentified Visitor</h3>
                <p className="text-xs text-slate-400">Identity Enrollment Workflow</p>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-blue-950/30 border border-blue-500/30 text-xs text-blue-200 space-y-2">
              <p className="font-semibold flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-cyan-400 shrink-0" />
                High-Quality Multi-Angle 360° Webcam Enrollment
              </p>
              <p className="text-slate-300 leading-relaxed">
                To guarantee strict recognition accuracy, RTSP security camera frame snapshots are{' '}
                <strong>never</strong> used as enrollment biometric embeddings.
              </p>
              <p className="text-slate-400">
                Proceeding will take you to the interactive Enrollment workstation to capture 5 distinct
                high-resolution angles using the laptop webcam.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setEnrollModalEvent(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleEnrollRedirect(enrollModalEvent)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-lg shadow-blue-500/20"
              >
                <span>Launch Webcam Enrollment</span>
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Direct RTSP Enrollment Modal (Owner Only) */}
      {rtspEnrollModalEvent && (
        <RtspEnrollModal
          event={rtspEnrollModalEvent}
          onClose={() => setRtspEnrollModalEvent(null)}
          onSuccess={loadData}
        />
      )}
    </div>
  );
};

