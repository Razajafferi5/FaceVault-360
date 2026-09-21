import React, { useEffect, useState, useCallback } from 'react';
import { DataTable } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { api } from '../services/api';
import { Person } from '../types';
import { Plus, RefreshCw, Trash2, UserCheck, Lock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { ColumnDef } from '@tanstack/react-table';

export const People: React.FC = () => {
  const [data, setData] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const navigate = useNavigate();

  const isOwner = currentUser?.is_owner === true || currentUser?.role?.toLowerCase() === 'owner';

  const loadPeople = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [list, user] = await Promise.all([
        api.getPersons(),
        api.getMe().catch(() => null)
      ]);
      setData(Array.isArray(list) ? list : []);
      if (user) setCurrentUser(user);
    } catch (err) {
      console.error("Error loading people:", err);
      setData([]);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadPeople();
  }, [loadPeople]);

  const handleDelete = async (id: number, name: string) => {
    if (!isOwner) {
      alert("Access Denied: Only Syed Raza Abbas (Owner) has authorization to delete enrolled personnel.");
      return;
    }
    if (!confirm(`Are you sure you want to delete ${name} and all biometric data?`)) return;
    try {
      await api.deletePerson(id);
      setData(prev => prev.filter(p => p.id !== id));
    } catch (err: any) {
      alert(`Failed to delete person: ${err.message || err}`);
    }
  };

  const columns: ColumnDef<Person>[] = [
    { accessorKey: 'name', header: 'Name' },
    { accessorKey: 'person_identifier', header: 'ID / Code' },
    { accessorKey: 'department', header: 'Department', cell: ({ row }) => row.original.department || 'General' },
    { 
      accessorKey: 'embedding_count', 
      header: 'Enrolled Angles',
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-1.5 font-mono font-semibold text-xs px-2.5 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
          <UserCheck className="w-3.5 h-3.5" />
          {row.original.embedding_count} {row.original.embedding_count === 1 ? 'Angle' : 'Angles'}
        </span>
      )
    },
    { 
      accessorKey: 'status', 
      header: 'Status',
      cell: ({ row }) => <StatusBadge status={row.original.status} />
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          {isOwner ? (
            <button
              onClick={() => handleDelete(row.original.id, row.original.name)}
              title="Delete Employee (Owner Only)"
              className="p-1.5 hover:bg-red-500/20 text-slate-400 hover:text-red-400 rounded transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          ) : (
            <span
              title="Owner permission required to delete personnel"
              className="p-1.5 text-slate-600 cursor-not-allowed flex items-center gap-1 text-xs"
            >
              <Lock className="w-3.5 h-3.5" />
            </span>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">People Management</h1>
          <p className="text-slate-400 text-sm">Manage enrolled employees and biometric access permissions</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadPeople}
            disabled={isRefreshing}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors border border-slate-700"
            title="Refresh List"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
          <button 
            onClick={() => navigate('/enroll')}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium flex items-center gap-2 transition-colors text-sm shadow-lg shadow-blue-500/20"
          >
            <Plus className="w-4 h-4" />
            Enroll New Person
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-400 bg-[#1e293b] border border-[#334155] rounded-xl flex flex-col items-center justify-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-400 mb-3" />
          <p className="font-semibold">Loading enrolled persons...</p>
        </div>
      ) : data.length === 0 ? (
        <div className="p-12 text-center text-slate-400 bg-[#1e293b] border border-[#334155] rounded-xl space-y-3">
          <p className="text-base font-semibold text-slate-300">No enrolled employees found.</p>
          <p className="text-xs text-slate-500">Click "Enroll New Person" to add employees and capture their facial biometrics.</p>
          <button
            onClick={() => navigate('/enroll')}
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-xs font-semibold"
          >
            Go to Enrollment
          </button>
        </div>
      ) : (
        <DataTable columns={columns} data={data} />
      )}
    </div>
  );
};
