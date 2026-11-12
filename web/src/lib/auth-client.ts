import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  baseURL: import.meta.env.VITE_AUTH_URL ?? "",
});

export type Session = typeof authClient.$Infer.Session;
