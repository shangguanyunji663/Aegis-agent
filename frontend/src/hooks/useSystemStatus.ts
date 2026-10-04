/* 服务健康与模型状态:登录页只看健康;登录后追加模型/编排摘要。60s 轮询。 */

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { PROVIDER_LABEL } from "../lib/labels";

export interface SystemStatus {
  healthOk: boolean | null;
  healthText: string;
  modelText: string;
}

export function useSystemStatus(authed: boolean): SystemStatus {
  const [state, setState] = useState<SystemStatus>({
    healthOk: null,
    healthText: "检测中",
    modelText: authed ? "模型检测中" : "",
  });

  const refresh = useCallback(async () => {
    try {
      const health = (await api.health()) as { status?: string };
      const up = health.status === "UP";
      setState((prev) => ({ ...prev, healthOk: up, healthText: up ? "邮路畅通" : health.status || "检测中" }));
      if (!authed) return;
      const status = await api.admin.agentStatus();
      const provider = PROVIDER_LABEL[status.models.base_provider] ?? status.models.base_provider;
      setState((prev) => ({
        ...prev,
        modelText:
          status.models.base_provider === "mock" ? "演示模式" : `${provider} · ${status.models.base_model}`,
      }));
    } catch {
      setState((prev) => ({ ...prev, healthOk: false, healthText: "邮路中断" }));
    }
  }, [authed]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 60000);
    return () => clearInterval(timer);
  }, [refresh]);

  return state;
}
