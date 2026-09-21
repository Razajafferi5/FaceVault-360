import { EventFilter, Person, PersonCreate, DashboardSummary, SystemStatus, RTSPCamera, RTSPCameraCreate, UnknownPersonEvent, UnknownPersonStats, UserSwitchOption } from '../types';

function getBaseUrl(): string {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  // In development (Vite dev server on port 5173), target FastAPI directly on port 8000.
  // This completely bypasses Vite's single-threaded Node.js proxy, avoiding HTTP socket pool
  // saturation and eliminates artificial request timeouts caused by streaming connections.
  if (typeof window !== 'undefined' && window.location.port === '5173') {
    return `http://${window.location.hostname}:8000/api`;
  }
  return '/api';
}

export const BASE_URL = getBaseUrl();

function getHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  };
}

interface FetchOptions extends RequestInit {
  timeoutMs?: number;
}

async function fetchWithAuth(url: string, options: FetchOptions = {}, retryCount: number = 1): Promise<any> {
  let headers = getHeaders();
  if (options.body instanceof FormData || !options.body) {
    delete (headers as any)['Content-Type'];
  }
  
  const timeoutMs = options.timeoutMs || 20000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BASE_URL}${url}`, {
      ...options,
      signal: options.signal || controller.signal,
      headers: { ...headers, ...options.headers }
    });
    clearTimeout(timeoutId);
    if (!response.ok) {
      let errorDetail = '';
      try {
        const errData = await response.json();
        errorDetail = errData.detail || errData.message || '';
      } catch {
        // ignore
      }
      throw new Error(errorDetail ? errorDetail : `API Error: ${response.status} ${response.statusText}`);
    }
    return response.json();
  } catch (err: any) {
    clearTimeout(timeoutId);

    // Auto-retry once for idempotent GET requests if aborted due to timeout or network glitch
    const isGet = !options.method || options.method.toUpperCase() === 'GET';
    if (retryCount > 0 && isGet && (err.name === 'AbortError' || err.message?.includes('Failed to fetch'))) {
      await new Promise(r => setTimeout(r, 400));
      return fetchWithAuth(url, options, retryCount - 1);
    }

    if (err.name === 'AbortError') {
      throw new Error('Request timed out. Please retry.');
    }
    throw err;
  }
}

export const api = {
  getPersons: async (): Promise<Person[]> => {
    const res = await fetchWithAuth('/persons');
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  },
  createPerson: (data: PersonCreate) => fetchWithAuth('/persons', { method: 'POST', body: JSON.stringify(data) }),
  getPerson: (id: number) => fetchWithAuth(`/persons/${id}`),
  updatePerson: (id: number, data: Partial<Person>) => fetchWithAuth(`/persons/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePerson: (id: number) => fetchWithAuth(`/persons/${id}`, { method: 'DELETE' }),
  
  startEnrollment: (personId: number) => fetchWithAuth('/enrollment/start', {
    method: 'POST',
    body: JSON.stringify({ person_id: personId })
  }),
  submitEnrollmentFrame: (sessionId: string, base64Frame: string) => fetchWithAuth(`/enrollment/frame?session_id=${sessionId}`, {
    method: 'POST',
    body: JSON.stringify({ frame: base64Frame })
  }),
  completeEnrollment: (sessionId: string) => fetchWithAuth(`/enrollment/complete?session_id=${sessionId}`, {
    method: 'POST'
  }),
  recognizeFrame: (base64Frame: string) => fetchWithAuth('/recognition', {
    method: 'POST',
    body: JSON.stringify({ frame: base64Frame })
  }),
  releaseCamera: () => fetchWithAuth('/system/camera/release', { method: 'POST' }),
  startCamera: () => fetchWithAuth('/system/camera/start', { method: 'POST' }),

  getLogs: async (filters?: EventFilter) => {
    const cleanFilters: any = {};
    if (filters) {
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') {
          cleanFilters[k] = v;
        }
      });
    }
    const params = new URLSearchParams(cleanFilters);
    const res = await fetchWithAuth(`/logs?${params.toString()}`);
    return res.items || res;
  },
  
  getAnalytics: (days: number = 7) => fetchWithAuth(`/analytics/trends?days=${days}`),
  getDashboardSummary: (): Promise<DashboardSummary> => fetchWithAuth('/analytics/summary'),
  getSystemStatus: (): Promise<SystemStatus> => fetchWithAuth('/system/status'),
  
  getSettings: () => fetchWithAuth('/system/settings'),
  updateSettings: (data: any) => fetchWithAuth('/system/settings', { method: 'PUT', body: JSON.stringify(data) }),
  
  getTodayAttendance: () => fetchWithAuth('/attendance/today'),
  getAttendanceByDate: (date: string) => fetchWithAuth(`/attendance/by-date?date=${encodeURIComponent(date)}`),
  getAttendanceHistory: (limit: number = 50) => fetchWithAuth(`/attendance/history?limit=${limit}`),
  markAttendance: (employeeId: number, matchScore: number = 1.0, employeeName?: string) =>
    fetchWithAuth('/attendance/mark', {
      method: 'POST',
      body: JSON.stringify({ employee_id: employeeId, match_score: matchScore, employee_name: employeeName })
    }),
  verifyAndMarkAttendance: (base64Frame: string) =>
    fetchWithAuth('/attendance/verify-and-mark', {
      method: 'POST',
      body: JSON.stringify({ frame: base64Frame })
    }),

  // RTSP Camera Management
  getCameras: (enabledOnly: boolean = false): Promise<{ success: boolean; items: RTSPCamera[]; count: number }> =>
    fetchWithAuth(`/cameras?enabled_only=${enabledOnly}`),
  
  getCamera: (id: number): Promise<{ success: boolean; camera: RTSPCamera }> =>
    fetchWithAuth(`/cameras/${id}`),

  createCamera: (data: RTSPCameraCreate): Promise<{ success: boolean; message: string; camera: RTSPCamera }> =>
    fetchWithAuth('/cameras', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  updateCamera: (id: number, data: Partial<RTSPCameraCreate>): Promise<{ success: boolean; message: string; camera: RTSPCamera }> =>
    fetchWithAuth(`/cameras/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  deleteCamera: (id: number): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth(`/cameras/${id}`, {
      method: 'DELETE'
    }),

  toggleCamera: (id: number): Promise<{ success: boolean; enabled: boolean; message: string }> =>
    fetchWithAuth(`/cameras/${id}/toggle`, {
      method: 'POST'
    }),

  testCameraConnection: (data: { rtsp_url: string; username?: string; password?: string }) =>
    fetchWithAuth('/cameras/test-connection', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  getCameraStatus: (id: number) => fetchWithAuth(`/cameras/${id}/status`),

  getCameraStreamUrl: (id: number): string => `${BASE_URL}/cameras/${id}/stream`,

  getAttendanceCameraStatus: () => fetchWithAuth('/cameras/attendance/status'),

  getAttendanceCameraStreamUrl: (): string => `${BASE_URL}/cameras/attendance/stream`,

  getCheckinCameraStatus: () => fetchWithAuth('/cameras/checkin/status'),

  getCheckinStreamUrl: (): string => `${BASE_URL}/cameras/checkin/stream`,

  getCheckoutCameraStatus: () => fetchWithAuth('/cameras/checkout/status'),

  getCheckoutStreamUrl: (): string => `${BASE_URL}/cameras/checkout/stream`,

  configureCheckinCamera: (data: RTSPCameraCreate) =>
    fetchWithAuth('/cameras/checkin/config', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  configureCheckoutCamera: (data: RTSPCameraCreate) =>
    fetchWithAuth('/cameras/checkout/config', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  connectCamera: (id: number): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth(`/cameras/${id}/connect`, { method: 'POST' }),

  disconnectCamera: (id: number): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth(`/cameras/${id}/disconnect`, { method: 'POST' }),

  reconnectCamera: (id: number): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth(`/cameras/${id}/reconnect`, { method: 'POST' }),

  connectCheckinCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkin/connect', { method: 'POST' }),

  disconnectCheckinCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkin/disconnect', { method: 'POST' }),

  reconnectCheckinCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkin/reconnect', { method: 'POST' }),

  connectCheckoutCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkout/connect', { method: 'POST' }),

  disconnectCheckoutCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkout/disconnect', { method: 'POST' }),

  reconnectCheckoutCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkout/reconnect', { method: 'POST' }),

  toggleCheckinCamera: (): Promise<{ success: boolean; enabled: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkin/toggle', { method: 'POST' }),

  deleteCheckinCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkin', { method: 'DELETE' }),

  toggleCheckoutCamera: (): Promise<{ success: boolean; enabled: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkout/toggle', { method: 'POST' }),

  deleteCheckoutCamera: (): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth('/cameras/checkout', { method: 'DELETE' }),

  // Unknown Persons & Visitor Approval (Owner-Only)
  getUnknownPersons: (params?: { skip?: number; limit?: number; date?: string; status?: string; camera_role?: string }): Promise<{ items: UnknownPersonEvent[]; total: number; skip: number; limit: number }> => {
    const query = new URLSearchParams();
    if (params?.skip !== undefined) query.set('skip', params.skip.toString());
    if (params?.limit !== undefined) query.set('limit', params.limit.toString());
    if (params?.date) query.set('date', params.date);
    if (params?.status) query.set('status', params.status);
    if (params?.camera_role) query.set('camera_role', params.camera_role);
    const qs = query.toString();
    return fetchWithAuth(`/unknown-persons${qs ? `?${qs}` : ''}`);
  },

  getUnknownStats: (): Promise<UnknownPersonStats> =>
    fetchWithAuth('/unknown-persons/stats/today'),

  getUnknownEvent: (id: number): Promise<UnknownPersonEvent> =>
    fetchWithAuth(`/unknown-persons/${id}`),

  approveUnknownPerson: (id: number, notes?: string): Promise<UnknownPersonEvent> =>
    fetchWithAuth(`/unknown-persons/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ notes })
    }),

  denyUnknownPerson: (id: number, notes?: string): Promise<UnknownPersonEvent> =>
    fetchWithAuth(`/unknown-persons/${id}/deny`, {
      method: 'POST',
      body: JSON.stringify({ notes })
    }),

  enrollUnknownPerson: (id: number, enrolledPersonId?: number): Promise<UnknownPersonEvent> =>
    fetchWithAuth(`/unknown-persons/${id}/enroll${enrolledPersonId ? `?enrolled_person_id=${enrolledPersonId}` : ''}`, {
      method: 'POST'
    }),

  deleteUnknownPerson: (id: number): Promise<{ success: boolean; message: string }> =>
    fetchWithAuth(`/unknown-persons/${id}`, { method: 'DELETE' }),

  // User Switching & Profile (for Testing & Multi-User)
  getMe: (): Promise<any> =>
    fetchWithAuth('/auth/me'),

  getUsersList: (): Promise<UserSwitchOption[]> =>
    fetchWithAuth('/auth/users-list'),

  switchUser: (personId?: number, role?: string): Promise<{ access_token: string; token_type: string; role: string; user: any }> =>
    fetchWithAuth('/auth/switch-user', {
      method: 'POST',
      body: JSON.stringify({ person_id: personId, role })
    }),

  login: (data: any) => {
    // Form data for OAuth2 password flow
    const formData = new URLSearchParams();
    formData.append('username', data.username);
    formData.append('password', data.password);
    return fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString()
    }).then(res => {
      if (!res.ok) throw new Error('Login failed');
      return res.json();
    });
  },

  loginJson: (data: { username: string; password: string }): Promise<{ access_token: string; token_type: string; role: string; full_name?: string; username: string }> =>
    fetchWithAuth('/auth/login-json', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  signup: (data: { username: string; password: string; full_name?: string; email?: string }): Promise<{ access_token: string; token_type: string; role: string; full_name?: string; username: string; message?: string }> =>
    fetchWithAuth('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  logout: async (): Promise<void> => {
    try {
      await fetchWithAuth('/auth/logout', { method: 'POST' });
    } catch {
      // ignore network errors on logout
    }
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_info');
  },

  evaluateRtspFrame: (data: { camera_id?: number; frame_base64?: string }): Promise<{
    valid: boolean;
    reason?: string;
    face_count: number;
    bbox?: number[];
    blur_variance?: number;
    pose_ok?: boolean;
    size_ok?: boolean;
    quality_score?: number;
    yaw?: number;
    pitch?: number;
  }> =>
    fetchWithAuth('/unknown-persons/eval-rtsp-frame', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  enrollUnknownFromRtsp: (eventId: number, data: {
    name: string;
    employee_id?: string;
    department?: string;
    role?: string;
    camera_id?: number;
    frames_base64?: string[];
  }): Promise<{ success: boolean; person: any; event: any }> =>
    fetchWithAuth(`/unknown-persons/${eventId}/enroll-rtsp`, {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  // Personal Staff Attendance Endpoints
  getMyTodayAttendance: (): Promise<{
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
  }> => fetchWithAuth('/attendance/my-today'),

  getMyAttendanceHistory: (limit: number = 100): Promise<{
    success: boolean;
    count: number;
    employee_id: number | null;
    records: any[];
  }> => fetchWithAuth(`/attendance/my-history?limit=${limit}`),

  // Owner Management, Role Management & Audit Logs
  changeOwner: (data: {
    target_user_id?: number;
    target_username?: string;
    new_role_for_previous_owner?: string;
  }): Promise<{
    success: boolean;
    message: string;
    new_owner: any;
  }> => fetchWithAuth('/auth/change-owner', {
    method: 'POST',
    body: JSON.stringify(data)
  }),

  updateUserRole: (userId: number, role: string): Promise<{
    success: boolean;
    user_id: number;
    username: string;
    new_role: string;
  }> => fetchWithAuth(`/auth/users/${userId}/role`, {
    method: 'PUT',
    body: JSON.stringify({ role })
  }),

  getAuditLogs: (): Promise<{
    success: boolean;
    logs: Array<{
      id: number;
      actor_id: number;
      actor_name: string;
      actor_role: string;
      action: string;
      target_entity: string;
      details: string;
      timestamp: string;
    }>;
  }> => fetchWithAuth('/auth/audit-logs'),

  getSystemUsers: (): Promise<Array<{
    id: number;
    username: string;
    role: string;
    is_active: boolean;
  }>> => fetchWithAuth('/auth/users'),

  createSystemUser: (data: {
    username: string;
    password: string;
    role: string;
  }) => fetchWithAuth('/auth/users', {
    method: 'POST',
    body: JSON.stringify(data)
  }),

  deleteSystemUser: (userId: number) => fetchWithAuth(`/auth/users/${userId}`, {
    method: 'DELETE'
  })
};


