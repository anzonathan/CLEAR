const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

export function getCsrfToken(): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const csrfHeader: Record<string, string> =
    method === 'GET' || method === 'HEAD' ? {} : { 'X-CSRFToken': getCsrfToken() };
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeader,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(error.error || error.detail || 'Request failed');
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// User
export interface User {
  id: string;
  name: string;
  email: string;
  role: 'user' | 'admin' | 'developer';
  image: string | null;
  created_at: string;
}

export async function getMe() {
  return request<User>('/api/users/me/');
}

// Pair codes
export async function generatePairCode() {
  return request<{ code: string; expires_at: string }>('/api/pair/generate/', {
    method: 'POST',
  });
}

export async function joinPairCode(code: string) {
  return request<{
    connectionId: string;
    connectedWith: { id: string; name: string; email: string; image: string | null };
  }>('/api/pair/join/', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

// Connections
export interface Connection {
  id: string;
  user_a: string;
  user_b: string;
  other_id: string;
  other_name: string;
  other_email: string;
  other_image: string | null;
  active: boolean;
  created_at: string;
}

export interface SharedVideo {
  id: string;
  uploader_id: string;
  uploader_name?: string;
  connection_id: string;
  file_path: string;
  file_name: string;
  file_size: number | null;
  mime_type: string | null;
  type: 'recorded' | 'live';
  thumbnail_path: string | null;
  duration_seconds: number | null;
  processed: boolean;
  detection_results: unknown | null;
  created_at: string;
}

export interface ConnectionDetail extends Connection {
  videos: SharedVideo[];
}

export async function getConnections() {
  return request<Connection[]>('/api/connections/');
}

export async function getConnection(id: string) {
  return request<ConnectionDetail>(`/api/connections/${id}/`);
}

export async function endConnection(id: string) {
  return request<{ success: boolean }>(`/api/connections/${id}/`, {
    method: 'DELETE',
  });
}

// Videos
export async function getVideos() {
  return request<SharedVideo[]>('/api/videos/');
}

export async function getVideo(id: string) {
  return request<SharedVideo>(`/api/videos/${id}/`);
}

// Live sessions
export interface LiveSession {
  id: string;
  connection_id: string;
  started_by_id: string;
  other_name: string;
  started_at: string;
  active: boolean;
}

export async function startLiveSession(connectionId: string) {
  return request<{ sessionId: string }>('/api/live/start/', {
    method: 'POST',
    body: JSON.stringify({ connectionId }),
  });
}

export async function endLiveSession(sessionId: string) {
  return request<{ success: boolean }>('/api/live/end/', {
    method: 'POST',
    body: JSON.stringify({ sessionId }),
  });
}

export async function getActiveSessions() {
  return request<LiveSession[]>('/api/live/active/');
}

// Admin
export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: 'user' | 'admin' | 'developer';
  image: string | null;
  created_at: string;
  email_verified: boolean;
  is_active: boolean;
}

export interface AdminStats {
  totalUsers: number;
  activeConnections: number;
  totalVideos: number;
  activeSessions: number;
}

export async function getAdminUsers() {
  return request<AdminUser[]>('/api/admin/users/');
}

export async function updateUserRole(userId: string, role: string) {
  return request<{ success: boolean }>(`/api/admin/users/${userId}/role/`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
}

export async function deleteUser(userId: string) {
  return request<{ success: boolean }>(`/api/admin/users/${userId}/`, {
    method: 'DELETE',
  });
}

export async function getAdminStats() {
  return request<AdminStats>('/api/admin/stats/');
}

// Developer
export async function getDevVideos() {
  return request<SharedVideo[]>('/api/dev/videos/');
}

// Field / Camera
export interface Camera {
  id: string;
  name: string;
  token: string;
  source: 'browser' | 'rtsp';
  rtsp_url: string;
  end: 'none' | 'end_a' | 'end_b';
  court_mode: 'singles' | 'doubles';
  calib_method: 'manual' | 'auto' | 'segmentation';
  active: boolean;
  online: boolean;
  overlays: Record<string, boolean>;
  detector: Record<string, number>;
  calibration_data: unknown | null;
}

export async function getCameras() {
  return request<{ cameras: Camera[]; active_id: string | null; match_id: string | null }>(
    '/api/field/cameras/'
  );
}

export async function createCamera(data: { name: string; source?: string; rtsp_url?: string; end?: string }) {
  return request<Camera>('/api/field/cameras/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateCamera(id: string, data: Partial<Camera>) {
  return request<Camera>(`/api/field/cameras/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteCamera(id: string) {
  return request<{ ok: boolean }>(`/api/field/cameras/${id}/`, {
    method: 'DELETE',
  });
}

export async function activateCamera(id: string) {
  return request<Camera>(`/api/field/cameras/${id}/activate/`, {
    method: 'POST',
  });
}

export async function getFieldHealth() {
  return request<{
    ok: boolean;
    active_id: string | null;
    match_id: string | null;
    camera_count: number;
    auth_enabled: boolean;
  }>('/api/field/health/');
}

// Games: a pair schedules a game; each player films one end with their phone.
export type GameEnd = 'end_a' | 'end_b';
export type GameStatus = 'scheduled' | 'live' | 'completed' | 'cancelled';
export type AnalysisStatus = 'none' | 'running' | 'done' | 'failed';

export interface UserBrief {
  id: string;
  name: string;
  email: string;
}

export interface CameraSlotState {
  id: string;
  online: boolean;
  active: boolean;
  fps?: number | null;
  calibrated?: boolean;
  missing?: boolean;
}

export interface GameEndSlot {
  user: UserBrief | null;
  camera: CameraSlotState | null;
}

export interface AnalysisReport {
  camera_id?: string;
  calibrated?: boolean;
  error?: string;
  total_frames?: number;
  fps?: number;
  ball_tracking?: {
    tracked_frames: number;
    coverage_pct: number;
    avg_speed_kmh: number;
    max_speed_kmh: number;
    rally_strokes: number;
  };
  line_calling?: {
    total_bounces: number;
    in_calls: number;
    out_calls: number;
    doubt_zone_calls: number;
  };
  foot_faults?: unknown[];
  service_faults?: unknown[];
}

export interface GameAnalysis {
  error?: string;
  finished_at?: string;
  cameras?: Partial<Record<GameEnd | string, AnalysisReport>>;
}

export interface Game {
  id: string;
  title: string;
  connection: string;
  scheduled_at: string;
  court_mode: 'singles' | 'doubles';
  status: GameStatus;
  partner: UserBrief | null;
  ends: Record<GameEnd, GameEndSlot>;
  my_end: GameEnd | null;
  my_camera: { id: string; token: string | null } | null;
  started_at: string | null;
  ended_at: string | null;
  analysis_status: AnalysisStatus;
  analysis: GameAnalysis | null;
  created_at: string;
}

export async function getGames(params: { connection?: string; upcoming?: boolean } = {}) {
  const q = new URLSearchParams();
  if (params.connection) q.set('connection', params.connection);
  if (params.upcoming) q.set('upcoming', '1');
  const qs = q.toString();
  return request<Game[]>(`/api/games/${qs ? `?${qs}` : ''}`);
}

export async function getGame(id: string) {
  return request<Game>(`/api/games/${id}/`);
}

export async function scheduleGame(data: {
  connection_id: string;
  scheduled_at: string;
  court_mode: 'singles' | 'doubles';
  title?: string;
}) {
  return request<Game>('/api/games/', { method: 'POST', body: JSON.stringify(data) });
}

export async function cancelGame(id: string) {
  return request<Game>(`/api/games/${id}/`, { method: 'DELETE' });
}

export async function claimGameEnd(id: string, end: GameEnd) {
  return request<Game>(`/api/games/${id}/camera/`, { method: 'POST', body: JSON.stringify({ end }) });
}

export async function releaseGameEnd(id: string) {
  return request<Game>(`/api/games/${id}/camera/`, { method: 'DELETE' });
}

export async function startGame(id: string) {
  return request<Game>(`/api/games/${id}/start/`, { method: 'POST' });
}

export async function stopGame(id: string) {
  return request<Game>(`/api/games/${id}/stop/`, { method: 'POST' });
}

// Developer view of games
export interface DevGame {
  id: string;
  title: string;
  scheduled_at: string;
  court_mode: 'singles' | 'doubles';
  status: GameStatus;
  players: (UserBrief | null)[];
  ends: Record<GameEnd, GameEndSlot>;
  match_id: string;
  recording_id: string;
  recorded: number;
  started_at: string | null;
  ended_at: string | null;
  analysis_status: AnalysisStatus;
  analysis: GameAnalysis | null;
  created_at: string;
}

export async function getDevGames(status?: GameStatus) {
  return request<DevGame[]>(`/api/dev/games/${status ? `?status=${status}` : ''}`);
}

export async function getDevGame(id: string) {
  return request<DevGame>(`/api/dev/games/${id}/`);
}

export async function analyzeDevGame(id: string) {
  return request<DevGame>(`/api/dev/games/${id}/analyze/`, { method: 'POST' });
}

export async function stopDevGame(id: string) {
  return request<DevGame>(`/api/dev/games/${id}/stop/`, { method: 'POST' });
}

export function devGameChartUrl(id: string, end: GameEnd) {
  return `${API_URL}/api/dev/games/${id}/chart/${end}/`;
}
