'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { getMe, getCsrfToken, User } from './api';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  /** Reloads the session user and returns it (null when signed out). */
  refetch: () => Promise<User | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUser = async (): Promise<User | null> => {
    try {
      setLoading(true);
      setError(null);
      const data = await getMe();
      setUser(data);
      return data;
    } catch (err) {
      setUser(null);
      // Don't set error for 401 - user just isn't logged in
      if (err instanceof Error && !err.message.includes('401')) {
        setError(err.message);
      }
      return null;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    try {
      await fetch('/api/auth/logout/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRFToken': getCsrfToken() },
      });
    } catch (err) {
      // Ignore logout errors
    }
    setUser(null);
  };

  useEffect(() => {
    fetchUser();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, refetch: fetchUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
