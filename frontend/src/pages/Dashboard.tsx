import React, { useEffect, useState, useRef } from 'react';
import { 
  Users, UserCheck, UserX, Activity, ArrowRight, RefreshCw, 
  Scan, Shield, Sparkles, Eye, CheckCircle2, AlertTriangle, 
  Maximize2, Radar, Cpu, Compass
} from 'lucide-react';
import { StatCard } from '../components/ui/StatCard';
import { StatusBadge } from '../components/ui/StatusBadge';
import { EntryChart } from '../components/charts/EntryChart';
import { AuthPieChart } from '../components/charts/AuthPieChart';
import { api } from '../services/api';
import { DashboardSummary, AccessEvent, DailyStats } from '../types';
import { useNavigate } from 'react-router-dom';

export const Dashboard: React.FC = () => {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [recentLogs, setRecentLogs] = useState<AccessEvent[]>([]);
  const [chartData, setChartData] = useState<DailyStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const isFetchingRef = useRef<boolean>(false);
  const navigate = useNavigate();

  const formatLogTime = (ts: string) => {
    if (!ts) return '--:--';
    const iso = ts.includes(' ') && !ts.includes('T') ? ts.replace(' ', 'T') : ts;
    const d = new Date(iso);
    return isNaN(d.getTime()) ? ts : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const fetchData = async (silent: boolean = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    if (!silent) {
      setIsRefreshing(true);
    }
    try {
      const summaryData = await api.getDashboardSummary();
      setSummary(summaryData);
    } catch (e) {
      console.warn("Could not fetch summary from backend", e);
    }

    try {
      const logsData = await api.getLogs();
      const list = Array.isArray(logsData) ? logsData : [];
      setRecentLogs(list.slice(0, 6));
    } catch (e) {
      console.warn("Could not fetch logs from backend", e);
      setRecentLogs([]);
    }

    try {
      const analyticsRes = await api.getAnalytics(7);
      if (analyticsRes && Array.isArray(analyticsRes.daily_stats)) {
        setChartData(analyticsRes.daily_stats);
      } else {
        setChartData([]);
      }
    } catch (e) {
      setChartData([]);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
      isFetchingRef.current = false;
    }
  };

  useEffect(() => {
    fetchData(false);
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      fetchData(true);
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-8 animate-slide-in">
      {/* ========================================================================= */}
      {/* HERO BANNER: FACEVAULT 360 TITLE & ANIMATED BIOMETRIC SCANNER VISUALIZER */}
      {/* ========================================================================= */}
      <div className="relative rounded-2xl overflow-hidden border border-blue-500/30 bg-gradient-to-r from-[#0a0f1d] via-[#101935] to-[#0a1128] p-6 sm:p-8 shadow-2xl shadow-blue-500/10">
        {/* Subtle Cyber Grid Background */}
        <div className="absolute inset-0 bg-cyber-grid opacity-30 pointer-events-none" />
        
        {/* Glowing Orbs */}
        <div className="absolute -right-20 -top-20 w-80 h-80 bg-blue-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -left-20 -bottom-20 w-80 h-80 bg-cyan-500/15 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row items-center justify-between gap-8">
          {/* Project Identity & Tagline */}
          <div className="space-y-4 max-w-xl text-center lg:text-left">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-400/30 text-cyan-300 text-xs font-mono font-semibold tracking-wide">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              INTELLIGENT BIOMETRIC ACCESS CONTROL
            </div>
            
            <div>
              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight text-white flex flex-wrap items-center justify-center lg:justify-start gap-3">
                <span>FACEVAULT</span>
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-cyan-300 to-teal-400">
                  360
                </span>
              </h1>
              <p className="text-sm sm:text-base text-slate-300 mt-2 font-medium">
                <span className="text-cyan-400 font-semibold font-mono tracking-widest uppercase text-xs">
                  "Recognize. Verify. Protect."
                </span>
                <span className="block text-slate-400 text-xs sm:text-sm mt-1">
                  High-speed pose-aware facial recognition, 7-angle biometric enrollment, and automated fail-closed attendance logging.
                </span>
              </p>
            </div>

            {/* Quick Action Navigation Buttons */}
            <div className="flex flex-wrap items-center justify-center lg:justify-start gap-3 pt-2">
              <button 
                onClick={() => navigate('/live')}
                className="bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-semibold text-xs sm:text-sm px-5 py-2.5 rounded-xl flex items-center gap-2 shadow-lg shadow-blue-500/30 transition-all transform hover:-translate-y-0.5 cursor-pointer"
              >
                <Scan className="w-4 h-4 animate-spin-slow" />
                Launch Live Recognition
              </button>
              <button 
                onClick={() => navigate('/enroll')}
                className="bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-slate-200 font-semibold text-xs sm:text-sm px-5 py-2.5 rounded-xl flex items-center gap-2 transition-all cursor-pointer"
              >
                <Users className="w-4 h-4 text-cyan-400" />
                Enroll New Identity
              </button>
              <button 
                onClick={() => fetchData(false)}
                disabled={isRefreshing}
                className="bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-slate-200 font-semibold text-xs sm:text-sm px-4 py-2.5 rounded-xl flex items-center gap-2 transition-all cursor-pointer"
                title="Sync Dashboard Telemetry"
              >
                <RefreshCw className={`w-4 h-4 text-emerald-400 ${isRefreshing ? 'animate-spin' : ''}`} />
                <span>Sync Data</span>
              </button>
            </div>
          </div>

          {/* Holographic 360 Face Radar Widget */}
          <div className="relative w-64 h-64 sm:w-72 sm:h-72 flex items-center justify-center shrink-0">
            {/* Outer Radar Rings */}
            <div className="absolute inset-0 rounded-full border border-cyan-500/20 animate-radar pointer-events-none" />
            <div className="absolute inset-4 rounded-full border border-blue-500/30 border-dashed animate-pulse-glow pointer-events-none" />
            <div className="absolute inset-10 rounded-full border border-cyan-400/20 pointer-events-none" />
            <div className="absolute inset-16 rounded-full border border-blue-400/40 pointer-events-none" />

            {/* Scanning Laser Line */}
            <div className="absolute inset-0 rounded-full overflow-hidden pointer-events-none">
              <div className="w-full h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-lg shadow-cyan-400 animate-laser" />
            </div>

            {/* Central Hologram Target */}
            <div className="relative w-28 h-28 rounded-2xl bg-gradient-to-b from-blue-900/60 to-cyan-950/80 border border-cyan-400/50 flex flex-col items-center justify-center p-3 text-center shadow-xl shadow-cyan-500/20 backdrop-blur-sm animate-biometric">
              <div className="relative">
                <Scan className="w-10 h-10 text-cyan-300 animate-pulse" />
                <Eye className="w-4 h-4 text-blue-400 absolute inset-0 m-auto" />
              </div>
              <span className="text-[10px] font-mono text-cyan-300 font-bold tracking-widest mt-1">
                360° MESH
              </span>
              <span className="text-[9px] font-mono text-slate-400">
                ACTIVE PIPELINE
              </span>
            </div>

            {/* Orbital Angle Badges */}
            <div className="absolute -top-1 px-2 py-0.5 rounded bg-blue-950 border border-blue-500/40 text-[9px] font-mono text-blue-300">
              PITCH: 0.0°
            </div>
            <div className="absolute -bottom-1 px-2 py-0.5 rounded bg-cyan-950 border border-cyan-500/40 text-[9px] font-mono text-cyan-300">
              YAW: 0.0°
            </div>
            <div className="absolute -left-2 px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-[9px] font-mono text-slate-400">
              ROLL: 0.0°
            </div>
            <div className="absolute -right-2 px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 text-[9px] font-mono text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
              LIVE
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TELEMETRY STATS GRID */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="transform transition-transform hover:-translate-y-1">
          <StatCard 
            title="Today's Entries" 
            value={summary?.todays_entries || 0} 
            icon={Activity} 
            color="blue" 
          />
        </div>
        <div className="transform transition-transform hover:-translate-y-1">
          <StatCard 
            title="Authorized (Granted)" 
            value={summary?.authorized_count || 0} 
            icon={UserCheck} 
            color="green" 
          />
        </div>
        <div className="transform transition-transform hover:-translate-y-1">
          <StatCard 
            title="Denied (Fail-Closed)" 
            value={summary?.denied_count || 0} 
            icon={UserX} 
            color="red" 
          />
        </div>
        <div className="transform transition-transform hover:-translate-y-1">
          <StatCard 
            title="Registered Person Profiles" 
            value={summary?.registered_people || 0} 
            icon={Users} 
            color="amber" 
          />
        </div>
      </div>

      {/* ========================================================================= */}
      {/* CHARTS SECTION */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 7-Day Trend Chart */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-[#111827] border border-[#1e293b] rounded-2xl p-6 shadow-xl relative overflow-hidden">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Activity className="w-4 h-4 text-blue-400" />
                  Entry & Verification Activity (Past 7 Days)
                </h3>
                <p className="text-xs text-slate-400">Audit logs & attendance telemetry</p>
              </div>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">
                DAILY LOGS
              </span>
            </div>
            
            {chartData.length > 0 ? (
              <EntryChart data={chartData} />
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-sm">
                <Scan className="w-8 h-8 mb-2 text-slate-600 animate-pulse" />
                <p>No historical entries yet. Live attendance events will populate this graph.</p>
              </div>
            )}
          </div>
        </div>

        {/* Access Ratio Doughnut */}
        <div className="space-y-6">
          <div className="bg-[#111827] border border-[#1e293b] rounded-2xl p-6 shadow-xl relative overflow-hidden flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Shield className="w-4 h-4 text-cyan-400" />
                  Today's Gate Ratio
                </h3>
                <p className="text-xs text-slate-400">Authorized vs Denied access</p>
              </div>
            </div>

            {(summary?.todays_entries || 0) > 0 ? (
              <AuthPieChart 
                authorized={summary?.authorized_count || 0} 
                denied={summary?.denied_count || 0} 
              />
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-center px-4">
                <Radar className="w-10 h-10 mb-2 text-cyan-500/40 animate-spin-slow" />
                <p className="text-sm">Awaiting access events from camera stream.</p>
                <p className="text-xs text-slate-600 mt-1">Standby for face detection</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* REAL-TIME ATTENDANCE & EVENT FEED TABLE */}
      {/* ========================================================================= */}
      <div className="bg-[#111827] border border-[#1e293b] rounded-2xl overflow-hidden shadow-xl">
        <div className="p-6 border-b border-[#1e293b] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500"></span>
              </span>
              Live Attendance & Access Feed
            </h3>
            <p className="text-xs text-slate-400">Directly synchronized with SQLite database event log</p>
          </div>
          
          <button 
            onClick={() => navigate('/logs')} 
            className="text-xs text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            Open Complete Logs <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-400 uppercase bg-[#0a0f1d]">
              <tr>
                <th className="px-6 py-3.5 font-semibold">Timestamp</th>
                <th className="px-6 py-3.5 font-semibold">Identified Subject</th>
                <th className="px-6 py-3.5 font-semibold">Status / Gate</th>
                <th className="px-6 py-3.5 font-semibold">Confidence Match</th>
                <th className="px-6 py-3.5 font-semibold">Sensor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b] text-slate-300">
              {recentLogs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-6 py-3.5 whitespace-nowrap text-xs font-mono text-slate-400">
                    {formatLogTime(log.timestamp)}
                  </td>
                  <td className="px-6 py-3.5 font-medium text-white flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-xs font-bold text-blue-400">
                      {log.recognized_name ? log.recognized_name[0].toUpperCase() : '?'}
                    </div>
                    <span>{log.recognized_name || 'Unknown Person'}</span>
                  </td>
                  <td className="px-6 py-3.5">
                    <StatusBadge status={log.status} />
                  </td>
                  <td className="px-6 py-3.5 font-mono text-xs">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 rounded-full bg-slate-700 overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${log.status === 'authorized' ? 'bg-emerald-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.round(log.confidence * 100)}%` }}
                        />
                      </div>
                      <span>{Math.round(log.confidence * 100)}%</span>
                    </div>
                  </td>
                  <td className="px-6 py-3.5 text-xs font-mono text-slate-400">
                    {log.camera_id || 'CAM-01'}
                  </td>
                </tr>
              ))}
              {recentLogs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-slate-500">
                    <Scan className="w-8 h-8 mx-auto mb-2 text-slate-600 opacity-60 animate-pulse" />
                    <p className="text-sm font-medium">No access events recorded today.</p>
                    <p className="text-xs text-slate-600 mt-1">Real-time attendance events from camera stream will populate here automatically.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
