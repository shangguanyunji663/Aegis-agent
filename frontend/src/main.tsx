import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

/* 自托管字体:摆脱系统字体的「默认感」。CJK 按 unicode-range 子集化按需加载。 */
import "@fontsource/noto-sans-sc/400.css";
import "@fontsource/noto-sans-sc/500.css";
import "@fontsource/noto-sans-sc/700.css";
import "@fontsource/noto-serif-sc/500.css";
import "@fontsource/noto-serif-sc/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "lxgw-wenkai-webfont/lxgwwenkai-regular.css";
import "lxgw-wenkai-webfont/lxgwwenkai-bold.css";
import "lxgw-wenkai-screen-webfont/lxgwwenkaiscreen.css";
import "@fontsource/ma-shan-zheng/chinese-simplified-400.css";

import "./styles/base.css";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";
import { ConceptProvider } from "./lib/concept";
/* fx 动效层声明在 App 之后:保证其规则在概念层 CSS 之后注入,级联胜出 */
import "./shared/fx.css";
/* 精美层最后注入:氛围光/渐变走线/水印字/排版精修 */
import "./shared/premium.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ConceptProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ConceptProvider>
    </BrowserRouter>
  </StrictMode>,
);
