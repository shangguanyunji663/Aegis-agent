/* 概念切换浮标:三个候选形态共存期间的对比控制器,选定后整体移除。
   固定右下角,用中性深色玻璃底,保证在三种概念、亮暗两档下都可读。 */

import { CONCEPT_META, useConcept } from "../lib/concept";
import type { Concept } from "../lib/concept";
import { useAuth } from "../lib/auth";

const ORDER: Concept[] = ["letter", "radio", "atlas"];

export function ConceptSwitcher() {
  const { concept, setConcept } = useConcept();
  const { mode, setMode } = useAuth();

  return (
    <div className="concept-switcher" role="toolbar" aria-label="设计形态切换">
      <span className="cs-label">形态</span>
      {ORDER.map((key) => (
        <button
          key={key}
          type="button"
          className={key === concept ? "on" : ""}
          aria-pressed={key === concept}
          onClick={() => setConcept(key)}
        >
          <i aria-hidden="true">{CONCEPT_META[key].glyph}</i>
          {CONCEPT_META[key].name}
        </button>
      ))}
      {concept !== "radio" && (
        <>
          <i className="cs-sep" aria-hidden="true" />
          <button type="button" onClick={() => setMode(mode === "dark" ? "light" : "dark")}>
            {mode === "dark" ? "暗" : "亮"}
          </button>
        </>
      )}
    </div>
  );
}
