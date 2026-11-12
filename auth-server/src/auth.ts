import { betterAuth } from "better-auth";
import { Pool } from "pg";
import "dotenv/config";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://clear:clear_dev_password@localhost:5432/clear",
});

export const trustedOrigins = (
  process.env.TRUSTED_ORIGINS ?? "http://localhost:8443"
)
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

export const auth = betterAuth({
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL,
  database: pool,
  trustedOrigins,
  emailAndPassword: {
    enabled: true,
  },
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    },
  },
  user: {
    additionalFields: {
      role: {
        type: "string",
        required: false,
        defaultValue: "user",
        input: false,
      },
      gender: {
        type: "string",
        required: false,
        input: true,
      },
    },
  },
});

export { pool };
