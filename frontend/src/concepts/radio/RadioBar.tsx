/* 夜航电台 · 公共顶栏:ON AIR 灯 + LED 状态。 */

import { useAuth } from "../../lib/auth";
import { clockLine, greeting } from "../../lib/labels";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

export function RadioBar({
  onAir,
  healthOk,
  healthText,
  modelText,
  actions,
}: {
  onAir: boolean;
  healthOk: boolean | null;
  healthText: string;
  modelText?: string;
  actions?: ReactNode;
}) {
  const { user, logout } = useAuth();
  const [clock, setClock] = useState(clockLine());

  useEffect(() => {
    const timer = setInterval(() => setClock(clockLine()), 20000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="rg-bar">
      <div className="rg-brand">
        <div>
          <span className="callword">心屿夜航</span>
          <small>LATE-NIGHT SUPPORT RADIO</small>
        </div>
      </div>
      <span className={`rg-onair ${onAir ? "live" : ""}`}>{onAir ? "ON AIR" : "STAND BY"}</span>
      <span className="num" style={{ font: "500 12px var(--mono)", color: "var(--muted)", letterSpacing: ".2em" }}>
        {clock}
      </span>
      <div className="spacer" />
      <span className={`rg-led ${healthOk === false ? "bad" : healthOk ? "ok" : ""}`}>{healthText}</span>
      {modelText ? <span className="rg-led amber">{modelText}</span> : null}
      {actions}
      {user ? (
        <span className="rg-user">
          <strong>{greeting()},{user.username}</strong>
          <span>{user.role === "student" ? "CALLER" : "DIRECTOR"}</span>
        </span>
      ) : null}
      {user ? (
        <button type="button" className="rg-ghost" onClick={() => void logout()}>
          退出
        </button>
      ) : null}
    </header>
  );
}
