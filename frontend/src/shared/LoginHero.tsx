/* 登录 Hero:「输入框即入口」(Manus/Kimi 范式)。
   大输入框 + 任务 chips;点任意处触发 onActivate(所点话题),
   由概念登录页展开认证卡。 */

import type { ReactNode } from "react";

export interface HeroChip {
  label: string;
  text: string;
}

export function LoginHero({
  slogan,
  placeholder,
  chips,
  actionLabel,
  onActivate,
}: {
  slogan: ReactNode;
  placeholder: string;
  chips: HeroChip[];
  actionLabel: string;
  onActivate: (topic: string | null) => void;
}) {
  return (
    <div className="lgh">
      <h1 className="lgh-slogan">{slogan}</h1>
      <button
        type="button"
        className="lgh-inputbar"
        data-tilt="1.2"
        onClick={() => onActivate(null)}
      >
        <span className="lgh-caret" aria-hidden="true" />
        <span>{placeholder}</span>
        <span className="lgh-go">
          <span className="lgh-go-t">{actionLabel}</span>
          <i className="lgh-go-ic" aria-hidden="true">→</i>
        </span>
      </button>
      <div className="lgh-chips">
        {chips.map((chip) => (
          <button key={chip.label} type="button" className="lgh-chip" onClick={() => onActivate(chip.text)}>
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  );
}
