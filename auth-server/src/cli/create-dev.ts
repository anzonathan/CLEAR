import { pool } from "../auth.js";
import bcrypt from "bcrypt";
import { nanoid } from "nanoid";
import "dotenv/config";

async function createDev() {
  const args = process.argv.slice(2);

  if (args.length < 3) {
    console.log("Usage: pnpm create-dev <name> <email> <password>");
    console.log("Example: pnpm create-dev \"Jane Developer\" dev@clear.app secretpassword");
    process.exit(1);
  }

  const [name, email, password] = args;

  try {
    // Check if user already exists
    const existing = await pool.query(
      'SELECT id FROM "user" WHERE email = $1',
      [email]
    );

    if (existing.rows.length > 0) {
      console.error(`Error: User with email ${email} already exists.`);
      process.exit(1);
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);
    const userId = nanoid();
    const accountId = nanoid();

    // Create user with developer role
    await pool.query(
      `INSERT INTO "user" (id, name, email, role, email_verified)
       VALUES ($1, $2, $3, 'developer', true)`,
      [userId, name, email]
    );

    // Create account with password
    await pool.query(
      `INSERT INTO account (id, user_id, account_id, provider_id, password)
       VALUES ($1, $2, $3, 'credential', $4)`,
      [accountId, userId, email, hashedPassword]
    );

    console.log(`Developer account created successfully.`);
    console.log(`  Name: ${name}`);
    console.log(`  Email: ${email}`);
    console.log(`  Role: developer`);
  } catch (error) {
    console.error("Failed to create developer account:", error);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

createDev();
