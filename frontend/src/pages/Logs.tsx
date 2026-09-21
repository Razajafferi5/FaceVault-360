import React, { useEffect, useState } from 'react';
import { DataTable } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { api } from '../services/api';
import { AccessEvent } from '../types';
import { ColumnDef } from '@tanstack/react-table';

export const Logs: React.FC = () => {
  const [data, setData] = useState<AccessEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getLogs()
      .then(res => setData(res as any))
      .catch(err => {
        console.error(err);
        // Mock data
        setData([
          { id: 1, person_id: 101, recognized_name: 'John Doe', timestamp: new Date().toISOString(), confidence: 0.95, status: 'authorized', authorization_result: 'granted', pose_yaw: 0, pose_pitch: 0, quality_score: 0.8, camera_id: 'cam1', failure_reason: null },
          { id: 2, person_id: null, recognized_name: null, timestamp: new Date(Date.now() - 60000).toISOString(), confidence: 0.45, status: 'denied', authorization_result: 'denied', pose_yaw: 0, pose_pitch: 0, quality_score: 0.5, camera_id: 'cam1', failure_reason: 'low_confidence' }
        ]);
      })
      .finally(() => setLoading(false));
  }, []);

  const columns: ColumnDef<AccessEvent>[] = [
    { accessorKey: 'id', header: 'ID' },
    { accessorKey: 'timestamp', header: 'Time', cell: ({ row }) => new Date(row.original.timestamp).toLocaleString() },
    { accessorKey: 'recognized_name', header: 'Person', cell: ({ row }) => row.original.recognized_name || 'Unknown' },
    { 
      accessorKey: 'status', 
      header: 'Status',
      cell: ({ row }) => <StatusBadge status={row.original.status} />
    },
    { accessorKey: 'confidence', header: 'Confidence', cell: ({ row }) => `${Math.round(row.original.confidence * 100)}%` },
    { accessorKey: 'camera_id', header: 'Camera' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Entry Logs</h1>
          <p className="text-slate-400">Detailed history of all system events and access attempts</p>
        </div>
      </div>

      <div className="bg-[#1e293b] p-4 rounded-xl border border-[#334155] flex gap-4">
        <input type="date" className="bg-[#0f172a] border border-[#334155] rounded-md px-3 py-1.5 text-sm text-white" />
        <select className="bg-[#0f172a] border border-[#334155] rounded-md px-3 py-1.5 text-sm text-white">
          <option value="">All Statuses</option>
          <option value="authorized">Authorized</option>
          <option value="denied">Denied</option>
        </select>
        <button className="bg-[#334155] text-white px-4 py-1.5 rounded-md text-sm hover:bg-slate-600">Filter</button>
      </div>

      {loading ? (
        <div className="text-slate-400 p-8 text-center">Loading logs...</div>
      ) : (
        <DataTable columns={columns} data={data} />
      )}
    </div>
  );
};
