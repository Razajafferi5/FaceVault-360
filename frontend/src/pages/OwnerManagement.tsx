import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import {
  Crown,
  Shield,
  KeyRound,
  Users,
  UserPlus,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Trash2,
  History,
  Lock,
  ArrowRightLeft
} from 'lucide-react';

export const OwnerManagement: React.FC = () => {
  const { user } = useAuth();
  const [users, setUsers] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // New User Form State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('staff');

  // Ownership Transfer State
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [transferTargetId, setTransferTargetId] = useState<number | null>(null);
  const [demoteRole, setDemoteRole] = useState('admin');

  const fetchData = async () => {
    try {
      setLoading(true);
      const [usersRes, logsRes]: [any, any] = await Promise.all([
        api.getUsersList().catch(() => []),
        api.getAuditLogs().catch(() => ({ logs: [] }))
      ]);
      if (Array.isArray(usersRes)) {
        setUsers(usersRes);
      } else if (usersRes && Array.isArray(usersRes.users)) {
        setUsers(usersRes.users);
      }
      if (logsRes && logsRes.logs) {
        setAuditLogs(logsRes.logs);
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: `Failed to load management data: ${e.message || e}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername || !newPassword) return;
    try {
      setActionLoading(true);
      await api.createSystemUser({
        username: newUsername,
        password: newPassword,
        role: newRole
      });
      setMessage({ type: 'success', text: `Created user account '${newUsername}' successfully.` });
      setShowCreateModal(false);
      setNewUsername('');
      setNewPassword('');
      fetchData();
    } catch (e: any) {
      setMessage({ type: 'error', text: `User creation failed: ${e.message || e}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRoleChange = async (userId: number, role: string) => {
    try {
      setActionLoading(true);
      await api.updateUserRole(userId, role);
      setMessage({ type: 'success', text: `Updated user role to ${role}.` });
      fetchData();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Role update failed: ${e.message || e}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteUser = async (userId: number, username: string) => {
    if (!window.confirm(`Are you sure you want to delete user account '${username}'?`)) return;
    try {
      setActionLoading(true);
      await api.deleteSystemUser(userId);
      setMessage({ type: 'success', text: `Deleted user '${username}'.` });
      fetchData();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Failed to delete user: ${e.message || e}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferOwnership = async () => {
    if (!transferTargetId) return;
    const target = users.find((u) => u.id === transferTargetId);
    if (!target) return;
    if (
      !window.confirm(
        `CRITICAL ACTION: Are you sure you want to permanently transfer Owner privileges to '${target.name || target.username}'? You will become an '${demoteRole}'.`
      )
    ) {
      return;
    }

    try {
      setActionLoading(true);
      const res = await api.changeOwner({
        target_user_id: transferTargetId,
        new_role_for_previous_owner: demoteRole
      });
      alert(res.message);
      window.location.reload();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Ownership transfer failed: ${e.message || e}` });
      setActionLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2 text-amber-400 text-xs font-mono mb-1">
            <Crown className="w-3.5 h-3.5" />
            <span>OWNER PRIVILEGES & GOVERNANCE</span>
          </div>
          <h1 className="text-2xl font-black text-white tracking-tight">System Users & Ownership</h1>
          <p className="text-xs text-slate-400">
            Manage system accounts, staff roles, ownership transfers, and audit logs.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-500/20 transition-all cursor-pointer"
          >
            <UserPlus className="w-4 h-4" />
            <span>Create User</span>
          </button>

          <button
            onClick={() => setShowTransferModal(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-semibold transition-all cursor-pointer"
          >
            <ArrowRightLeft className="w-4 h-4" />
            <span>Transfer Ownership</span>
          </button>

          <button
            onClick={fetchData}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Status Notice */}
      {message && (
        <div
          className={`p-4 rounded-2xl flex items-center justify-between gap-3 text-xs ${
            message.type === 'success'
              ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'
              : 'bg-rose-500/10 border border-rose-500/30 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2">
            {message.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 shrink-0" />
            )}
            <span>{message.text}</span>
          </div>
          <button onClick={() => setMessage(null)} className="text-slate-400 hover:text-white font-bold">
            ×
          </button>
        </div>
      )}

      {/* Users Management Table */}
      <div className="rounded-3xl bg-[#0b1329] border border-slate-800/80 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <Users className="w-4 h-4 text-cyan-400" />
            <span>Registered System Accounts ({users.length})</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-900/60 border-b border-slate-800 text-slate-400 font-mono uppercase">
                <th className="py-3 px-4">User</th>
                <th className="py-3 px-4">Username</th>
                <th className="py-3 px-4">Current Role</th>
                <th className="py-3 px-4">Role Management</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {users.map((u) => {
                const isItemOwner = u.is_owner || u.role?.toLowerCase() === 'owner';
                return (
                  <tr key={u.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-white flex items-center gap-2">
                      <div
                        className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                          isItemOwner ? 'bg-amber-500 text-black' : 'bg-blue-600 text-white'
                        }`}
                      >
                        {isItemOwner ? '👑' : '👤'}
                      </div>
                      <span>{u.name || u.username}</span>
                    </td>
                    <td className="py-3 px-4 text-slate-300">@{u.username}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded font-bold uppercase text-[10px] ${
                          isItemOwner
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                            : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30'
                        }`}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {isItemOwner ? (
                        <span className="text-[11px] text-slate-500 italic">Owner role (Use Transfer)</span>
                      ) : (
                        <select
                          value={u.role?.toLowerCase()}
                          onChange={(e) => handleRoleChange(u.id, e.target.value)}
                          disabled={actionLoading}
                          className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-cyan-500"
                        >
                          <option value="staff">staff</option>
                          <option value="operator">operator</option>
                          <option value="admin">admin</option>
                          <option value="viewer">viewer</option>
                        </select>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {!isItemOwner && (
                        <button
                          onClick={() => handleDeleteUser(u.id, u.username)}
                          disabled={actionLoading}
                          className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 transition-colors cursor-pointer"
                          title="Delete user account"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Security Audit Log */}
      <div className="rounded-3xl bg-[#0b1329] border border-slate-800/80 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-white font-bold text-base">
            <History className="w-4 h-4 text-amber-400" />
            <span>Security & Governance Audit Logs ({auditLogs.length})</span>
          </div>
          <span className="text-xs text-slate-500 font-mono">Immutable server-recorded events</span>
        </div>

        {auditLogs.length === 0 ? (
          <div className="py-10 text-center text-slate-500 text-xs font-mono">
            No privileged audit events recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="bg-slate-900/60 border-b border-slate-800 text-slate-400 font-mono uppercase">
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Actor</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Target</th>
                  <th className="py-3 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {auditLogs.map((l) => (
                  <tr key={l.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-400">
                      {l.timestamp ? new Date(l.timestamp).toLocaleString() : '--'}
                    </td>
                    <td className="py-3 px-4 text-white font-semibold">
                      {l.actor_name} ({l.actor_role})
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/30 font-bold text-[10px]">
                        {l.action}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-cyan-300">{l.target_entity || '--'}</td>
                    <td className="py-3 px-4 text-slate-300 max-w-xs truncate">{l.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#0f172a] border border-slate-700 rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-blue-400" />
              <span>Create New Account</span>
            </h3>

            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Username</label>
                <input
                  type="text"
                  required
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                  placeholder="e.g. employee_john"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Password</label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                  placeholder="At least 6 characters"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Assigned Role</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="staff">Staff (Personal portal & logs)</option>
                  <option value="operator">Operator (Attendance operator)</option>
                  <option value="admin">Admin (System administrator)</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-colors cursor-pointer"
                >
                  {actionLoading ? 'Creating...' : 'Create Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Transfer Ownership Modal */}
      {showTransferModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#0f172a] border border-amber-500/30 rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl">
            <h3 className="text-lg font-bold text-amber-300 flex items-center gap-2">
              <Crown className="w-5 h-5 text-amber-400" />
              <span>Transfer System Ownership</span>
            </h3>

            <p className="text-xs text-slate-400 leading-relaxed">
              Transferring ownership will grant full administrative privileges to the selected user and demote your current account.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">Select New Owner</label>
                <select
                  value={transferTargetId || ''}
                  onChange={(e) => setTransferTargetId(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="">-- Choose User Account --</option>
                  {users
                    .filter((u) => !u.is_owner && u.role?.toLowerCase() !== 'owner')
                    .map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name || u.username} (@{u.username})
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">
                  Your New Role After Transfer
                </label>
                <select
                  value={demoteRole}
                  onChange={(e) => setDemoteRole(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="admin">admin (Administrator)</option>
                  <option value="staff">staff (Staff member)</option>
                  <option value="operator">operator (Security operator)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowTransferModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleTransferOwnership}
                disabled={!transferTargetId || actionLoading}
                className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs transition-colors cursor-pointer"
              >
                {actionLoading ? 'Transferring...' : 'Confirm Transfer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
