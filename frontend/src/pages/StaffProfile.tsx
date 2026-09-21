import React from 'react';
import { useAuth } from '../context/AuthContext';
import {
  User,
  Shield,
  Key,
  Mail,
  Building,
  CheckCircle2,
  Lock,
  LogOut,
  Sparkles,
  Info
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const StaffProfile: React.FC = () => {
  const { user, isOwner, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="border-b border-slate-800 pb-5">
        <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono mb-1">
          <User className="w-3.5 h-3.5" />
          <span>AUTHENTICATED CREDENTIALS</span>
        </div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Staff Account Profile</h1>
        <p className="text-xs text-slate-400">
          Your verified biometric identity and permissions within FaceVault 360.
        </p>
      </div>

      {/* Main Profile Card */}
      <div className="rounded-3xl bg-[#0b1329] border border-slate-800/80 p-6 md:p-8 space-y-6 relative overflow-hidden">
        <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-blue-600 to-cyan-500 flex items-center justify-center text-white text-2xl font-bold shadow-xl shadow-blue-500/20">
            {user?.full_name?.charAt(0) || user?.username?.charAt(0) || 'U'}
          </div>

          <div className="space-y-1 text-center sm:text-left flex-1">
            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
              <h2 className="text-xl font-bold text-white">
                {user?.full_name || user?.username}
              </h2>
              <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 text-xs font-mono font-bold uppercase">
                {isOwner ? '👑 Owner' : '👤 Staff Member'}
              </span>
            </div>
            <p className="text-xs font-mono text-slate-400">@{user?.username}</p>
            <p className="text-xs text-slate-500 pt-1">
              Active session secured by JSON Web Token (JWT) cryptographic signature.
            </p>
          </div>

          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-semibold transition-all cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out</span>
          </button>
        </div>

        {/* Credentials Details Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-slate-800/80">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="flex items-center gap-2 text-slate-400 text-xs font-mono">
              <Mail className="w-3.5 h-3.5 text-cyan-400" />
              <span>Email Address</span>
            </div>
            <div className="text-sm font-semibold text-white">
              {user?.email || 'N/A (Local Auth Account)'}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="flex items-center gap-2 text-slate-400 text-xs font-mono">
              <Key className="w-3.5 h-3.5 text-cyan-400" />
              <span>System Role & Permissions</span>
            </div>
            <div className="text-sm font-semibold text-cyan-300 uppercase font-mono">
              {user?.role || 'staff'}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="flex items-center gap-2 text-slate-400 text-xs font-mono">
              <Building className="w-3.5 h-3.5 text-cyan-400" />
              <span>Department / Organization Unit</span>
            </div>
            <div className="text-sm font-semibold text-white">
              {user?.person_details?.department || 'Operations / Staff'}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="flex items-center gap-2 text-slate-400 text-xs font-mono">
              <Shield className="w-3.5 h-3.5 text-cyan-400" />
              <span>Enrolled Biometric Gallery</span>
            </div>
            <div className="text-sm font-semibold text-emerald-400 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" />
              <span>Active & Match Ready</span>
            </div>
          </div>
        </div>

        {/* Security / Scope Notice */}
        <div className="p-4 rounded-2xl bg-blue-500/5 border border-blue-500/20 text-xs text-slate-400 flex items-start gap-3">
          <Info className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-slate-200">Staff Permission Boundary</p>
            <p className="text-[11px] leading-relaxed text-slate-400">
              Staff accounts have read-only access to their own attendance sessions and live monitor camera feeds.
              Privileged actions such as enrolling faces, deleting employees, approving unknown visitors, or modifying RTSP cameras require Owner authorization.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

