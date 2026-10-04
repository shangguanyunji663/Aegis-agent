/* 概念切换上下文:三个候选设计形态(letter / radio / atlas)共存一炉,
   供用户在同一份功能上对比形态本身。选定后删除落选概念即可,互不渗透。 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

export type Concept = "letter" | "radio" | "atlas";

export const CONCEPT_META: Record<Concept, { name: string; glyph: string; blurb: string }> = {
  letter: { name: "信笺往来", glyph: "封信", blurb: "倾诉是一封信,回信逐字送达" },
  radio: { name: "夜航电台", glyph: "波段", blurb: "深夜热线,拨通就有回应" },
  atlas: { name: "群岛图鉴", glyph: "航迹", blurb: "每次会话是一座小岛" },
};

const STORAGE_KEY = "aegis:concept";

interface ConceptValue {
  concept: Concept;
  setConcept: (c: Concept) => void;
}

const ConceptContext = createContext<ConceptValue | null>(null);

function initialConcept(): Concept {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved === "radio" || saved === "atlas" || saved === "letter" ? saved : "letter";
}

export function ConceptProvider({ children }: { children: ReactNode }) {
  const [concept, setConceptState] = useState<Concept>(initialConcept);
  const [reveal, setReveal] = useState(0);

  useEffect(() => {
    document.documentElement.dataset.concept = concept;
  }, [concept]);

  const setConcept = useCallback((next: Concept) => {
    localStorage.setItem(STORAGE_KEY, next);
    setConceptState(next);
    setReveal((n) => n + 1);
  }, []);

  return (
    <ConceptContext.Provider value={{ concept, setConcept }}>
      {children}
      {reveal > 0 && <div key={reveal} className="fx-reveal" aria-hidden="true" />}
    </ConceptContext.Provider>
  );
}

export function useConcept(): ConceptValue {
  const value = useContext(ConceptContext);
  if (!value) throw new Error("useConcept 必须在 ConceptProvider 内使用");
  return value;
}
