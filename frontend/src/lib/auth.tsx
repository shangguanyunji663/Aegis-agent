/* 鉴权上下文。亮暗双模式已按需求移除,首屏主题由 pages.py 注入 data-theme="light"。 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { User } from "./types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<User | null>;
  login: (username: string, password: string) => Promise<User>;
  register: (payload: { username: string; password: string; role: string; invite_code: string }) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.me();
      setUser(data.user);
      return data.user;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    await api.login(username, password);
    const me = await api.me();
    setUser(me.user);
    return me.user;
  }, []);

  const register = useCallback(
    async (payload: { username: string; password: string; role: string; invite_code: string }) => {
      await api.register(payload);
      const me = await api.me();
      setUser(me.user);
      return me.user;
    },
    [],
  );

  const logout = useCallback(async () => {
    await api.logout();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return value;
}
