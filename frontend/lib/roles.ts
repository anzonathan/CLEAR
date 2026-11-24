import type { User } from './api';

/** Where each role lands after sign-in. Admins live in /admin only; developers start in
 *  their tools but can also use the player app; players use /app. */
export function homeFor(role: User['role'] | undefined | null): string {
  if (role === 'admin') return '/admin';
  if (role === 'developer') return '/dev';
  return '/app';
}
