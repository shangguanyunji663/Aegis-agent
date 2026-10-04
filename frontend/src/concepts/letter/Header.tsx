/* 信笺概念 · 公共报头:信桌与值班室共用。 */

import { useAuth } from "../../lib/auth";
import { dateLine, greeting } from "../../lib/labels";
import type { ReactNode } from "react";

export function Masthead({
  title,
  subtitle,
  healthText,
  healthOk,
  modelText,
  actions,
}: {
  title: string;
  subtitle: string;
  healthText: string;
  healthOk: boolean | null;
  modelText?: string;
  actions?: ReactNode;
}) {
  const { user, logout } = useAuth();

  return (
    <header className="lz-masthead">
      <div className="lz-brand">
        <span className="seal-mark" aria-hidden="true">屿</span>
        <div>
          <h1>{title}</h1>
          <small>{subtitle}</small>
        </div>
      </div>
      <div className="lz-side">
        <span className="lz-user">
          <strong>{greeting()},{user?.username ?? ""}</strong>
          <span>{dateLine()}</span>
        </span>
        <span className={`lz-stamp ${healthOk === false ? "bad" : healthOk ? "ok" : "quiet"}`}>
          {healthOk === false ? "✕" : "●"} {healthText}
        </span>
        {modelText ? <span className="lz-stamp quiet">{modelText}</span> : null}
        {actions}
        {user ? (
          <button type="button" className="lz-link" onClick={() => void logout()}>
            退出
          </button>
        ) : null}
      </div>
    </header>
  );
}
