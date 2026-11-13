const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(error.error || error.detail || 'Request failed');
  }

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
