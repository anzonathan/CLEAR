import { pool } from "./auth.js";
import "dotenv/config";

const migrations = `
-- better-auth core tables
CREATE TABLE IF NOT EXISTS "user" (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  email_verified BOOLEAN DEFAULT FALSE,
  image TEXT,
  role TEXT DEFAULT 'user',
  gender TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add gender column if it doesn't exist (for existing databases)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user' AND column_name = 'gender') THEN
    ALTER TABLE "user" ADD COLUMN gender TEXT;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS session (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  token TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS account (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  account_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  access_token TEXT,
  refresh_token TEXT,
  access_token_expires_at TIMESTAMPTZ,
  refresh_token_expires_at TIMESTAMPTZ,
  scope TEXT,
  id_token TEXT,
  password TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS verification (
  id TEXT PRIMARY KEY,
  identifier TEXT NOT NULL,
  value TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- CLEAR app tables
CREATE TABLE IF NOT EXISTS pair_codes (
  id TEXT PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  creator_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  used BOOLEAN DEFAULT FALSE,
  used_by TEXT REFERENCES "user"(id) ON DELETE SET NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS connections (
  id TEXT PRIMARY KEY,
  user_a TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  user_b TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  pair_code_id TEXT REFERENCES pair_codes(id) ON DELETE SET NULL,
  active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_a, user_b)
);

CREATE TABLE IF NOT EXISTS shared_videos (
  id TEXT PRIMARY KEY,
  uploader_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  connection_id TEXT REFERENCES connections(id) ON DELETE SET NULL,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_size BIGINT,
  mime_type TEXT,
  type TEXT DEFAULT 'recorded',
  thumbnail_path TEXT,
  duration_seconds INTEGER,
  processed BOOLEAN DEFAULT FALSE,
  detection_results JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS live_sessions (
  id TEXT PRIMARY KEY,
  connection_id TEXT NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
  started_by TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_session_user_id ON session(user_id);
CREATE INDEX IF NOT EXISTS idx_session_token ON session(token);
CREATE INDEX IF NOT EXISTS idx_account_user_id ON account(user_id);
CREATE INDEX IF NOT EXISTS idx_pair_codes_code ON pair_codes(code);
CREATE INDEX IF NOT EXISTS idx_pair_codes_creator ON pair_codes(creator_id);
CREATE INDEX IF NOT EXISTS idx_connections_user_a ON connections(user_a);
CREATE INDEX IF NOT EXISTS idx_connections_user_b ON connections(user_b);
CREATE INDEX IF NOT EXISTS idx_shared_videos_uploader ON shared_videos(uploader_id);
CREATE INDEX IF NOT EXISTS idx_shared_videos_connection ON shared_videos(connection_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_connection ON live_sessions(connection_id);
`;

async function migrate() {
  console.log("Running migrations...");
  try {
    await pool.query(migrations);
    console.log("Migrations completed successfully.");
  } catch (error) {
    console.error("Migration failed:", error);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

migrate();
