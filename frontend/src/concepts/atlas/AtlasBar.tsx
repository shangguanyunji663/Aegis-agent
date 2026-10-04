/* 群群岛屿 · 公共顶栏。 */

import { useAuth } from "../../lib/auth";
import { greeting } from "../../lib/labels";
import type { ReactNode } from "react";

export function AtlasBar({
  healthOk,
  healthText,
  modelText,
  actions,
}: {
  healthOk: boolean | null;
  healthText: string;
  modelText?: string;
  actions?: ReactNode;
}) {
  const { user, logout } = useAuth();

  return (
    <header className="at-bar">
      <div className="at-brand">
        <span className="at-rose" aria-hidden="true">
          <i />
        </span>
        <div>
          <h1>心屿群岛</h1>
          <small>CAMPUS SUPPORT ATLAS</small>
        </div>
      </div>
      <div className="at-side">
        <span className="at-user">
          <strong>{greeting()},{user?.username ?? ""}</strong>
          <span>{user?.role === "student" ? "船员" : "守塔人"}</span>
        </span>
        <span className={`at-sig ${healthOk === false ? "bad" : healthOk ? "ok" : ""}`}>
          <span className={`flag ${healthOk === false ? "high" : healthOk ? "low" : "medium"}`} aria-hidden="true" />
          {healthText}
        </span>
        {modelText ? <span className="at-sig">{modelText}</span> : null}
        {actions}
        {user ? (
          <button type="button" className="at-link" onClick={() => void logout()}>
            退出
          </button>
        ) : null}
      </div>
    </header>
  );
}
