/* 概念(主题)切换器:三套设计形态共存的产品级切换入口。 */

import { CONCEPT_META, useConcept } from "../lib/concept";
import type { Concept } from "../lib/concept";

const ORDER: Concept[] = ["letter", "radio", "atlas"];

export function ConceptSwitcher() {
  const { concept, setConcept } = useConcept();

  return (
    <div className="concept-switcher" role="toolbar" aria-label="主题切换">
      <span className="cs-label">主题</span>
      {ORDER.map((key) => (
        <button
          key={key}
          type="button"
          className={key === concept ? "on" : ""}
          aria-pressed={key === concept}
          title={CONCEPT_META[key].blurb}
          onClick={() => setConcept(key)}
        >
          <i aria-hidden="true">{CONCEPT_META[key].glyph}</i>
          {CONCEPT_META[key].name}
        </button>
      ))}
    </div>
  );
}
