(function () {
  /** 平台 iframe 注入 ?auth= 时尽早写入会话，避免 SPA 路由守卫先跳到 /login */
  function bootstrapAuthFromUrl() {
    var params = new URLSearchParams(location.search);
    var auth = params.get("auth");
    if (!auth) return false;
    var raw = auth.replace(/^Bearer\s+/i, "").trim();
    if (!raw) return false;
    try {
      localStorage.setItem("Authorization", raw);
    } catch (e) {
      return false;
    }
    params.delete("auth");
    var qs = params.toString();
    var next = location.pathname + (qs ? "?" + qs : "") + location.hash;
    history.replaceState(null, "", next);
    fetchUserInfoAfterAuth(raw);
    return true;
  }

  function fetchUserInfoAfterAuth(auth) {
    fetch("/v1/user/info", { headers: { Authorization: auth } })
      .then(function (r) {
        return r.json();
      })
      .then(function (body) {
        if (!body || body.code !== 0 || !body.data) return;
        var d = body.data;
        if (d.access_token) {
          try {
            localStorage.setItem("Token", d.access_token);
          } catch (e) {
            /* ignore */
          }
        }
        var info = {
          avatar: d.avatar,
          name: d.nickname,
          email: d.email,
          display_name: d.nickname,
        };
        try {
          localStorage.setItem("userInfo", JSON.stringify(info));
        } catch (e) {
          /* ignore */
        }
        if (d.nickname) {
          PLATFORM_DISPLAY_NAME = d.nickname;
          patchWelcomeNickname(d.nickname);
        }
      })
      .catch(function () {
        /* ignore */
      });
  }

  var APP_NAME = window.__ZT_PLATFORM_APP_NAME__ || "智碳平台AI系统";
  var PRIMARY = "#18a058";
  var PRIMARY_HOVER = "#36ad6a";
  var PRIMARY_PRESSED = "#0c7a43";
  var PRIMARY_LIGHT = "#e8f7ef";
  var HIDE_FILE_MANAGER = window.__ZT_PLATFORM_HIDE_FILE_MANAGER__ !== false;

  var FILE_PATH_PARTS = [
    "/management/files",
    "/file-management",
    "/file-manager",
    "/user-setting/management/file-management",
  ];

  var FILE_LABELS = ["文件管理", "fileManager", "File Manager", "File management"];

  var LOGO_URL = "/logo.svg";
  var FAVICON_URL = "/favicon.svg";

  document.title = APP_NAME + " · 知识问答";

  function setFavicon(href) {
    var url = href || FAVICON_URL;
    var link =
      document.querySelector("link[rel='icon']") ||
      document.querySelector("link[rel='shortcut icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.type = "image/svg+xml";
    link.href = url;
  }

  var BLUE_REPLACEMENTS = {
    "#1677ff": null,
    "#1890ff": null,
    "#3b82f6": null,
    "#2563eb": null,
    "#1d4ed8": null,
    "#60a5fa": null,
    "#40a9ff": null,
    "#93c5fd": null,
    "#bfdbfe": null,
    "#dbeafe": null,
    "#eff6ff": null,
    "#095fab": null,
    "#25abe8": null,
    "#55c8dd": null,
    "rgb(22, 119, 255)": null,
    "rgb(24, 144, 255)": null,
    "rgb(59, 130, 246)": null,
    "rgba(59, 130, 246, 0.1)": "rgba(24, 160, 88, 0.12)",
    "rgba(59,130,246,0.1)": "rgba(24, 160, 88, 0.12)",
  };

  function initBlueReplacementMap() {
    BLUE_REPLACEMENTS["#1677ff"] = PRIMARY;
    BLUE_REPLACEMENTS["#1890ff"] = PRIMARY;
    BLUE_REPLACEMENTS["#3b82f6"] = PRIMARY;
    BLUE_REPLACEMENTS["#2563eb"] = PRIMARY;
    BLUE_REPLACEMENTS["#1d4ed8"] = PRIMARY_PRESSED;
    BLUE_REPLACEMENTS["#60a5fa"] = PRIMARY_HOVER;
    BLUE_REPLACEMENTS["#40a9ff"] = PRIMARY_HOVER;
    BLUE_REPLACEMENTS["#93c5fd"] = PRIMARY_LIGHT;
    BLUE_REPLACEMENTS["#bfdbfe"] = PRIMARY_LIGHT;
    BLUE_REPLACEMENTS["#dbeafe"] = PRIMARY_LIGHT;
    BLUE_REPLACEMENTS["#eff6ff"] = PRIMARY_LIGHT;
    BLUE_REPLACEMENTS["#095fab"] = PRIMARY_PRESSED;
    BLUE_REPLACEMENTS["#25abe8"] = PRIMARY;
    BLUE_REPLACEMENTS["#55c8dd"] = PRIMARY_HOVER;
    BLUE_REPLACEMENTS["rgb(22, 119, 255)"] = PRIMARY;
    BLUE_REPLACEMENTS["rgb(24, 144, 255)"] = PRIMARY;
    BLUE_REPLACEMENTS["rgb(59, 130, 246)"] = PRIMARY;
  }

  function replaceBlueInString(str) {
    if (!str) return str;
    var out = str;
    Object.keys(BLUE_REPLACEMENTS).forEach(function (from) {
      var to = BLUE_REPLACEMENTS[from];
      if (!to) return;
      out = out.split(from).join(to);
      out = out.split(from.toUpperCase()).join(to);
    });
    return out;
  }

  var GREEN_ICON_FILTER =
    "brightness(0) saturate(100%) invert(52%) sepia(61%) saturate(638%) hue-rotate(103deg) brightness(92%) contrast(92%)";

  function isBlueRgb(color) {
    if (!color) return false;
    var m = String(color).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (!m) return false;
    var r = parseInt(m[1], 10);
    var g = parseInt(m[2], 10);
    var b = parseInt(m[3], 10);
    return b >= 120 && b > r + 30;
  }

  function fixTreeCheckboxes() {
    document.querySelectorAll(".ant-tree-checkbox-inner").forEach(function (inner) {
      var box = inner.closest(".ant-tree-checkbox");
      if (!box) return;
      if (box.classList.contains("ant-tree-checkbox-checked")) {
        inner.style.setProperty("background-color", PRIMARY, "important");
        inner.style.setProperty("border-color", PRIMARY, "important");
      }
    });
    document.querySelectorAll(".ant-tree .ant-checkbox-inner").forEach(function (inner) {
      var box = inner.closest(".ant-checkbox");
      if (box && box.classList.contains("ant-checkbox-checked")) {
        inner.style.setProperty("background-color", PRIMARY, "important");
        inner.style.setProperty("border-color", PRIMARY, "important");
      }
    });
  }

  function fixKnowledgeCardIcons() {
    document
      .querySelectorAll("[class*='leftIconDoc'], [class*='leftIconDate']")
      .forEach(function (el) {
        el.style.setProperty("filter", GREEN_ICON_FILTER, "important");
      });
  }

  function fixRibbonBadges() {
    document.querySelectorAll(".ant-ribbon").forEach(function (ribbon) {
      var bg = ribbon.style.background || ribbon.style.backgroundColor;
      if (isBlueRgb(bg) || (bg && replaceBlueInString(bg) !== bg)) {
        ribbon.style.setProperty("background", PRIMARY, "important");
        ribbon.style.setProperty("background-color", PRIMARY, "important");
        ribbon.style.setProperty("border-color", PRIMARY, "important");
      }
      var computed = window.getComputedStyle(ribbon).backgroundColor;
      if (isBlueRgb(computed)) {
        ribbon.style.setProperty("background-color", PRIMARY, "important");
      }
    });
    document.querySelectorAll(".ant-ribbon-corner").forEach(function (corner) {
      var c = window.getComputedStyle(corner).color;
      if (isBlueRgb(c)) {
        corner.style.setProperty("color", PRIMARY, "important");
        corner.style.setProperty("border-color", PRIMARY, "important");
      }
    });
  }

  function fixInlineBlueStyles() {
    initBlueReplacementMap();
    document.querySelectorAll("[style]").forEach(function (el) {
      var style = el.getAttribute("style");
      if (!style) return;
      var next = replaceBlueInString(style);
      if (next !== style) el.setAttribute("style", next);
    });
    document
      .querySelectorAll(
        ".ant-tree-checkbox-inner, .ant-checkbox-inner, [class*='leftIconDoc'], [class*='leftIconDate']"
      )
      .forEach(function (el) {
        var bg = el.style.backgroundColor || "";
        var border = el.style.borderColor || "";
        if (bg && BLUE_REPLACEMENTS[bg.toLowerCase()]) {
          el.style.setProperty("background-color", BLUE_REPLACEMENTS[bg.toLowerCase()], "important");
        }
        if (border && BLUE_REPLACEMENTS[border.toLowerCase()]) {
          el.style.setProperty("border-color", BLUE_REPLACEMENTS[border.toLowerCase()], "important");
        }
      });

    document.querySelectorAll(".ant-badge-color, .ant-ribbon").forEach(function (badge) {
      var c = badge.style.backgroundColor || badge.style.background || badge.getAttribute("color");
      if (c && BLUE_REPLACEMENTS[String(c).toLowerCase()]) {
        badge.style.setProperty("background-color", BLUE_REPLACEMENTS[String(c).toLowerCase()], "important");
        badge.style.setProperty("background", BLUE_REPLACEMENTS[String(c).toLowerCase()], "important");
      }
    });

    fixTreeCheckboxes();
    fixKnowledgeCardIcons();
    fixRibbonBadges();

    document.querySelectorAll("svg path[fill], svg path[stroke]").forEach(function (path) {
      var fill = path.getAttribute("fill");
      var stroke = path.getAttribute("stroke");
      var fillKey = fill ? fill.toLowerCase() : "";
      var strokeKey = stroke ? stroke.toLowerCase() : "";
      if (fillKey && BLUE_REPLACEMENTS[fillKey]) {
        path.setAttribute("fill", BLUE_REPLACEMENTS[fillKey]);
      }
      if (strokeKey && BLUE_REPLACEMENTS[strokeKey]) {
        path.setAttribute("stroke", BLUE_REPLACEMENTS[strokeKey]);
      }
    });
  }

  function applyGreenTheme() {
    initBlueReplacementMap();
    var root = document.documentElement;
    var map = {
      "--platform-primary": PRIMARY,
      "--platform-primary-hover": PRIMARY_HOVER,
      "--platform-primary-pressed": PRIMARY_PRESSED,
      "--platform-primary-light": PRIMARY_LIGHT,
      "--platform-primary-subtle": "rgba(24, 160, 88, 0.06)",
      "--platform-primary-soft": "rgba(24, 160, 88, 0.12)",
      "--platform-primary-border": "rgba(24, 160, 88, 0.28)",
      "--platform-primary-muted": PRIMARY_HOVER,
      "--ant-color-primary": PRIMARY,
      "--ant-color-primary-hover": PRIMARY_HOVER,
      "--ant-color-primary-active": PRIMARY_PRESSED,
      "--ant-color-link": PRIMARY_PRESSED,
      "--ant-color-link-hover": PRIMARY,
      "--ant-color-info": PRIMARY,
      "--ant-color-info-hover": PRIMARY_HOVER,
      "--ant-color-info-active": PRIMARY_PRESSED,
      "--el-color-primary": PRIMARY,
      "--el-color-primary-dark-2": PRIMARY_PRESSED,
      "--primary": "152 73% 36%",
      "--ring": "152 73% 36%",
      "--sidebar-primary": "152 73% 36%",
      "--sidebar-ring": "152 73% 36%",
      "--colors-background-sentiment-solid-primary": PRIMARY,
      "--colors-outline-sentiment-primary": "rgba(24, 160, 88, 0.35)",
      "--colors-text-core-standard": PRIMARY_PRESSED,
      "--colors-background-core-strong": PRIMARY,
      "--colors-background-core-standard": PRIMARY_HOVER,
      "--background-highlight": "rgba(24, 160, 88, 0.12)",
      "--button-blue-text": "rgb(24, 160, 88)",
      "--ant-menu-dark-item-active-bg": "rgba(24, 160, 88, 0.06)",
      "--ant-menu-item-selected-bg": "rgba(24, 160, 88, 0.06)",
    };
    Object.keys(map).forEach(function (key) {
      root.style.setProperty(key, map[key]);
    });
  }

  function applyPlatformLogo() {
    document.querySelectorAll("img").forEach(function (img) {
      var src = img.getAttribute("src") || "";
      var alt = (img.getAttribute("alt") || "").toLowerCase();
      if (
        src.indexOf("logo") >= 0 ||
        img.classList.contains("appIcon") ||
        alt === "knowflow" ||
        alt === "logo"
      ) {
        img.src = LOGO_URL;
      }
    });
    setFavicon(FAVICON_URL);
  }

  function normalizeText(s) {
    return (s || "").replace(/\s+/g, "").trim();
  }

  function labelMatches(text) {
    var n = normalizeText(text);
    if (!n) return false;
    for (var i = 0; i < FILE_LABELS.length; i++) {
      var lab = normalizeText(FILE_LABELS[i]);
      if (n === lab || n.indexOf(lab) >= 0) return true;
    }
    return false;
  }

  function isFileMgmtPath(path) {
    if (!path) return false;
    var p = path.split("?")[0].replace(/\/+$/, "") || "/";
    if (p === "/files" || p === "/file") return true;
    if (/^\/file(\/|$)/.test(p)) return true;
    return FILE_PATH_PARTS.some(function (part) {
      return p.indexOf(part) >= 0;
    });
  }

  function hideElement(el) {
    if (!el || el.dataset.ztHiddenFile === "1") return;
    el.dataset.ztHiddenFile = "1";
    el.style.setProperty("display", "none", "important");
    el.setAttribute("aria-hidden", "true");
  }

  function findMenuShell(el) {
    return (
      el.closest(
        ".ant-menu-item, .ant-menu-submenu, .ant-tabs-tab, " +
          ".el-menu-item, .el-sub-menu, .ragItem, " +
          "[class*='ragItem'], [role='tab'], [data-radix-collection-item]"
      ) || el
    );
  }

  function shouldHideNode(el) {
    if (!el || el.nodeType !== 1) return false;

    var href =
      el.getAttribute("href") ||
      (el.querySelector && el.querySelector("a") && el.querySelector("a").getAttribute("href")) ||
      "";
    if (href && isFileMgmtPath(href)) return true;

    var ragText = el.querySelector ? el.querySelector(".ragText") : null;
    if (ragText && labelMatches(ragText.textContent)) return true;

    var own = normalizeText(el.textContent);
    if (own.length > 40) return false;
    if (labelMatches(el.textContent)) return true;

    return false;
  }

  function hideFileManagerMenu() {
    if (!HIDE_FILE_MANAGER) return;

    var nodes = document.querySelectorAll(
      ".ant-menu-item, .ant-menu-submenu-title, .ant-tabs-tab, " +
        ".el-menu-item, .el-sub-menu__title, .ragItem, .ragText, " +
        "a, button, li, [role='tab'], [role='menuitem']"
    );

    nodes.forEach(function (el) {
      if (!shouldHideNode(el)) return;
      hideElement(findMenuShell(el));
    });

    // Radix / shadcn Segmented（next 布局顶栏）
    document.querySelectorAll("[class*='segmented'], [role='group']").forEach(function (group) {
      group.querySelectorAll("button, label, div").forEach(function (el) {
        if (!shouldHideNode(el)) return;
        hideElement(el.closest("button") || el.closest("label") || el);
      });
    });
  }

  function redirectFromFileManager() {
    if (!HIDE_FILE_MANAGER) return;
    if (!isFileMgmtPath(location.pathname)) return;
    var fallbacks = ["/datasets", "/knowledge", "/home", "/dashboard", "/"];
    for (var i = 0; i < fallbacks.length; i++) {
      if (fallbacks[i] === location.pathname) continue;
      location.replace(fallbacks[i]);
      return;
    }
  }

  var PLATFORM_DISPLAY_NAME = "";

  function applyPlatformUser(theme) {
    var t = theme || {};
    var name = (t.display_name || t.platform_display_name || "").trim();
    if (!name) return;
    PLATFORM_DISPLAY_NAME = name;
    patchWelcomeNickname(name);
    patchStoredUserInfo(name);
  }

  function patchWelcomeNickname(name) {
    var welcome = "欢迎回来, " + name;
    document.querySelectorAll("span, h1, h2, h3, p, div").forEach(function (el) {
      if (el.children && el.children.length > 0) return;
      var text = (el.textContent || "").trim();
      if (/^欢迎回来[,，]/.test(text)) {
        el.textContent = welcome;
      }
    });
  }

  function patchStoredUserInfo(name) {
    try {
      var raw = localStorage.getItem("userInfo");
      if (!raw) return;
      var info = JSON.parse(raw);
      if (!info || typeof info !== "object") return;
      info.nickname = name;
      if (!info.display_name) info.display_name = name;
      localStorage.setItem("userInfo", JSON.stringify(info));
    } catch (e) {
      /* ignore */
    }
  }

  function applyBranding(theme) {
    var t = theme || {};
    applyPlatformUser(t);
    if (t.app_name) {
      window.__ZT_PLATFORM_APP_NAME__ = t.app_name;
      document.title = t.app_name + " · 知识问答";
    }
    if (t.primary_color) PRIMARY = t.primary_color;
    if (t.primary_hover) PRIMARY_HOVER = t.primary_hover;
    if (t.primary_pressed) PRIMARY_PRESSED = t.primary_pressed;
    applyGreenTheme();
    fixInlineBlueStyles();
    if (t.logo_url) LOGO_URL = t.logo_url;
    if (t.favicon_url) FAVICON_URL = t.favicon_url;
    applyPlatformLogo();
    if (t.hide_file_manager === false) {
      HIDE_FILE_MANAGER = false;
      window.__ZT_PLATFORM_HIDE_FILE_MANAGER__ = false;
    } else if (t.hide_file_manager === true) {
      HIDE_FILE_MANAGER = true;
      window.__ZT_PLATFORM_HIDE_FILE_MANAGER__ = true;
    }
    hideFileManagerMenu();
    redirectFromFileManager();
  }

  function applyPlatformSso(sso) {
    if (!sso || !sso.authorization) return;
    var raw = String(sso.authorization).replace(/^Bearer\s+/i, "").trim();
    if (!raw) return;
    try {
      localStorage.setItem("Authorization", raw);
      if (sso.access_token) localStorage.setItem("Token", sso.access_token);
      if (sso.user_info) {
        var ui = sso.user_info;
        var info = {
          avatar: ui.avatar,
          name: ui.nickname || ui.name,
          email: ui.email,
          display_name: ui.nickname || ui.name,
        };
        localStorage.setItem("userInfo", JSON.stringify(info));
        if (info.display_name) {
          PLATFORM_DISPLAY_NAME = info.display_name;
          patchWelcomeNickname(info.display_name);
        }
      }
    } catch (e) {
      /* ignore */
    }
  }

  window.addEventListener("message", function (ev) {
    if (!ev.data) return;
    if (ev.data.type === "zt-platform-sso") {
      applyPlatformSso(ev.data.sso);
      return;
    }
    if (ev.data.type !== "zt-platform-theme") return;
    applyBranding(ev.data.theme);
    if (PLATFORM_DISPLAY_NAME) {
      patchWelcomeNickname(PLATFORM_DISPLAY_NAME);
    }
  });

  var urlParams = new URLSearchParams(location.search);
  if (urlParams.get("zt_hide_file") === "0") {
    HIDE_FILE_MANAGER = false;
  }

  var style = document.createElement("style");
  style.id = "zt-platform-branding-style";
  style.textContent =
    ".ant-pro-sider-logo h1, .ant-pro-global-header-logo h1 { font-size: 0 !important; }" +
    ".ant-pro-sider-logo h1::after, .ant-pro-global-header-logo h1::after { content: '" +
    APP_NAME +
    "'; font-size: 16px; }" +
    "a[href*='/management/files'],a[href*='/file-management'],a[href*='/file-manager']{display:none!important}" +
    ".ant-menu-item:has(a[href*='/management/files']),.ant-menu-item:has(a[href*='/file-management'])," +
    ".ant-tabs-tab:has([data-node-key='file-management']),.ant-tabs-tab:has([data-node-key='file-manager'])," +
    ".ragItem:has(.ragText){display:none!important}" +
    "[data-zt-hidden-file='1']{display:none!important}";
  document.head.appendChild(style);

  applyGreenTheme();
  fixInlineBlueStyles();
  applyPlatformLogo();
  hideFileManagerMenu();
  redirectFromFileManager();

  var brandingTick = 0;
  function runBrandingPass(full) {
    applyGreenTheme();
    if (full) fixInlineBlueStyles();
    hideFileManagerMenu();
    if (brandingTick % 4 === 0) applyPlatformLogo();
    if (PLATFORM_DISPLAY_NAME) patchWelcomeNickname(PLATFORM_DISPLAY_NAME);
    brandingTick += 1;
  }

  var timer = setInterval(function () {
    runBrandingPass(false);
  }, 2000);
  setTimeout(function () {
    clearInterval(timer);
  }, 60000);

  var observerPending = false;
  var observer = new MutationObserver(function () {
    if (observerPending) return;
    observerPending = true;
    requestAnimationFrame(function () {
      observerPending = false;
      runBrandingPass(false);
    });
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener("popstate", redirectFromFileManager);
  var _push = history.pushState;
  var _replace = history.replaceState;
  history.pushState = function () {
    _push.apply(history, arguments);
    setTimeout(function () {
      hideFileManagerMenu();
      redirectFromFileManager();
    }, 0);
  };
  history.replaceState = function () {
    _replace.apply(history, arguments);
    setTimeout(function () {
      hideFileManagerMenu();
      redirectFromFileManager();
    }, 0);
  };

  bootstrapAuthFromUrl();
})();
