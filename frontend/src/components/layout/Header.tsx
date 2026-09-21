import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  ShieldCheck,
  Video,
  User,
  ShieldAlert,
  Crown,
  LogOut
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';


export const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isOwner, logout } = useAuth();

  const getPageTitle = () => {
    switch (location.pathname) {
      case '/': return 'Command Center & SOC Telemetry';
      case '/unknowns': return 'Unknown Persons & Visitor Access';
      case '/attendance': return 'Biometric Attendance & Sessions';
      case '/cameras': return 'RTSP High-Accuracy Camera Streams';
      case '/live': return 'Live Biometric Recognition Stream';
      case '/enroll': return 'Multi-Angle 360° Identity Enrollment';
      case '/people': return 'Enrolled Personnel Directory';
      case '/logs': return 'Audit & Attendance Entry Records';
      case '/testing': return 'Biometric Verification Sandbox';
      case '/analytics': return 'Security Trends & Incident Analytics';
      case '/settings': return 'System Engine Thresholds & Parameters';
      default: return 'FaceVault 360';
    }
  };

  return (
    <header className="h-16 bg-[#0a0f1d]/90 backdrop-blur-md border-b border-[#1e293b] flex items-center justify-between px-6 shrink-0 z-20">
      {/* Title with Project Name Badge */}
      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono font-bold tracking-wider">
          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
          <span>FACEVAULT 360</span>
        </div>
        <span className="text-slate-600 hidden sm:inline">/</span>
        <h2 className="text-base font-semibold text-white tracking-tight">{getPageTitle()}</h2>
      </div>

      <div className="flex items-center gap-3.5">
        {/* Unknown Visitors Alert Quick Link */}
        <button
          onClick={() => navigate('/unknowns')}
          className="hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-semibold transition-all cursor-pointer"
          title="View unrecognized visitor access log"
        >
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
          <span>Unknown Visitors</span>
        </button>

        {/* Quick Access Live Button */}
        <button
          onClick={() => navigate('/live')}
          className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white text-xs font-semibold shadow-md shadow-blue-500/20 transition-all cursor-pointer"
        >
          <Video className="w-3.5 h-3.5 animate-pulse" />
          <span>Live Monitor</span>
        </button>

        {/* Authenticated User Status Badge */}
        <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl border text-xs font-medium select-none bg-slate-900/90 border-slate-800">
          <div
            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
              isOwner ? 'bg-amber-500 text-black shadow-md shadow-amber-500/20' : 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
            }`}
          >
            {isOwner ? <Crown className="w-4 h-4" /> : <User className="w-4 h-4" />}
          </div>
          <div className="text-left hidden sm:block">
            <div className="font-bold text-white leading-tight flex items-center gap-1.5">
              <span>{user?.full_name || user?.username || 'Authenticated User'}</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono font-bold tracking-wider uppercase ${
                isOwner
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
              }`}>
                {isOwner ? 'Owner' : 'Staff'}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              {user?.email || (isOwner ? 'Full Administrative Access' : 'Personal Staff Portal')}
            </div>
          </div>
        </div>

        {/* Quick Logout Button */}
        <button
          onClick={async () => {
            await logout();
            navigate('/login');
          }}
          title="Sign Out of FaceVault 360"
          className="p-2 rounded-xl bg-slate-800/80 hover:bg-rose-500/20 text-slate-400 hover:text-rose-300 border border-slate-700/80 hover:border-rose-500/30 transition-all cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
        </button>

        {/* Status Notification Icon */}
        <div className="relative p-2 rounded-lg bg-[#111827] border border-slate-800 text-slate-400">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-cyan-400 rounded-full shadow-sm shadow-cyan-400 animate-pulse"></span>
        </div>
      </div>
    </header>
  );
};
