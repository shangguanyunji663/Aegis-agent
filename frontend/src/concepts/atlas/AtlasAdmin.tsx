/* 群群岛屿 · 管理端壳:概念顶栏 + 共享工作台(三段式)。 */

import { useEffect } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { AdminConsole } from "../../shared/AdminConsole";
import { AtlasBar } from "./AtlasBar";

export function AtlasAdmin() {
  const { user } = useAuth();
  const status = useSystemStatus(true);

  useEffect(() => {
    document.title = "守望塔 · 心屿群岛";
  }, []);

  return (
    <>
      <AtlasBar
        healthOk={status.healthOk}
        healthText={status.healthText}
        modelText={status.modelText}
        actions={
          <span className="at-user">
            <strong>{user?.username}</strong>
            <span>守塔人 · KEEP</span>
          </span>
        }
      />
      <AdminConsole />
    </>
  );
}
