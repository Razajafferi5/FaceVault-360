import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { 
  Users, 
  UserCheck, 
  Clock, 
  Calendar, 
  CheckCircle2, 
  Search, 
  RefreshCw, 
  Download, 
  Video, 
  LogIn, 
  LogOut, 
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Layers,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { AttendanceRecord, EmployeeDailySummary, Person } from '../types';

export const Attendance: React.FC = () => {
  // Helper to get formatted DD-MM-YYYY string for today or a specific Date object
  const formatDateToDDMMYYYY = (d: Date): string => {
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    return `${day}-${month}-${year}`;
  };

  // Helper to convert Date to YYYY-MM-DD for <input type="date" />
  const formatDateToYYYYMMDD = (d: Date): string => {
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    return `${year}-${month}-${day}`;
  };

  // Parse DD-MM-YYYY string into a Date object
  const parseDDMMYYYY = (str: string): Date => {
    const parts = str.split('-');
    if (parts.length === 3) {
      return new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
    }
    return new Date();
  };

  // Date state (defaults to today's date formatted as DD-MM-YYYY)
  const [selectedDate, setSelectedDate] = useState<string>(() => formatDateToDDMMYYYY(new Date()));
  const todayStr = useMemo(() => formatDateToDDMMYYYY(new Date()), []);
  const isToday = selectedDate === todayStr;

  // Data states
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [summaries, setSummaries] = useState<EmployeeDailySummary[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // In-flight concurrency lock
  const isFetchingRef = useRef<boolean>(false);

  // Accordion state: set of expanded employee IDs
  const [expandedEmployees, setExpandedEmployees] = useState<Set<number>>(new Set());

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'checked_in' | 'checked_out'>('all');

  // Toggle accordion expansion for an employee
  const toggleExpand = (employeeId: number) => {
    setExpandedEmployees(prev => {
      const next = new Set(prev);
      if (next.has(employeeId)) {
        next.delete(employeeId);
      } else {
        next.add(employeeId);
      }
      return next;
    });
  };

  // Expand or collapse all
  const toggleExpandAll = () => {
    if (expandedEmployees.size === summaries.length) {
      setExpandedEmployees(new Set());
    } else {
      setExpandedEmployees(new Set(summaries.map(s => s.employee_id)));
    }
  };

  // Fetch registered people (to calculate enrollment KPIs)
  const loadPeople = useCallback(async () => {
    try {
      const list = await api.getPersons();
      if (Array.isArray(list)) {
        setPeople(list);
      }
    } catch (err) {
      console.warn('Failed to load registered people:', err);
    }
  }, []);

  // Fetch attendance records and summaries for the selected date
  const loadRecords = useCallback(async (silent = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    if (!silent) setError(null);

    try {
      let res;
      if (selectedDate === todayStr) {
        res = await api.getTodayAttendance();
      } else {
        res = await api.getAttendanceByDate(selectedDate);
      }

      if (res) {
        setRecords(res.records || []);
        if (res.summaries && Array.isArray(res.summaries)) {
          setSummaries(res.summaries);
        } else {
          // Fallback: Group records by employee manually if backend didn't return summaries
          const recs: AttendanceRecord[] = res.records || [];
          const grouped: { [key: number]: AttendanceRecord[] } = {};
          recs.forEach(r => {
            if (!grouped[r.employee_id]) grouped[r.employee_id] = [];
            grouped[r.employee_id].push(r);
          });
          const fallbackSummaries: EmployeeDailySummary[] = Object.entries(grouped).map(([idStr, items]) => {
            const empId = Number(idStr);
            const openSess = items.find(r => r.check_in_time && !r.check_out_time);
            const closedSess = items.filter(r => r.check_out_time);
            return {
              employee_id: empId,
              employee_name: items[0].employee_name,
              date: selectedDate,
              current_status: openSess ? 'CHECKED IN' : 'CHECKED OUT',
              first_check_in: items[0].check_in_time || null,
              last_check_out: closedSess.length > 0 ? closedSess[closedSess.length - 1].check_out_time || null : null,
              total_worked_minutes: 0,
              total_worked_duration: items.length === 1 && items[0].duration ? items[0].duration : `${items.length} sessions`,
              session_count: items.length,
              sessions: items
            };
          });
          setSummaries(fallbackSummaries);
        }
        setError(null);
      } else if (!silent) {
        setRecords([]);
        setSummaries([]);
      }
    } catch (err: any) {
      console.warn('Failed to load attendance records:', err);
      // Resilient UX: If a background poll hiccup occurs, NEVER wipe out existing valid state
      if (!silent) {
        setError(err.message || 'Failed to load attendance records');
        setRecords([]);
        setSummaries([]);
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
      isFetchingRef.current = false;
    }
  }, [selectedDate, todayStr]);

  // Initial load & when date changes
  useEffect(() => {
    loadPeople();
  }, [loadPeople]);

  useEffect(() => {
    loadRecords(false);

    // Auto-poll records if viewing today's records (every 3 seconds, visibility-aware)
    let timer: NodeJS.Timeout | null = null;
    if (isToday) {
      timer = setInterval(() => {
        if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
          return;
        }
        loadRecords(true);
      }, 3000);
    }


    return () => {
      if (timer) clearInterval(timer);
    };
  }, [selectedDate, isToday, loadRecords]);

  // Date Navigation handlers
  const handlePrevDay = () => {
    const current = parseDDMMYYYY(selectedDate);
    current.setDate(current.getDate() - 1);
    setSelectedDate(formatDateToDDMMYYYY(current));
  };

  const handleNextDay = () => {
    const current = parseDDMMYYYY(selectedDate);
    current.setDate(current.getDate() + 1);
    setSelectedDate(formatDateToDDMMYYYY(current));
  };

  const handleGoToday = () => {
    setSelectedDate(todayStr);
  };

  const handleDateInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.value) return;
    const parts = e.target.value.split('-'); // YYYY-MM-DD
    if (parts.length === 3) {
      setSelectedDate(`${parts[2]}-${parts[1]}-${parts[0]}`);
    }
  };

  // Export CSV with full multi-session logs
  const handleExportCSV = () => {
    if (records.length === 0) {
      alert('No records available to export for this date.');
      return;
    }

    const headers = [
      'Session ID',
      'Employee ID',
      'Employee Name',
      'Date',
      'Session Status',
      'Check-In Time',
      'Check-In Gate',
      'Check-Out Time',
      'Check-Out Gate',
      'Session Duration',
      'Match Score'
    ];

    const rows = records.map(r => [
      r.id,
      r.employee_id,
      `"${r.employee_name.replace(/"/g, '""')}"`,
      r.date,
      r.status,
      r.check_in_time || '',
      `"${(r.check_in_camera || 'Entrance Gate').replace(/"/g, '""')}"`,
      r.check_out_time || '',
      `"${(r.check_out_camera || 'Exit Gate').replace(/"/g, '""')}"`,
      r.duration || '',
      r.match_score ? `${(r.match_score * 100).toFixed(1)}%` : '100%'
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `FaceVault360_Attendance_Sessions_${selectedDate}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Filtered employee summaries
  const filteredSummaries = useMemo(() => {
    return summaries.filter(s => {
      // Search filter
      const matchesSearch = 
        s.employee_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        String(s.employee_id).includes(searchQuery);

      if (!matchesSearch) return false;

      // Status filter
      if (statusFilter === 'checked_in') {
        return s.current_status === 'CHECKED IN';
      }
      if (statusFilter === 'checked_out') {
        return s.current_status === 'CHECKED OUT';
      }
      return true;
    });
  }, [summaries, searchQuery, statusFilter]);

  // Dynamic KPI calculations from summaries
  const stats = useMemo(() => {
    const presentCount = summaries.length;
    const checkedInCount = summaries.filter(s => s.current_status === 'CHECKED IN').length;
    const checkedOutCount = summaries.filter(s => s.current_status === 'CHECKED OUT').length;
    const totalEnrolled = people.length;
    const totalSessions = records.length;
    const attendanceRate = totalEnrolled > 0 
      ? Math.min(100, Math.round((presentCount / totalEnrolled) * 100))
      : 100;

    return {
      presentCount,
      checkedInCount,
      checkedOutCount,
      totalEnrolled,
      totalSessions,
      attendanceRate
    };
  }, [summaries, people, records]);

  // Formatted date label for banner
  const dateDisplayLabel = useMemo(() => {
    const d = parseDDMMYYYY(selectedDate);
    return d.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  }, [selectedDate]);

  return (
    <div className="space-y-6">
      {/* Top Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white tracking-tight">Daily Attendance Dashboard</h1>
            {isToday && (
              <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                Live Feed Active
              </span>
            )}
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Real-time biometric attendance with multiple daily session tracking and total working hours
          </p>
        </div>

        {/* Top Actions: Live Monitor link & CSV Export */}
        <div className="flex items-center gap-3 flex-wrap">
          <Link
            to="/cameras"
            className="flex items-center gap-2 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white rounded-lg border border-slate-700 text-xs font-semibold transition-all shadow-sm"
          >
            <Video className="w-4 h-4 text-blue-400" />
            <span>RTSP Live Monitor</span>
          </Link>

          <button
            onClick={handleExportCSV}
            disabled={records.length === 0}
            className="flex items-center gap-2 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-200 hover:text-white rounded-lg border border-slate-700 text-xs font-semibold transition-all shadow-sm"
            title="Download CSV for this date"
          >
            <Download className="w-4 h-4 text-emerald-400" />
            <span>Export CSV ({records.length})</span>
          </button>

          <button
            onClick={() => {
              loadPeople();
              loadRecords(false);
            }}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition-all shadow-md shadow-blue-600/20"
            title="Refresh Attendance Records"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Enrolled Employees */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Registered Staff</p>
            <h3 className="text-2xl font-bold text-white mt-1">{stats.totalEnrolled}</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">Biometrically enrolled</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <Users className="w-6 h-6" />
          </div>
        </div>

        {/* Present Today */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Present Staff</p>
            <h3 className="text-2xl font-bold text-emerald-400 mt-1">{stats.presentCount}</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {stats.totalEnrolled > 0 ? `${stats.attendanceRate}% staff turnout` : 'No staff registered'}
            </p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <UserCheck className="w-6 h-6" />
          </div>
        </div>

        {/* Currently Checked In (Open Sessions) */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Checked In Now</p>
            <h3 className="text-2xl font-bold text-amber-400 mt-1">{stats.checkedInCount}</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">Active working sessions</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <LogIn className="w-6 h-6" />
          </div>
        </div>

        {/* Total Attendance Sessions Today */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Total Sessions</p>
            <h3 className="text-2xl font-bold text-indigo-400 mt-1">{stats.totalSessions}</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">{stats.checkedOutCount} closed shifts today</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <Layers className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Date Navigation and Controls Bar */}
      <div className="bg-slate-800/70 border border-slate-700/80 rounded-xl p-4 flex flex-col md:flex-row items-center justify-between gap-4 shadow-sm">
        {/* Date Selector buttons */}
        <div className="flex items-center gap-2 flex-wrap w-full md:w-auto">
          <button
            onClick={handlePrevDay}
            className="p-2 bg-slate-900/80 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700 transition-colors"
            title="Previous Day"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <button
            onClick={handleGoToday}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
              isToday 
                ? 'bg-blue-600 text-white border-blue-500 shadow-sm' 
                : 'bg-slate-900/80 hover:bg-slate-700 text-slate-300 border-slate-700'
            }`}
          >
            Today
          </button>

          <button
            onClick={handleNextDay}
            className="p-2 bg-slate-900/80 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700 transition-colors"
            title="Next Day"
          >
            <ChevronRight className="w-4 h-4" />
          </button>

          <div className="relative flex items-center ml-2">
            <input
              type="date"
              value={formatDateToYYYYMMDD(parseDDMMYYYY(selectedDate))}
              onChange={handleDateInputChange}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500 cursor-pointer"
            />
          </div>

          <div className="text-slate-300 text-xs font-medium ml-2 hidden sm:block">
            <span className="text-slate-400">Selected: </span>
            <span className="font-semibold text-white">{dateDisplayLabel}</span>
            <span className="text-slate-500 ml-1 font-mono">({selectedDate})</span>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div className="flex items-center gap-3 w-full md:w-auto flex-wrap">
          {/* Search Box */}
          <div className="relative flex-1 sm:w-60">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search employee or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center bg-slate-900 border border-slate-700 rounded-lg p-0.5 text-xs">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                statusFilter === 'all' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              All ({summaries.length})
            </button>
            <button
              onClick={() => setStatusFilter('checked_in')}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                statusFilter === 'checked_in' ? 'bg-amber-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Checked In ({stats.checkedInCount})
            </button>
            <button
              onClick={() => setStatusFilter('checked_out')}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                statusFilter === 'checked_out' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Checked Out ({stats.checkedOutCount})
            </button>
          </div>

          {/* Toggle Expand All */}
          {summaries.length > 0 && (
            <button
              onClick={toggleExpandAll}
              className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg border border-slate-700 text-xs font-medium transition-colors"
              title="Expand or collapse all session details"
            >
              {expandedEmployees.size === summaries.length ? 'Collapse All' : 'Expand All'}
            </button>
          )}
        </div>
      </div>

      {/* Error alert if any */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs flex items-center gap-3">
          <Clock className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Attendance Table Card */}
      <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl overflow-hidden shadow-lg">
        {isLoading ? (
          <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center">
            <RefreshCw className="w-8 h-8 animate-spin text-blue-400 mb-3" />
            <p className="text-sm font-semibold text-slate-200">Loading daily attendance records...</p>
            <p className="text-xs text-slate-500 mt-1">Retrieving verified biometric sessions for {selectedDate}</p>
          </div>
        ) : filteredSummaries.length === 0 ? (
          <div className="p-16 text-center space-y-3">
            <div className="w-12 h-12 rounded-xl bg-slate-700/50 border border-slate-600/50 flex items-center justify-center text-slate-400 mx-auto">
              <Calendar className="w-6 h-6" />
            </div>
            <p className="text-base font-semibold text-slate-300">
              {searchQuery ? 'No matching employee records found.' : `No attendance recorded for ${selectedDate}.`}
            </p>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              {searchQuery 
                ? 'Try searching with a different employee name or ID.' 
                : 'Biometric entries through the Check-In RTSP Camera will automatically generate attendance sessions here.'}
            </p>
            {!isToday && (
              <button
                onClick={handleGoToday}
                className="mt-2 inline-flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition-colors"
              >
                Go to Today's Records
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-700">
                <tr>
                  <th className="py-3.5 px-3 w-10 text-center font-semibold"></th>
                  <th className="py-3.5 px-4 font-semibold">Employee</th>
                  <th className="py-3.5 px-3 font-semibold">Employee ID</th>
                  <th className="py-3.5 px-3 font-semibold">Current Status</th>
                  <th className="py-3.5 px-4 font-semibold">First Check-In</th>
                  <th className="py-3.5 px-4 font-semibold">Last Check-Out</th>
                  <th className="py-3.5 px-3 font-semibold">Total Worked Duration</th>
                  <th className="py-3.5 px-4 font-semibold text-center">Sessions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50 text-slate-300">
                {filteredSummaries.map((summary) => {
                  const isCheckedIn = summary.current_status === 'CHECKED IN';
                  const isExpanded = expandedEmployees.has(summary.employee_id);

                  // Initials for avatar
                  const initials = summary.employee_name
                    ? summary.employee_name.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase()
                    : 'EMP';

                  return (
                    <React.Fragment key={summary.employee_id}>
                      <tr 
                        onClick={() => toggleExpand(summary.employee_id)}
                        className={`hover:bg-slate-750/60 transition-colors cursor-pointer ${
                          isExpanded ? 'bg-slate-750/40' : ''
                        }`}
                      >
                        {/* Expand/Collapse Toggle Button */}
                        <td className="py-3.5 px-3 text-center">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(summary.employee_id);
                            }}
                            className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                            title={isExpanded ? 'Collapse session details' : 'Expand session details'}
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-blue-400" />
                            ) : (
                              <ChevronRight className="w-4 h-4" />
                            )}
                          </button>
                        </td>

                        {/* Employee Avatar & Name */}
                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center font-bold text-[11px] text-blue-400 flex-shrink-0">
                              {initials}
                            </div>
                            <div>
                              <div className="font-semibold text-white">{summary.employee_name}</div>
                              <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
                                {isCheckedIn ? (
                                  <span className="text-amber-400 flex items-center gap-1 font-medium">
                                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                                    Active Session: {summary.current_check_in || 'Open'}
                                  </span>
                                ) : (
                                  <span className="text-slate-400">
                                    {summary.session_count} completed {summary.session_count === 1 ? 'session' : 'sessions'}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Employee ID */}
                        <td className="py-3.5 px-3 font-mono text-slate-300 font-semibold">
                          #{summary.employee_id}
                        </td>

                        {/* Current Status Badge */}
                        <td className="py-3.5 px-3">
                          {isCheckedIn ? (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/25 shadow-sm">
                              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                              CHECKED IN
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 shadow-sm">
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                              CHECKED OUT
                            </span>
                          )}
                        </td>

                        {/* First Check-In Time */}
                        <td className="py-3.5 px-4">
                          {summary.first_check_in ? (
                            <div className="flex items-center gap-2">
                              <div className="p-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                <LogIn className="w-3 h-3" />
                              </div>
                              <span className="font-semibold text-white font-mono">{summary.first_check_in}</span>
                            </div>
                          ) : (
                            <span className="text-slate-500 font-mono">—</span>
                          )}
                        </td>

                        {/* Last Check-Out Time */}
                        <td className="py-3.5 px-4">
                          {isCheckedIn ? (
                            <div className="flex items-center gap-1.5 text-amber-400 italic">
                              <Clock className="w-3 h-3 text-amber-400 animate-pulse" />
                              <span>Currently in progress</span>
                            </div>
                          ) : summary.last_check_out ? (
                            <div className="flex items-center gap-2">
                              <div className="p-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                                <LogOut className="w-3 h-3" />
                              </div>
                              <span className="font-semibold text-white font-mono">{summary.last_check_out}</span>
                            </div>
                          ) : (
                            <span className="text-slate-500 font-mono">—</span>
                          )}
                        </td>

                        {/* Total Worked Duration */}
                        <td className="py-3.5 px-3">
                          <span className="font-semibold font-mono text-slate-200 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/60 inline-flex items-center gap-1.5">
                            <Clock className="w-3 h-3 text-blue-400" />
                            {summary.total_worked_duration || '0m'}
                          </span>
                        </td>

                        {/* Sessions Count & Details Trigger */}
                        <td className="py-3.5 px-4 text-center">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-700/60 text-slate-300 border border-slate-600/50">
                            <Layers className="w-3 h-3 text-blue-400" />
                            {summary.session_count} {summary.session_count === 1 ? 'Session' : 'Sessions'}
                          </span>
                        </td>
                      </tr>

                      {/* Expanded Accordion: Individual Chronological Sessions Breakdown */}
                      {isExpanded && (
                        <tr className="bg-slate-900/70 border-y border-slate-700/80">
                          <td colSpan={8} className="py-4 px-6">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between text-xs">
                                <div className="flex items-center gap-2 text-slate-300 font-semibold">
                                  <Sparkles className="w-4 h-4 text-blue-400" />
                                  <span>Chronological Session History for {summary.employee_name} ({selectedDate})</span>
                                </div>
                                <span className="text-[11px] text-slate-400">
                                  {summary.sessions.length} total recorded {summary.sessions.length === 1 ? 'session' : 'sessions'}
                                </span>
                              </div>

                              {/* Sessions Grid */}
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {summary.sessions.map((sess, idx) => {
                                  const isSessOpen = Boolean(sess.check_in_time && !sess.check_out_time);
                                  return (
                                    <div 
                                      key={sess.id}
                                      className={`p-3 rounded-xl border transition-all ${
                                        isSessOpen 
                                          ? 'bg-amber-500/5 border-amber-500/30 shadow-sm shadow-amber-500/10' 
                                          : 'bg-slate-800/80 border-slate-700/60'
                                      }`}
                                    >
                                      {/* Header: Session number and status */}
                                      <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-1.5">
                                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-200">
                                            Session #{idx + 1}
                                          </span>
                                          <span className="text-[10px] text-slate-500 font-mono">
                                            (ID: {sess.id})
                                          </span>
                                        </div>
                                        {isSessOpen ? (
                                          <span className="text-[10px] font-bold text-amber-400 flex items-center gap-1">
                                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                                            ACTIVE
                                          </span>
                                        ) : (
                                          <span className="text-[10px] font-semibold text-emerald-400 flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                            CLOSED
                                          </span>
                                        )}
                                      </div>

                                      {/* Times: Check-In -> Check-Out */}
                                      <div className="space-y-1.5 text-[11px]">
                                        <div className="flex items-center justify-between">
                                          <span className="text-slate-400 flex items-center gap-1.5">
                                            <LogIn className="w-3 h-3 text-emerald-400" />
                                            Check-In:
                                          </span>
                                          <span className="font-semibold text-white font-mono">
                                            {sess.check_in_time || '—'}
                                          </span>
                                        </div>
                                        {sess.check_in_camera && (
                                          <div className="text-[10px] text-slate-500 pl-4">
                                            Gate: {sess.check_in_camera}
                                          </div>
                                        )}

                                        <div className="flex items-center justify-between pt-1 border-t border-slate-750">
                                          <span className="text-slate-400 flex items-center gap-1.5">
                                            <LogOut className="w-3 h-3 text-indigo-400" />
                                            Check-Out:
                                          </span>
                                          <span className="font-semibold text-white font-mono">
                                            {sess.check_out_time || (
                                              <span className="text-amber-400 italic">In progress</span>
                                            )}
                                          </span>
                                        </div>
                                        {sess.check_out_camera && (
                                          <div className="text-[10px] text-slate-500 pl-4">
                                            Gate: {sess.check_out_camera}
                                          </div>
                                        )}

                                        <div className="flex items-center justify-between pt-1 border-t border-slate-750 font-semibold">
                                          <span className="text-slate-400">Duration:</span>
                                          <span className="text-blue-400 font-mono">
                                            {sess.duration || (isSessOpen ? 'In progress' : '0m')}
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer Summary */}
        <div className="px-4 py-3 bg-slate-900/60 border-t border-slate-700/80 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-400 gap-2">
          <div>
            Showing <span className="text-white font-semibold">{filteredSummaries.length}</span> of{' '}
            <span className="text-white font-semibold">{summaries.length}</span> employees for{' '}
            <span className="text-white font-mono">{selectedDate}</span> ({records.length} total attendance sessions)
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span>Multi-Session State Machine Active</span>
          </div>
        </div>
      </div>
    </div>
  );
};
