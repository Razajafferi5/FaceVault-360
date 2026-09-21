import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Video,
  UserCheck,
  UserPlus,
  Users,
  FileText,
  FlaskConical,
  BarChart3,
  Settings,
  Shield,
  Scan,
  Radio,
  ShieldAlert,
  Crown,
  User,
  Clock,
  KeyRound,
  Sparkles
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const Sidebar: React.FC = () => {
  const { isOwner, user } = useAuth();

  const ownerNavItems = [
    { to: '/', icon: LayoutDashboard, label: 'Overview Dashboard' },
    { to: '/attendance', icon: UserCheck, label: 'Org Attendance' },
    { to: '/people', icon: Users, label: 'Personnel & Deletion' },
    { to: '/unknowns', icon: ShieldAlert, label: 'Unknown Visitors & Approval' },
    { to: '/cameras', icon: Radio, label: 'RTSP Cameras' },
    { to: '/enroll', icon: UserPlus, label: 'Biometric Enrollment' },
    { to: '/owner-management', icon: KeyRound, label: 'Users & Ownership' },
    { to: '/live', icon: Video, label: 'Live Monitor' },
    { to: '/logs', icon: FileText, label: 'Entry & Audit Logs' },
    { to: '/analytics', icon: BarChart3, label: 'Analytics' },
    { to: '/testing', icon: FlaskConical, label: 'Testing Sandbox' },
    { to: '/settings', icon: Settings, label: 'System Settings' },
  ];

  const staffNavItems = [
    { to: '/staff-dashboard', icon: LayoutDashboard, label: 'My Dashboard' },
    { to: '/my-attendance', icon: Clock, label: 'My Attendance Log' },
    { to: '/profile', icon: User, label: 'My Profile & Status' },
    { to: '/live', icon: Video, label: 'Live Monitor' },
    { to: '/testing', icon: FlaskConical, label: 'Biometric Sandbox' },
  ];

  const navItems = isOwner ? ownerNavItems : staffNavItems;

  return (
    <aside className="w-64 bg-[#0a0f1d] border-r border-[#1e293b] h-screen flex flex-col hidden md:flex shrink-0 select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-[#1e293b] flex items-center gap-3">
        <div className="relative flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-lg shadow-blue-500/30 overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-t from-transparent via-cyan-300/30 to-transparent animate-laser opacity-75 pointer-events-none" />
          <Scan className="w-6 h-6 animate-pulse-glow" />
          <Shield className="absolute w-3.5 h-3.5 mt-0.5 text-cyan-200" />
        </div>
        
        <div>
          <div className="flex items-center gap-1.5">
            <h1 className="text-lg font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-blue-400">
              FACEVAULT
            </h1>
            <span className="text-xs px-1.5 py-0.5 font-bold rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
              360
            </span>
          </div>
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/80">
            Recognize • Verify • Protect
          </p>
        </div>
      </div>

      {/* Role Panel Banner */}
      <div className="px-3 pt-3 pb-1">
        <div className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold ${
          isOwner
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
            : 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300'
        }`}>
          <div className="flex items-center gap-2">
            {isOwner ? <Crown className="w-4 h-4 text-amber-400" /> : <User className="w-4 h-4 text-cyan-400" />}
            <span className="font-mono uppercase tracking-wider text-[11px]">
              {isOwner ? 'Owner / Admin' : 'Staff Portal'}
            </span>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 border border-white/10 uppercase">
            {isOwner ? 'Privileged' : 'Limited'}
          </span>
        </div>
      </div>
      
      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        <div className="px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">
          {isOwner ? 'Administrative Modules' : 'Personal Navigation'}
        </div>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all relative overflow-hidden group ${
                isActive 
                  ? (isOwner 
                      ? 'bg-gradient-to-r from-amber-500/20 to-yellow-500/10 text-amber-300 border border-amber-500/30 shadow-lg shadow-amber-500/10' 
                      : 'bg-gradient-to-r from-cyan-600/20 to-blue-500/10 text-cyan-300 border border-cyan-500/30 shadow-lg shadow-cyan-500/10'
                    )
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className={`absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r-full shadow-sm ${
                    isOwner ? 'bg-amber-400 shadow-amber-400' : 'bg-cyan-400 shadow-cyan-400'
                  }`} />
                )}
                <item.icon className={`w-4.5 h-4.5 transition-transform group-hover:scale-110 ${
                  isActive 
                    ? (isOwner ? 'text-amber-300' : 'text-cyan-300')
                    : 'text-slate-400'
                }`} />
                <span className="truncate">{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Telemetry Status Footer */}
      <div className="p-4 border-t border-[#1e293b] bg-slate-950/40">
        <div className="flex items-center justify-between px-2 py-1.5 rounded-lg bg-[#0f172a] border border-slate-800 text-xs">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="font-mono text-[11px] font-semibold text-slate-300">
              {isOwner ? 'ROOT ACTIVE' : 'STAFF SECURE'}
            </span>
          </div>
          <span className="font-mono text-[10px] text-cyan-400 font-bold bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-800/40">
            360° ENGINE
          </span>
        </div>
      </div>
    </aside>
  );
};
