/* 夜航电台 · 管理端壳:概念顶栏 + 共享工作台(三段式)。 */

import { useEffect } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { AdminConsole } from "../../shared/AdminConsole";
import { RadioBar } from "./RadioBar";

export function RadioAdmin() {
  const { user } = useAuth();
  const status = useSystemStatus(true);

  useEffect(() => {
    document.title = "导播间 · 心屿夜航";
  }, []);

  return (
    <>
      <RadioBar
        onAir={false}
        healthOk={status.healthOk}
        healthText={status.healthText}
        modelText={status.modelText}
        actions={
          <span className="rg-user">
            <strong>{user?.username}</strong>
            <span>DIRECTOR · 导播</span>
          </span>
        }
      />
      <AdminConsole />
    </>
  );
}
