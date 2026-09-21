import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import {
  Clock,
  Calendar,
  Search,
  Filter,
  RefreshCw,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight
} from 'lucide-react';

export const StaffAttendance: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [records, setRecords] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDate, setSelectedDate] = useState('');

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const res = await api.getMyAttendanceHistory(150);
      if (res && res.records) {
        setRecords(res.records);
      }
    } catch (e) {
      console.error('Failed to load attendance history:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const filteredRecords = records.filter((r) => {
    const matchesSearch =
      searchTerm === '' ||
      r.date?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.camera_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.status?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesDate = selectedDate === '' || r.date === selectedDate;
    return matchesSearch && matchesDate;
  });

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono mb-1">
            <Clock className="w-3.5 h-3.5" />
            <span>MY BIOMETRIC LOGS</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Personal Attendance History</h1>
          <p className="text-xs text-slate-400">
            Chronological log of your authenticated entrance and exit sessions.
          </p>
        </div>

        <button
          onClick={fetchHistory}
          disabled={loading}
          className="self-start md:self-auto flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Records</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between bg-[#0b1329] border border-slate-800/80 p-4 rounded-2xl">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Filter by date, camera..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors font-mono"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <span className="text-xs text-slate-400 font-mono">Total Recorded Sessions:</span>
          <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
            {records.length}
          </span>
        </div>
      </div>

      {/* History Table */}
      <div className="rounded-2xl bg-[#0b1329] border border-slate-800/80 overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto text-cyan-400 mb-2" />
            Retrieving personal attendance records...
          </div>
        ) : filteredRecords.length === 0 ? (
          <div className="py-16 text-center text-slate-400 space-y-2">
            <AlertCircle className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-sm">No attendance records found matching the filter.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="bg-slate-900/60 border-b border-slate-800 text-slate-400 font-mono uppercase">
                  <th className="py-3.5 px-4">Date</th>
                  <th className="py-3.5 px-4">Check-In</th>
                  <th className="py-3.5 px-4">Check-Out</th>
                  <th className="py-3.5 px-4">Duration</th>
                  <th className="py-3.5 px-4">Camera</th>
                  <th className="py-3.5 px-4">Recognition Confidence</th>
                  <th className="py-3.5 px-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {filteredRecords.map((r, i) => (
                  <tr key={r.id || i} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 text-white font-bold flex items-center gap-2">
                      <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                      <span>{r.date}</span>
                    </td>
                    <td className="py-3 px-4 text-emerald-400 font-bold">
                      {r.check_in_time || r.time || '--'}
                    </td>
                    <td className="py-3 px-4 text-cyan-400 font-bold">
                      {r.check_out_time || (
                        <span className="text-amber-400 animate-pulse">In Progress...</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-amber-300">
                      {r.formatted_duration || r.duration || '--'}
                    </td>
                    <td className="py-3 px-4 text-slate-300">
                      {r.camera_name || 'RTSP Main Gate'}
                    </td>
                    <td className="py-3 px-4 text-slate-400">
                      {r.match_score ? `${(r.match_score * 100).toFixed(1)}%` : '--'}
                    </td>
                    <td className="py-3 px-4">
                      {r.check_out_time ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[10px]">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Complete</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 text-[10px]">
                          <span>Active Session</span>
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
    </div>
  );
};

