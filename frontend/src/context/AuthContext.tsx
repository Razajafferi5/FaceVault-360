import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { api } from '../services/api';

export interface AuthUser {
  id?: number;
  username: string;
  full_name?: string;
  email?: string;
  role: string;
  is_owner: boolean;
  person_id?: number | null;
  person_details?: any;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isOwner: boolean;
  loading: boolean;
  login: (credentials: { username: string; password: string }) => Promise<void>;
  signup: (data: { username: string; password: string; full_name?: string; email?: string }) => Promise<{ role: string; is_owner: boolean }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'));
  const [loading, setLoading] = useState<boolean>(true);

  const refreshUser = useCallback(async () => {
    const currentToken = localStorage.getItem('token');
    if (!currentToken) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const me = await api.getMe();
      if (me) {
        setUser({
          id: me.id,
          username: me.username,
          full_name: me.name || me.full_name,
          email: me.email,
          role: me.role,
          is_owner: me.is_owner === true || me.role?.toLowerCase() === 'owner',
          person_id: me.person_id,
          person_details: me.person_details
        });
      } else {
        setUser(null);
        localStorage.clear();
        setToken(null);
      }
    } catch (err) {
      console.warn('Authentication check failed:', err);
      setUser(null);
      localStorage.clear();
      setToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (credentials: { username: string; password: string }) => {
    const resp = await api.loginJson(credentials);
    if (resp.access_token) {
      localStorage.setItem('token', resp.access_token);
      localStorage.setItem('user_role', resp.role);
      setToken(resp.access_token);
      setUser({
        username: resp.username,
        full_name: resp.full_name,
        role: resp.role,
        is_owner: resp.role.toLowerCase() === 'owner',
      });
      await refreshUser();
    } else {
      throw new Error('No access token received from server');
    }
  };

  const signup = async (data: { username: string; password: string; full_name?: string; email?: string }) => {
    const resp = await api.signup(data);
    if (resp.access_token) {
      localStorage.setItem('token', resp.access_token);
      localStorage.setItem('user_role', resp.role);
      setToken(resp.access_token);
      const isOwner = resp.role.toLowerCase() === 'owner';
      setUser({
        username: resp.username,
        full_name: resp.full_name,
        role: resp.role,
        is_owner: isOwner,
      });
      await refreshUser();
      return { role: resp.role, is_owner: isOwner };
    }
    throw new Error('Registration failed');
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // ignore
    }
    localStorage.clear();
    sessionStorage.clear();
    setToken(null);
    setUser(null);
  };

  const isOwner = Boolean(user?.is_owner || user?.role?.toLowerCase() === 'owner');
  const isAuthenticated = Boolean(token && user);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated,
        isOwner,
        loading,
        login,
        signup,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const ProtectedRoute: React.FC<{ children: React.ReactNode; requireOwner?: boolean }> = ({
  children,
  requireOwner = false,
}) => {
  const { isAuthenticated, isOwner, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#070b14] flex flex-col items-center justify-center text-slate-300">
        <div className="relative w-16 h-16 mb-4">
          <div className="absolute inset-0 rounded-full border-2 border-cyan-500/20 animate-ping" />
          <div className="w-16 h-16 rounded-full border-2 border-transparent border-t-cyan-400 border-r-blue-500 animate-spin" />
        </div>
        <p className="text-xs font-mono uppercase tracking-widest text-cyan-400/80 animate-pulse">
          Verifying Biometric Credentials...
        </p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requireOwner && !isOwner) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mb-4 shadow-lg shadow-rose-500/10">
          <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Owner Authorization Required</h2>
        <p className="text-sm text-slate-400 max-w-md mb-6">
          This secure operation is restricted exclusively to system Owners. Your current account does not have permission to access or perform actions in this section.
        </p>
      </div>
    );
  }

  return <>{children}</>;
};
