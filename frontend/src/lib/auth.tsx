/* 鉴权与亮暗模式上下文。
   模式(html[data-theme]=light|dark)首屏由 pages.py 服务端注入避免闪烁,
   登录后切档会 PUT /api/auth/me/theme 按用户持久化;未登录只记 localStorage。 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { User } from "./types";

export type Mode = "light" | "dark";
const MODE_KEY = "aegis:mode";

interface AuthValue {
  user: User | null;
  loading: boolean;
  mode: Mode;
  setMode: (m: Mode) => void;
  refresh: () => Promise<User | null>;
  login: (username: string, password: string) => Promise<User>;
  register: (payload: { username: string; password: string; role: string; invite_code: string }) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

function initialMode(): Mode {
  const attr = document.documentElement.dataset.theme;
  if (attr === "dark" || attr === "light") return attr;
  return localStorage.getItem(MODE_KEY) === "dark" ? "dark" : "light";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setModeState] = useState<Mode>(initialMode);

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    localStorage.setItem(MODE_KEY, mode);
  }, [mode]);

  const setMode = useCallback(
    (next: Mode) => {
      setModeState(next);
      if (user) api.saveTheme(next).catch(() => { /* 已应用,持久化失败不阻断 */ });
    },
    [user],
  );

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
    <AuthContext.Provider value={{ user, loading, mode, setMode, refresh, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return value;
}
