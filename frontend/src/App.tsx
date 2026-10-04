/* 路由与角色守卫:/ 登录, /student 学生信桌, /admin 教师值班区。
   三个概念各自实现三页,由 data-concept 决定渲染哪一套外壳。 */

import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { useConcept } from "./lib/concept";
import { initFx } from "./shared/fx";
import { ConceptSwitcher } from "./shared/ConceptSwitcher";
import { AtlasAdmin, AtlasLogin, AtlasStudent } from "./concepts/atlas";
import { LetterAdmin, LetterLogin, LetterStudent } from "./concepts/letter";
import { RadioAdmin, RadioLogin, RadioStudent } from "./concepts/radio";
import type { Role } from "./lib/types";
import type { ReactNode } from "react";

type Pages = { Login: () => ReactNode; Student: () => ReactNode; Admin: () => ReactNode };

const CONCEPT_PAGES: Record<string, Pages> = {
  letter: { Login: LetterLogin, Student: LetterStudent, Admin: LetterAdmin },
  radio: { Login: RadioLogin, Student: RadioStudent, Admin: RadioAdmin },
  atlas: { Login: AtlasLogin, Student: AtlasStudent, Admin: AtlasAdmin },
};

function homeFor(role: Role): string {
  return role === "admin" || role === "teacher" ? "/admin" : "/student";
}

export function App() {
  const { user, loading } = useAuth();
  const { concept } = useConcept();
  const pages = CONCEPT_PAGES[concept];

  useEffect(() => initFx(), []);

  if (loading) return null;

  return (
    <>
      <Routes>
        <Route
          path="/"
          element={user ? <Navigate to={homeFor(user.role)} replace /> : <pages.Login />}
        />
        <Route
          path="/student"
          element={
            !user ? (
              <Navigate to="/" replace />
            ) : user.role === "student" ? (
              <pages.Student />
            ) : (
              <Navigate to="/admin" replace />
            )
          }
        />
        <Route
          path="/admin"
          element={
            !user ? (
              <Navigate to="/" replace />
            ) : user.role === "student" ? (
              <Navigate to="/student" replace />
            ) : (
              <pages.Admin />
            )
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ConceptSwitcher />
      <div className="fx-grain" aria-hidden="true" />
    </>
  );
}
