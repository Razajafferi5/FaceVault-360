import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import {
  Clock,
  Calendar,
  CheckCircle2,
  AlertCircle,
  User,
  ShieldCheck,
  Video,
  ArrowUpRight,
  ArrowDownLeft,
  Timer,
  RefreshCw,
  Sparkles
} from 'lucide-react';
import { Link } from 'react-router-dom';

export const StaffDashboard: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{
    success: boolean;
    date: string;
    employee_id: number | null;
    employee_name: string;
    status: string;
    first_check_in: string | null;
    last_check_out: string | null;
    total_duration_minutes: number;
    formatted_duration: string;
    sessions_count: number;
    records: any[];
  } | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());

  const fetchTodayData = async () => {
    try {
      setLoading(true);
      const res = await api.getMyTodayAttendance();
      setData(res);
    } catch (e) {
      console.error('Failed to load staff attendance today:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTodayData();
    const clockInterval = setInterval(() => {
      setCurrentTime(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(clockInterval);
  }, []);

  const isCheckedIn = data?.status === 'CHECKED_IN';
  const isCheckedOut = data?.status === 'CHECKED_OUT';

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Welcome & Banner */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-blue-900/40 via-cyan-900/20 to-slate-900/60 border border-blue-500/20 p-6 md:p-8 backdrop-blur-xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/10 rounded-full filter blur-3xl pointer-events-none -mr-20 -mt-20" />
        
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-mono">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>STAFF ACCESS PORTAL</span>
            </div>
            <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
              Welcome back, <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400">{user?.full_name || user?.username}</span>
            </h1>
            <p className="text-sm text-slate-400 max-w-xl">
              Your biometric presence is continuously validated at entrances. View your today's check-in/out records, sessions, and duration below.
            </p>
          </div>

          {/* Clock & Refresh */}
          <div className="flex flex-col items-end gap-3 shrink-0">
            <div className="text-right">
              <div className="text-2xl font-mono font-bold text-white tracking-widest">{currentTime}</div>
              <div className="text-xs text-slate-400 flex items-center gap-1.5 justify-end mt-0.5">
                <Calendar className="w-3 h-3 text-cyan-400" />
                <span>{data?.date || new Date().toLocaleDateString()}</span>
              </div>
            </div>
            <button
              onClick={fetchTodayData}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh Status</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Status Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Presence Status */}
        <div className="rounded-2xl bg-[#0b1329] border border-slate-800/80 p-5 space-y-3 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Current Status</span>
            <span className="relative flex h-3 w-3">
              {isCheckedIn ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-3 w-3 bg-slate-600" />
              )}
            </span>
          </div>

          <div className="pt-1">
            <div className={`text-xl font-bold font-mono ${
              isCheckedIn
                ? 'text-emerald-400'
                : isCheckedOut
                  ? 'text-cyan-400'
                  : 'text-slate-400'
            }`}>
              {isCheckedIn
                ? 'CHECKED IN (ON-SITE)'
                : isCheckedOut
                  ? 'CHECKED OUT'
                  : 'NOT CHECKED IN'}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {isCheckedIn
                ? 'Your active session is ongoing'
                : isCheckedOut
                  ? 'Completed current work session'
                  : 'No attendance marked yet today'}
            </p>
          </div>
        </div>

        {/* First Check-In */}
        <div className="rounded-2xl bg-[#0b1329] border border-slate-800/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">First Check-In</span>
            <ArrowDownLeft className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="pt-1">
            <div className="text-xl font-bold font-mono text-white">
              {data?.first_check_in || '--:-- --'}
            </div>
            <p className="text-xs text-slate-500 mt-1">Entrance arrival timestamp</p>
          </div>
        </div>

        {/* Last Check-Out */}
        <div className="rounded-2xl bg-[#0b1329] border border-slate-800/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Last Check-Out</span>
            <ArrowUpRight className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="pt-1">
            <div className="text-xl font-bold font-mono text-white">
              {data?.last_check_out || '--:-- --'}
            </div>
            <p className="text-xs text-slate-500 mt-1">Exit departure timestamp</p>
          </div>
        </div>

        {/* Total Working Time */}
        <div className="rounded-2xl bg-[#0b1329] border border-slate-800/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Total Work Time</span>
            <Timer className="w-4 h-4 text-amber-400" />
          </div>
          <div className="pt-1">
            <div className="text-xl font-bold font-mono text-amber-300">
              {data?.formatted_duration || '0m'}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {data?.sessions_count || 0} session(s) today
            </p>
          </div>
        </div>
      </div>

      {/* Today's Attendance Session Breakdown */}
      <div className="rounded-2xl bg-[#0b1329] border border-slate-800/80 p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-base font-bold text-white">Today's Attendance Sessions</h2>
            <p className="text-xs text-slate-400">
              Individual check-in and check-out intervals captured for your profile
            </p>
          </div>
          <Link
            to="/my-attendance"
            className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
          >
            <span>View Full History</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {loading ? (
          <div className="py-12 flex justify-center items-center text-slate-400 text-sm">
            <RefreshCw className="w-5 h-5 animate-spin mr-2 text-cyan-400" />
            Loading attendance records...
          </div>
        ) : !data?.records || data.records.length === 0 ? (
          <div className="py-12 text-center text-slate-400 space-y-2">
            <AlertCircle className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-sm">No attendance sessions recorded for you today yet.</p>
            <p className="text-xs text-slate-500">
              Walk in front of the RTSP entrance camera or use the attendance kiosk to record your presence.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-mono uppercase">
                  <th className="py-3 px-4">Session #</th>
                  <th className="py-3 px-4">Check-In Time</th>
                  <th className="py-3 px-4">Check-Out Time</th>
                  <th className="py-3 px-4">Camera / Location</th>
                  <th className="py-3 px-4">Duration</th>
                  <th className="py-3 px-4">Match Score</th>
                  <th className="py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {data.records.map((rec, idx) => (
                  <tr key={rec.id || idx} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-300">Session {idx + 1}</td>
                    <td className="py-3 px-4 text-emerald-400 font-bold">
                      {rec.check_in_time || rec.time || '--'}
                    </td>
                    <td className="py-3 px-4 text-cyan-400 font-bold">
                      {rec.check_out_time || (
                        <span className="text-amber-400 animate-pulse">In Progress...</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-300">{rec.camera_name || 'RTSP Entrance'}</td>
                    <td className="py-3 px-4 text-amber-300">
                      {rec.formatted_duration || rec.duration || '--'}
                    </td>
                    <td className="py-3 px-4 text-slate-400">
                      {rec.match_score ? `${(rec.match_score * 100).toFixed(1)}%` : '--'}
                    </td>
                    <td className="py-3 px-4">
                      {rec.check_out_time ? (
                        <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[10px]">
                          Completed
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 text-[10px]">
                          Open Session
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quick Navigation Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link
          to="/live"
          className="p-5 rounded-2xl bg-gradient-to-br from-blue-900/30 to-slate-900 border border-blue-500/20 hover:border-blue-500/40 transition-all group cursor-pointer block"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 group-hover:scale-105 transition-transform">
                <Video className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white group-hover:text-blue-300 transition-colors">
                  Live Camera Stream
                </h3>
                <p className="text-xs text-slate-400">Watch the live entrance RTSP recognition feed</p>
              </div>
            </div>
            <ArrowUpRight className="w-4 h-4 text-slate-400 group-hover:text-blue-300 transition-colors" />
          </div>
        </Link>

        <Link
          to="/profile"
          className="p-5 rounded-2xl bg-gradient-to-br from-cyan-900/30 to-slate-900 border border-cyan-500/20 hover:border-cyan-500/40 transition-all group cursor-pointer block"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 group-hover:scale-105 transition-transform">
                <User className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white group-hover:text-cyan-300 transition-colors">
                  My Profile & Credentials
                </h3>
                <p className="text-xs text-slate-400">View enrolled employee ID and department metadata</p>
              </div>
            </div>
            <ArrowUpRight className="w-4 h-4 text-slate-400 group-hover:text-cyan-300 transition-colors" />
          </div>
        </Link>
      </div>
    </div>
  );
};

