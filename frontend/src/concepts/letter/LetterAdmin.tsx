/* 信笺概念 · 管理端壳:概念报头 + 共享工作台(三段式)。 */

import { useEffect } from "react";
import { useAuth } from "../../lib/auth";
import { useSystemStatus } from "../../hooks/useSystemStatus";
import { AdminConsole } from "../../shared/AdminConsole";
import { Masthead } from "./Header";

export function LetterAdmin() {
  const { user } = useAuth();
  const status = useSystemStatus(true);

  useEffect(() => {
    document.title = "咨询工作台 · 心屿";
  }, []);

  return (
    <>
      <Masthead
        title="心屿 · 值班室"
        subtitle="校园心理支持平台 · 教师工作区"
        healthText={status.healthText}
        healthOk={status.healthOk}
        modelText={status.modelText}
        actions={
          <span className="lz-user">
            <strong>{user?.username}</strong>
            <span>值班教师</span>
          </span>
        }
      />
      <AdminConsole />
    </>
  );
}
