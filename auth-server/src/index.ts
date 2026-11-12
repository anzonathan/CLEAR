import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { cors } from "hono/cors";
import { auth, trustedOrigins, pool } from "./auth.js";
import { nanoid } from "nanoid";

const app = new Hono();

// Health check
app.get("/health", (c) => c.json({ ok: true, ts: Date.now() }));

// CORS for all API routes
app.use(
  "/api/*",
  cors({
    origin: trustedOrigins,
    credentials: true,
    allowHeaders: ["Content-Type", "Authorization", "X-Requested-With"],
    allowMethods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  })
);

// Auth routes
app.on(["POST", "GET"], "/api/auth/*", (c) => auth.handler(c.req.raw));

// Helper to get session from request
async function getSession(c: any) {
  const session = await auth.api.getSession({ headers: c.req.raw.headers });
  return session;
}

// Helper to require auth
async function requireAuth(c: any) {
  const session = await getSession(c);
  if (!session?.user) {
    return null;
  }
  return session;
}

// Helper to require specific roles
async function requireRole(c: any, roles: string[]) {
  const session = await requireAuth(c);
  if (!session) return null;

  const result = await pool.query('SELECT role FROM "user" WHERE id = $1', [
    session.user.id,
  ]);
  const role = result.rows[0]?.role ?? "user";

  if (!roles.includes(role)) {
    return null;
  }

  return { ...session, role };
}

// ============ PAIR CODE ROUTES ============

// Generate pair code
app.post("/api/pair/generate", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  // Generate 6-character alphanumeric code
  const code = nanoid(6).toUpperCase();
  const id = nanoid();
  const expiresAt = new Date(Date.now() + 10 * 60 * 1000); // 10 minutes

  await pool.query(
    `INSERT INTO pair_codes (id, code, creator_id, expires_at)
     VALUES ($1, $2, $3, $4)`,
    [id, code, session.user.id, expiresAt]
  );

  return c.json({ code, expiresAt });
});

// Join via pair code
app.post("/api/pair/join", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const { code } = await c.req.json();

  // Find valid pair code
  const result = await pool.query(
    `SELECT * FROM pair_codes
     WHERE code = $1 AND used = false AND expires_at > NOW()`,
    [code.toUpperCase()]
  );

  if (result.rows.length === 0) {
    return c.json({ error: "Invalid or expired code" }, 400);
  }

  const pairCode = result.rows[0];

  // Can't pair with yourself
  if (pairCode.creator_id === session.user.id) {
    return c.json({ error: "Cannot pair with yourself" }, 400);
  }

  // Check if connection already exists
  const existingConn = await pool.query(
    `SELECT id FROM connections
     WHERE (user_a = $1 AND user_b = $2) OR (user_a = $2 AND user_b = $1)`,
    [pairCode.creator_id, session.user.id]
  );

  if (existingConn.rows.length > 0) {
    return c.json({ error: "Already connected", connectionId: existingConn.rows[0].id }, 400);
  }

  // Mark code as used
  await pool.query(
    `UPDATE pair_codes SET used = true, used_by = $1, used_at = NOW()
     WHERE id = $2`,
    [session.user.id, pairCode.id]
  );

  // Create connection
  const connectionId = nanoid();
  await pool.query(
    `INSERT INTO connections (id, user_a, user_b, pair_code_id)
     VALUES ($1, $2, $3, $4)`,
    [connectionId, pairCode.creator_id, session.user.id, pairCode.id]
  );

  // Get creator info
  const creator = await pool.query(
    'SELECT id, name, email, image FROM "user" WHERE id = $1',
    [pairCode.creator_id]
  );

  return c.json({
    connectionId,
    connectedWith: creator.rows[0],
  });
});

// Get my connections
app.get("/api/connections", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const result = await pool.query(
    `SELECT c.*,
      CASE WHEN c.user_a = $1 THEN u2.id ELSE u1.id END as other_id,
      CASE WHEN c.user_a = $1 THEN u2.name ELSE u1.name END as other_name,
      CASE WHEN c.user_a = $1 THEN u2.email ELSE u1.email END as other_email,
      CASE WHEN c.user_a = $1 THEN u2.image ELSE u1.image END as other_image
     FROM connections c
     JOIN "user" u1 ON c.user_a = u1.id
     JOIN "user" u2 ON c.user_b = u2.id
     WHERE (c.user_a = $1 OR c.user_b = $1) AND c.active = true
     ORDER BY c.created_at DESC`,
    [session.user.id]
  );

  return c.json(result.rows);
});

// Get connection detail
app.get("/api/connections/:id", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const { id } = c.req.param();

  const result = await pool.query(
    `SELECT c.*,
      CASE WHEN c.user_a = $1 THEN u2.id ELSE u1.id END as other_id,
      CASE WHEN c.user_a = $1 THEN u2.name ELSE u1.name END as other_name,
      CASE WHEN c.user_a = $1 THEN u2.email ELSE u1.email END as other_email,
      CASE WHEN c.user_a = $1 THEN u2.image ELSE u1.image END as other_image
     FROM connections c
     JOIN "user" u1 ON c.user_a = u1.id
     JOIN "user" u2 ON c.user_b = u2.id
     WHERE c.id = $2 AND (c.user_a = $1 OR c.user_b = $1)`,
    [session.user.id, id]
  );

  if (result.rows.length === 0) {
    return c.json({ error: "Connection not found" }, 404);
  }

  // Get shared videos for this connection
  const videos = await pool.query(
    `SELECT * FROM shared_videos
     WHERE connection_id = $1
     ORDER BY created_at DESC`,
    [id]
  );

  return c.json({
    ...result.rows[0],
    videos: videos.rows,
  });
});

// End connection
app.delete("/api/connections/:id", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const { id } = c.req.param();

  await pool.query(
    `UPDATE connections SET active = false, updated_at = NOW()
     WHERE id = $1 AND (user_a = $2 OR user_b = $2)`,
    [id, session.user.id]
  );

  return c.json({ success: true });
});

// ============ SHARED VIDEOS ROUTES ============

// Get shared videos
app.get("/api/videos", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const result = await pool.query(
    `SELECT v.*, u.name as uploader_name
     FROM shared_videos v
     JOIN "user" u ON v.uploader_id = u.id
     JOIN connections c ON v.connection_id = c.id
     WHERE (c.user_a = $1 OR c.user_b = $1)
     ORDER BY v.created_at DESC`,
    [session.user.id]
  );

  return c.json(result.rows);
});

// Get video by ID
app.get("/api/videos/:id", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const { id } = c.req.param();

  const result = await pool.query(
    `SELECT v.*, u.name as uploader_name
     FROM shared_videos v
     JOIN "user" u ON v.uploader_id = u.id
     JOIN connections c ON v.connection_id = c.id
     WHERE v.id = $1 AND (c.user_a = $2 OR c.user_b = $2)`,
    [id, session.user.id]
  );

  if (result.rows.length === 0) {
    return c.json({ error: "Video not found" }, 404);
  }

  return c.json(result.rows[0]);
});

// ============ LIVE SESSION ROUTES ============

// Start live session
app.post("/api/live/start", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const { connectionId } = await c.req.json();

  // Verify connection
  const conn = await pool.query(
    `SELECT * FROM connections
     WHERE id = $1 AND (user_a = $2 OR user_b = $2) AND active = true`,
    [connectionId, session.user.id]
  );

  if (conn.rows.length === 0) {
    return c.json({ error: "Connection not found" }, 404);
  }

  const sessionId = nanoid();

  await pool.query(
    `INSERT INTO live_sessions (id, connection_id, started_by)
     VALUES ($1, $2, $3)`,
    [sessionId, connectionId, session.user.id]
  );

  return c.json({ sessionId });
});

// End live session
app.post("/api/live/end", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const { sessionId } = await c.req.json();

  await pool.query(
    `UPDATE live_sessions SET active = false, ended_at = NOW()
     WHERE id = $1`,
    [sessionId]
  );

  return c.json({ success: true });
});

// Get active live sessions
app.get("/api/live/active", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const result = await pool.query(
    `SELECT ls.*, c.user_a, c.user_b,
      CASE WHEN c.user_a = $1 THEN u2.name ELSE u1.name END as other_name
     FROM live_sessions ls
     JOIN connections c ON ls.connection_id = c.id
     JOIN "user" u1 ON c.user_a = u1.id
     JOIN "user" u2 ON c.user_b = u2.id
     WHERE ls.active = true AND (c.user_a = $1 OR c.user_b = $1)`,
    [session.user.id]
  );

  return c.json(result.rows);
});

// ============ ADMIN ROUTES ============

// Get all users (admin only)
app.get("/api/admin/users", async (c) => {
  const session = await requireRole(c, ["admin"]);
  if (!session) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const result = await pool.query(
    `SELECT id, name, email, role, image, created_at, email_verified
     FROM "user" ORDER BY created_at DESC`
  );

  return c.json(result.rows);
});

// Update user role (admin only)
app.patch("/api/admin/users/:id/role", async (c) => {
  const session = await requireRole(c, ["admin"]);
  if (!session) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const { id } = c.req.param();
  const { role } = await c.req.json();

  if (!["user", "admin", "developer"].includes(role)) {
    return c.json({ error: "Invalid role" }, 400);
  }

  await pool.query(
    'UPDATE "user" SET role = $1, updated_at = NOW() WHERE id = $2',
    [role, id]
  );

  return c.json({ success: true });
});

// Delete user (admin only)
app.delete("/api/admin/users/:id", async (c) => {
  const session = await requireRole(c, ["admin"]);
  if (!session) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const { id } = c.req.param();

  // Don't allow deleting yourself
  if (id === session.user.id) {
    return c.json({ error: "Cannot delete yourself" }, 400);
  }

  await pool.query('DELETE FROM "user" WHERE id = $1', [id]);

  return c.json({ success: true });
});

// Get system stats (admin only)
app.get("/api/admin/stats", async (c) => {
  const session = await requireRole(c, ["admin"]);
  if (!session) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const [users, connections, videos, sessions] = await Promise.all([
    pool.query('SELECT COUNT(*) as count FROM "user"'),
    pool.query("SELECT COUNT(*) as count FROM connections WHERE active = true"),
    pool.query("SELECT COUNT(*) as count FROM shared_videos"),
    pool.query("SELECT COUNT(*) as count FROM live_sessions WHERE active = true"),
  ]);

  return c.json({
    totalUsers: parseInt(users.rows[0].count),
    activeConnections: parseInt(connections.rows[0].count),
    totalVideos: parseInt(videos.rows[0].count),
    activeSessions: parseInt(sessions.rows[0].count),
  });
});

// ============ DEVELOPER ROUTES ============

// Get test videos (developer only)
app.get("/api/dev/videos", async (c) => {
  const session = await requireRole(c, ["developer", "admin"]);
  if (!session) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const result = await pool.query(
    `SELECT v.*, u.name as uploader_name
     FROM shared_videos v
     JOIN "user" u ON v.uploader_id = u.id
     ORDER BY v.created_at DESC`
  );

  return c.json(result.rows);
});

// Get current user with role
app.get("/api/me", async (c) => {
  const session = await requireAuth(c);
  if (!session) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const result = await pool.query(
    'SELECT id, name, email, role, image, created_at FROM "user" WHERE id = $1',
    [session.user.id]
  );

  return c.json(result.rows[0]);
});

import { setupSignaling } from "./signaling.js";

const port = Number(process.env.PORT ?? 3030);

const server = serve({ fetch: app.fetch, port }, (info) => {
  console.log(`CLEAR auth server listening on http://localhost:${info.port}`);
});

// Set up WebRTC signaling
setupSignaling(server);
