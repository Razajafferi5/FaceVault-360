export interface Person {
  id: number;
  person_identifier: string;
  name: string;
  department: string | null;
  role: string | null;
  notes: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  embedding_count: number;
}

export interface PersonCreate {
  person_identifier: string;
  name: string;
  department?: string;
  role?: string;
  notes?: string;
}

export interface FaceDetectionResult {
  bbox: number[];
  confidence: number;
  name: string | null;
  person_id: number | null;
  similarity: number;
  authorized: boolean;
  status: string;
  pose_label: string;
  pose_yaw: number;
  pose_pitch: number;
  quality_score: number;
  liveness_score: number;
  is_unknown?: boolean;
}

export interface CameraGuidance {
  face_detected: boolean;
  position_ok: boolean;
  message: string;
  severity: 'good' | 'warning' | 'error';
  status_color?: 'red' | 'green' | 'yellow';
  yaw: number;
  pitch: number;
  roll: number;
  action?: string;
}

export interface CameraHealth {
  online: boolean;
  fps: number;
  latency_ms: number;
  last_frame: string | null;
}

export interface RecognitionMessage {
  type: string;
  faces: FaceDetectionResult[];
  camera_guidance: CameraGuidance;
  camera_health: CameraHealth;
  timestamp: string;
}

export interface AccessEvent {
  id: number;
  person_id: number | null;
  recognized_name: string | null;
  timestamp: string;
  confidence: number;
  status: string;
  authorization_result: string;
  pose_yaw: number | null;
  pose_pitch: number | null;
  quality_score: number | null;
  camera_id: string;
  failure_reason: string | null;
}

export interface DashboardSummary {
  todays_entries: number;
  authorized_count: number;
  denied_count: number;
  registered_people: number;
  system_online: boolean;
}

export interface DailyStats {
  date: string;
  total: number;
  authorized: number;
  denied: number;
}

export interface SystemStatus {
  status: string;
  camera_online: boolean;
  fps: number;
  avg_inference_ms: number;
  recognition_latency_ms: number;
  cpu_percent: number;
  ram_percent: number;
  ram_used_mb: number;
  registered_persons: number;
  total_embeddings: number;
  faiss_index_size: number;
  uptime_seconds: number;
}

export interface EnrollmentSession {
  session_id: string;
  person_name: string;
  total_poses: number;
  poses: PoseStep[];
}

export interface PoseStep {
  step: number;
  label: string;
  instruction: string;
  target_yaw_range: [number, number];
  target_pitch_range: [number, number];
}

export interface EnrollmentFrameResult {
  status?: string;
  captured: boolean;
  message?: string;
  instruction: string;
  status_color?: string;
  detected_bbox?: number[] | null;
  face_count?: number;
  hold_progress?: number;
  is_wrong_direction?: boolean;
  warning_message?: string | null;
  direction_hint?: string | null;
  current_step: number;
  total_steps: number;
  pose_label: string;
  guidance?: CameraGuidance | null;
  quality_score: number | null;
  completed: boolean;
  current_yaw?: number;
  current_pitch?: number;
}

export type EventFilter = {
  date_from?: string;
  date_to?: string;
  person_id?: number;
  status?: string;
  camera_id?: string;
  min_confidence?: number;
  max_confidence?: number;
}

export interface RTSPCameraDiagnostics {
  camera_id?: number;
  camera_name?: string;
  role?: string;
  redacted_url?: string;
  host?: string;
  port?: number;
  path?: string;
  state?: string;
  transport?: string;
  actual_fps?: number;
  stream_fps?: number;
  display_fps?: number;
  ai_fps?: number;
  avg_inference_ms?: number;
  latency_ms?: number;
  dropped_frames?: number;
  queue_size?: number;
  faces_detected?: number;
  faces_recognized?: number;
  unknown_count?: number;
  too_small_count?: number;
  socket_reachable?: boolean;
  reconnect_attempt?: number;
  reconnect_count?: number;
  last_connected_time?: string | null;
  last_frame_time?: string | null;
  last_connected?: string | null;
  last_frame?: string | null;
  last_error?: string | null;
  backend_local_ip?: string;
  hint?: string;
  [key: string]: any;
}

export interface RTSPCamera {
  id: number;
  name: string;
  rtsp_url: string;
  redacted_url?: string;
  username?: string;
  location?: string;
  mode: 'CHECK-IN' | 'CHECK-OUT' | 'COMBINED';
  camera_role?: 'CHECK-IN' | 'CHECK-OUT' | 'COMBINED' | string;
  enabled: boolean;
  status: 'connected' | 'disconnected' | 'reconnecting' | 'connecting' | string;
  live_status?: 'connected' | 'disconnected' | 'reconnecting' | 'connecting' | string;
  is_connected?: boolean;
  status_message?: string;
  last_seen?: string;
  has_password: boolean;
  active_persons?: number;
  actual_fps?: number;
  stream_fps?: number;
  display_fps?: number;
  ai_fps?: number;
  avg_inference_ms?: number;
  latency_ms?: number;
  dropped_frames?: number;
  queue_size?: number;
  is_receiving_frames?: boolean;
  reconnect_attempt?: number;
  last_connected_time?: string | null;
  last_frame_time?: string | null;
  diagnostics?: RTSPCameraDiagnostics;
  recent_events?: Array<{
    timestamp: string;
    employee_id: number;
    employee_name: string;
    action: string;
    time: string;
    score: string;
    camera: string;
    mode: string;
  }>;
  latest_detections?: Array<any>;
  created_at?: string;
  updated_at?: string;
}

export interface RTSPCameraCreate {
  name: string;
  rtsp_url: string;
  username?: string;
  password?: string;
  location?: string;
  mode: 'CHECK-IN' | 'CHECK-OUT' | 'COMBINED';
  enabled?: boolean;
}

export interface AttendanceRecord {
  id: number;
  employee_id: number;
  employee_name: string;
  date: string;
  time: string;
  status: string;
  match_score: number;
  check_in_time?: string;
  check_out_time?: string;
  duration?: string | null;
  check_in_camera?: string;
  check_out_camera?: string;
  created_at?: string;
}

export interface EmployeeDailySummary {
  employee_id: number;
  employee_name: string;
  date: string;
  current_status: 'CHECKED IN' | 'CHECKED OUT';
  first_check_in: string | null;
  last_check_out: string | null;
  total_worked_minutes: number;
  total_worked_duration: string;
  session_count: number;
  active_session_id?: number | null;
  current_check_in?: string | null;
  sessions: AttendanceRecord[];
}

export interface UnknownPersonEvent {
  id: number;
  event_uuid: string;
  detected_at: string;
  timestamp?: string;
  date_str: string;
  time_str: string;
  camera_id?: number | null;
  camera_name: string;
  camera_role: 'CHECK-IN' | 'CHECK-OUT' | string;
  snapshot_path?: string | null;
  snapshot_url?: string | null;
  face_confidence: number;
  recognition_status: string;
  access_status: 'PENDING' | 'APPROVED' | 'DENIED' | 'ENROLLED' | string;
  approved_by_id?: number | null;
  approved_by_name?: string | null;
  approved_at?: string | null;
  enrolled_person_id?: number | null;
  enrollment_method?: 'RTSP' | 'WEBCAM' | string | null;
  enrolled_by?: string | null;
  enrolled_at?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  first_seen_time_str?: string | null;
  last_seen_time_str?: string | null;
  detection_count?: number;
  duration_seconds?: number;
  best_quality_score?: number;
  notes?: string | null;
}


export interface UnknownPersonStats {
  total_today: number;
  pending_count: number;
  approved_count: number;
  denied_count: number;
  enrolled_count: number;
}

export interface UserSwitchOption {
  id: number;
  name: string;
  role: string;
  is_owner: boolean;
  department?: string | null;
  email: string;
}

