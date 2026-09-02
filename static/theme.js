/* 主题切换器:读取服务端注入的 html[data-theme],即时切换并 PUT 回后端按用户持久化。
   仅挂载到 #theme-switcher(学生端/管理端顶栏);登录页无用户不挂载。 */
(function () {
  "use strict";

  var THEMES = [
    { key: "warm", name: "暖意疗愈", desc: "温暖踏实", swatch: "#6f9d8b" },
    { key: "ocean", name: "深海冥想", desc: "深邃安宁", swatch: "#2a7a8f" },
    { key: "forest", name: "晨雾森林", desc: "清新通透", swatch: "#4a7c59" },
    { key: "playful", name: "童趣治愈", desc: "童趣温暖", swatch: "#8b7ab8" },
  ];
  var DEFAULT_THEME = "warm";

  function currentTheme() {
    var t = document.documentElement.getAttribute("data-theme");
    return THEMES.some(function (x) { return x.key === t; }) ? t : DEFAULT_THEME;
  }

  function findMeta(key) {
    for (var i = 0; i < THEMES.length; i++) if (THEMES[i].key === key) return THEMES[i];
    return THEMES[0];
  }

  function applyTheme(key) {
    document.documentElement.setAttribute("data-theme", key);
  }

  function saveTheme(key) {
    return fetch("/api/auth/me/theme", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: key }),
    }).then(function (res) {
      if (res.status === 401) window.location.replace("/");
      if (!res.ok) throw new Error("theme save failed");
      return res.json();
    });
  }

  function renderButton(root, key) {
    var meta = findMeta(key);
    root.innerHTML =
      '<button type="button" class="theme-btn" aria-haspopup="listbox" aria-expanded="false">'
      + '<span class="theme-swatch" style="background:' + meta.swatch + '"></span>'
      + '<span class="theme-label">' + meta.name + '</span>'
      + '<span class="chev" aria-hidden="true">▾</span>'
      + '</button>'
      + '<div class="theme-menu" role="listbox"></div>';
  }

  function renderMenu(menu, key) {
    menu.innerHTML = THEMES.map(function (t) {
      return '<button type="button" class="theme-opt' + (t.key === key ? " active" : "") + '" role="option" data-theme="' + t.key + '" aria-selected="' + (t.key === key) + '">'
        + '<span class="dot" style="background:' + t.swatch + '"></span>'
        + '<span class="name">' + t.name + '<small class="desc">' + t.desc + '</small></span>'
        + '</button>';
    }).join("");
  }

  function syncActive(key) {
    var opts = document.querySelectorAll(".theme-opt");
    for (var i = 0; i < opts.length; i++) {
      var k = opts[i].getAttribute("data-theme");
      var on = k === key;
      opts[i].classList.toggle("active", on);
      opts[i].setAttribute("aria-selected", on);
    }
    var meta = findMeta(key);
    var sw = document.querySelector(".theme-btn .theme-swatch");
    var lb = document.querySelector(".theme-btn .theme-label");
    if (sw) sw.style.background = meta.swatch;
    if (lb) lb.textContent = meta.name;
  }

  function init() {
    var root = document.getElementById("theme-switcher");
    if (!root) return;
    var key = currentTheme();
    renderButton(root, key);
    var menu = root.querySelector(".theme-menu");
    var btn = root.querySelector(".theme-btn");
    renderMenu(menu, key);

    function close() {
      menu.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
    }
    function toggle() {
      var open = menu.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggle();
    });
    menu.addEventListener("click", function (e) {
      var opt = e.target.closest(".theme-opt");
      if (!opt) return;
      var next = opt.getAttribute("data-theme");
      if (next === key) { close(); return; }
      key = next;
      applyTheme(key);
      syncActive(key);
      saveTheme(key).catch(function () { /* 静默:主题已应用,保存失败不阻断交互 */ });
      close();
    });
    document.addEventListener("click", function (e) {
      if (!root.contains(e.target)) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
