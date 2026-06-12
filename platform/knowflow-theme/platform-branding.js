(function () {
  /** 平台 iframe 注入 ?auth= 时尽早写入会话，避免 SPA 路由守卫先跳到 /login */
  bootstrapAuthFromUrl();

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

  var APP_NAME = window.__ZT_PLATFORM_APP_NAME__ || "AI办公系统";
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

  function hideKbElement(el) {
    if (!el || el.dataset.ztHiddenKb === "1") return;
    el.dataset.ztHiddenKb = "1";
    el.style.setProperty("display", "none", "important");
    el.setAttribute("aria-hidden", "true");
  }

  function showKbElement(el) {
    if (!el || el.dataset.ztHiddenKb !== "1") return;
    delete el.dataset.ztHiddenKb;
    el.style.removeProperty("display");
    el.removeAttribute("aria-hidden");
  }

  function revealAllHiddenKnowledgeBases() {
    document.querySelectorAll("[data-zt-hidden-kb='1']").forEach(showKbElement);
  }

  var ALLOWED_KB_TITLES = new Set();
  var ALLOWED_DATASET_IDS = new Set();
  var KB_VISIBILITY_FILTER_ENABLED = false;
  var STRICT_KB_FILTER = false;
  var IS_SYSTEM_ADMIN = false;

  function normalizeKbTitle(text) {
    return String(text || "")
      .replace(/\s*[（(][^）)]*[）)]\s*$/g, "")
      .replace(/\s*\d+\s*$/g, "")
      .trim()
      .toLowerCase();
  }

  function addAllowedKbTitle(value) {
    var n = normalizeKbTitle(value);
    if (n) ALLOWED_KB_TITLES.add(n);
  }

  function addAllowedDatasetId(value) {
    var id = String(value || "").trim();
    if (id) ALLOWED_DATASET_IDS.add(id);
  }

  function extractDatasetIdFromNode(node) {
    if (!node) return "";
    var links = [];
    if (node.querySelectorAll) {
      node.querySelectorAll("a[href]").forEach(function (a) {
        links.push(a.getAttribute("href"));
      });
    }
    if (node.getAttribute) {
      var href = node.getAttribute("href");
      if (href) links.push(href);
      var dataId =
        node.getAttribute("data-id") ||
        node.getAttribute("data-key") ||
        node.getAttribute("data-dataset-id");
      if (dataId) return String(dataId).trim();
    }
    for (var i = 0; i < links.length; i++) {
      var m = String(links[i] || "").match(
        /(?:dataset|knowledgebase|kb)[s]?\/([a-f0-9-]{32,36})/i
      );
      if (m) return m[1];
    }
    return "";
  }

  function isAllowedDatasetId(id) {
    if (!STRICT_KB_FILTER || IS_SYSTEM_ADMIN) return true;
    if (!ALLOWED_DATASET_IDS.size) return true;
    return ALLOWED_DATASET_IDS.has(String(id || "").trim());
  }

  function isAllowedKbNode(node, text) {
    if (!KB_VISIBILITY_FILTER_ENABLED) return true;
    var dsId = extractDatasetIdFromNode(node);
    if (dsId && !isAllowedDatasetId(dsId)) return false;
    if (!text || !normalizeKbTitle(text)) return !STRICT_KB_FILTER;
    return isAllowedKbTitle(text);
  }

  function rebuildAllowedKbTitles(theme) {
    ALLOWED_KB_TITLES = new Set();
    ALLOWED_DATASET_IDS = new Set();
    KB_VISIBILITY_FILTER_ENABLED = false;
    STRICT_KB_FILTER = false;
    IS_SYSTEM_ADMIN = !!(theme && theme.is_system_admin);
    if (IS_SYSTEM_ADMIN) {
      revealAllHiddenKnowledgeBases();
      return;
    }
    STRICT_KB_FILTER = !!(theme && theme.kb_visibility_strict);
    var ids = (theme && theme.allowed_dataset_ids) || [];
    for (var j = 0; j < ids.length; j++) {
      addAllowedDatasetId(ids[j]);
    }
    var list = (theme && theme.knowflow_kb_labels) || [];
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      if (!item) continue;
      addAllowedKbTitle(item.name);
      addAllowedKbTitle(item.label);
    }
    var suf = (theme && theme.dept_suffix_labels) || {};
    Object.keys(suf).forEach(function (key) {
      addAllowedKbTitle(suf[key]);
    });
    KB_VISIBILITY_FILTER_ENABLED = STRICT_KB_FILTER || ALLOWED_KB_TITLES.size > 0;
  }

  function isAllowedKbTitle(text) {
    if (!KB_VISIBILITY_FILTER_ENABLED) return true;
    var n = normalizeKbTitle(text);
    if (!n) return !STRICT_KB_FILTER;
    return ALLOWED_KB_TITLES.has(n);
  }

  function hideUnauthorizedKnowledgeBases() {
    if (IS_SYSTEM_ADMIN) {
      revealAllHiddenKnowledgeBases();
      return;
    }
    if (!KB_VISIBILITY_FILTER_ENABLED) return;

    document
      .querySelectorAll('[class*="searchSide"] .ant-tree-treenode, [class*="searchSide"] .ant-tree .ant-tree-treenode')
      .forEach(function (node) {
        var titleEl =
          node.querySelector('[class*="knowledgeName"]') ||
          node.querySelector(".ant-tree-title") ||
          node.querySelector(".ant-typography");
        var text = titleEl ? titleEl.textContent : node.textContent;
        if (!text || !normalizeKbTitle(text)) return;
        if (isAllowedKbNode(node, text)) {
          showKbElement(node);
        } else {
          hideKbElement(node);
        }
      });

    document
      .querySelectorAll(
        '[class*="knowledgeCardContainer"] [class*="card"], ' +
          '[class*="knowledgeList"] [class*="card"], ' +
          '[class*="datasetCard"]'
      )
      .forEach(function (card) {
        var titleEl =
          card.querySelector('[class*="title"]') ||
          card.querySelector("h3") ||
          card.querySelector("h4") ||
          card.querySelector(".ant-typography");
        var text = titleEl ? titleEl.textContent : "";
        if (!text || !normalizeKbTitle(text)) return;
        if (isAllowedKbNode(card, text)) {
          showKbElement(card);
        } else {
          hideKbElement(card);
        }
      });
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

  function isPlatformEmbedMode() {
    var params = new URLSearchParams(location.search);
    var embed =
      params.get("zt_embed") ||
      document.documentElement.getAttribute("data-zt-platform-embed") ||
      "";
    return embed === "1" || embed === "search" || embed === "knowledge";
  }

  function isKnowflowLoginPath() {
    var path = (location.pathname || "").replace(/\/+$/, "").toLowerCase();
    return (
      path === "/login" ||
      path.endsWith("/login") ||
      path.indexOf("/login-next") >= 0
    );
  }

  var ssoRefreshRequestedAt = 0;

  function requestParentEmbedSso() {
    if (!window.parent || window.parent === window) return;
    var now = Date.now();
    if (now - ssoRefreshRequestedAt < 2500) return;
    ssoRefreshRequestedAt = now;
    try {
      window.parent.postMessage({ type: "zt-request-embed-sso" }, "*");
    } catch (e) {
      /* ignore */
    }
  }

  function suppressKnowflowLoginPage() {
    if (!isPlatformEmbedMode() || !isKnowflowLoginPath()) return;
    try {
      document.documentElement.setAttribute("data-zt-suppress-login", "1");
    } catch (e) {
      /* ignore */
    }
    var auth = "";
    try {
      auth = (localStorage.getItem("Authorization") || "").trim();
    } catch (e) {
      auth = "";
    }
    if (auth) {
      var embed = document.documentElement.getAttribute("data-zt-platform-embed") || "knowledge";
      var target = embed === "search" ? "/search" : "/knowledge";
      var path = (location.pathname || "").replace(/\/+$/, "") || "/";
      if (path !== target && path.indexOf(target + "/") !== 0) {
        var qs = new URLSearchParams(location.search);
        qs.delete("auth");
        var nextQs = qs.toString();
        location.replace(target + (nextQs ? "?" + nextQs : "") + location.hash);
        return;
      }
    }
    requestParentEmbedSso();
  }

  var PLATFORM_DISPLAY_NAME = "";
  /** RAGFlow 技术库名 → 展示名（用户名 / 部门名 / 公司） */
  var KB_LABEL_MAP = {};
  /** zt-dept-xxxxxx 的 6 位后缀 → 部门名 */
  var DEPT_SUFFIX_LABELS = {};

  function applyKnowflowKbLabels(theme) {
    var list = (theme && theme.knowflow_kb_labels) || [];
    KB_LABEL_MAP = {};
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      if (!item || !item.name || !item.label) continue;
      KB_LABEL_MAP[String(item.name).trim()] = String(item.label).trim();
    }
    DEPT_SUFFIX_LABELS = {};
    var suf = (theme && theme.dept_suffix_labels) || {};
    Object.keys(suf).forEach(function (key) {
      var k = String(key).trim().toLowerCase();
      var v = String(suf[key] || "").trim();
      if (k && v) DEPT_SUFFIX_LABELS[k] = v;
    });
    rebuildAllowedKbTitles(theme);
    hideUnauthorizedKnowledgeBases();
  }

  function deptLabelFromSuffix(suffix) {
    var s = String(suffix || "").trim().toLowerCase();
    return DEPT_SUFFIX_LABELS[s] || "";
  }

  function replaceZtLegacyKbText(text) {
    if (!text || text.indexOf("zt-") === -1) return text;
    var out = text;
    var keys = Object.keys(KB_LABEL_MAP);
    for (var i = 0; i < keys.length; i++) {
      var technical = keys[i];
      var label = KB_LABEL_MAP[technical];
      if (!label || technical === label) continue;
      if (out.indexOf(technical) !== -1) {
        out = out.split(technical).join(label);
      }
    }
    if (out.indexOf("zt-company") !== -1) {
      out = out.split("zt-company").join(KB_LABEL_MAP["公司"] || "公司");
    }
    out = out.replace(/\bzt-personal-[\w-]+\b/gi, function (m) {
      return KB_LABEL_MAP[m] || PLATFORM_DISPLAY_NAME || "我的";
    });
    out = out.replace(/zt-dept-([a-f0-9]{6})/gi, function (m, suf) {
      return KB_LABEL_MAP[m] || deptLabelFromSuffix(suf) || "部门";
    });
    out = out.replace(/([\w\u4e00-\u9fff]+)-([a-f0-9]{6})/g, function (m, _prefix, suf) {
      if (m.indexOf("zt-") === 0) return m;
      var bySuf = deptLabelFromSuffix(suf);
      return bySuf || KB_LABEL_MAP[m] || m;
    });
    out = out.replace(/\bzt-platform-[\w-]+\b/gi, function (m) {
      return KB_LABEL_MAP[m] || PLATFORM_DISPLAY_NAME || "我的";
    });
    return out;
  }

  function patchElementKbLabel(el) {
    if (!el || !el.getAttribute) return;
    ["title", "aria-label", "data-name", "data-title"].forEach(function (attr) {
      var raw = el.getAttribute(attr);
      if (!raw || raw.indexOf("zt-") === -1) return;
      var next = replaceZtLegacyKbText(raw);
      if (next !== raw) el.setAttribute(attr, next);
    });
  }

  function patchKnowflowKbLabels() {
    var keys = Object.keys(KB_LABEL_MAP);
    if (!keys.length && !PLATFORM_DISPLAY_NAME && !Object.keys(DEPT_SUFFIX_LABELS).length) {
      return;
    }
    var walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      null
    );
    var node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent || parent.tagName === "SCRIPT" || parent.tagName === "STYLE") {
        continue;
      }
      var text = node.textContent;
      if (!text || text.indexOf("zt-") === -1) continue;
      var next = replaceZtLegacyKbText(text);
      if (next !== text) node.textContent = next;
    }
    document.querySelectorAll("[title],[aria-label],[data-name],[data-title]").forEach(patchElementKbLabel);
    document.querySelectorAll("input[value*='zt-dept'],textarea").forEach(function (el) {
      if (el.tagName === "TEXTAREA") {
        var t = el.value;
        if (t && t.indexOf("zt-dept") !== -1) {
          var n = replaceZtLegacyKbText(t);
          if (n !== t) el.value = n;
        }
        return;
      }
      var v = el.value;
      if (v && v.indexOf("zt-dept") !== -1) {
        var nv = replaceZtLegacyKbText(v);
        if (nv !== v) el.value = nv;
      }
    });
  }

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
    applyKnowflowKbLabels(t);
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

  function enablePlatformEmbedChrome(mode) {
    var m = (mode || "1").trim();
    if (m !== "search" && m !== "knowledge" && m !== "1") {
      m = "1";
    }
    try {
      document.documentElement.setAttribute("data-zt-platform-embed", m);
    } catch (e) {
      /* ignore */
    }
    applyEmbedLayoutChrome(m);
  }

  /** 仅隐藏根布局应用导航（siderStyle），保留 /search 的 searchSide 知识库树 */
  function applyEmbedLayoutChrome(mode) {
    var embed = (mode || document.documentElement.getAttribute("data-zt-platform-embed") || "").trim();
    if (!embed) return;
    var path = (location.pathname || "").replace(/\/+$/, "") || "/";
    var onSearch = path === "/search" || embed === "search";

    document.querySelectorAll("aside.ant-layout-sider, .ant-layout-sider").forEach(function (el) {
      var cls = typeof el.className === "string" ? el.className : "";
      if (cls.indexOf("searchSide") >= 0) {
        el.style.removeProperty("display");
        el.style.removeProperty("width");
        el.style.removeProperty("flex");
        el.style.removeProperty("pointer-events");
        return;
      }
      if (cls.indexOf("siderStyle") >= 0) {
        el.style.setProperty("display", "none", "important");
        el.style.setProperty("width", "0", "important");
        el.style.setProperty("min-width", "0", "important");
        el.style.setProperty("max-width", "0", "important");
        el.style.setProperty("flex", "0 0 0", "important");
        el.style.setProperty("pointer-events", "none", "important");
      }
    });

    if (onSearch) {
      document.querySelectorAll('aside.ant-layout-sider[class*="searchSide"]').forEach(function (el) {
        el.style.setProperty("flex", "0 0 220px", "important");
        el.style.setProperty("width", "220px", "important");
        el.style.setProperty("display", "block", "important");
        el.style.setProperty("pointer-events", "auto", "important");
      });
      var rootLayout = document.querySelector("#root > .ant-layout.ant-layout-has-sider");
      if (rootLayout) {
        var main = rootLayout.querySelector(":scope > .ant-layout");
        if (main) {
          main.style.setProperty("margin-left", "0", "important");
          main.style.setProperty("margin-inline-start", "0", "important");
        }
      }
    }
  }

  function bootstrapEmbedFromUrl() {
    var params = new URLSearchParams(location.search);
    var embed = params.get("zt_embed");
    if (embed === "1" || embed === "search" || embed === "knowledge") {
      enablePlatformEmbedChrome(embed);
      return true;
    }
    return false;
  }

  window.addEventListener("message", function (ev) {
    if (!ev.data) return;
    if (ev.data.type === "zt-platform-sso") {
      applyPlatformSso(ev.data.sso);
      return;
    }
    if (ev.data.type === "zt-platform-embed") {
      enablePlatformEmbedChrome(ev.data.mode || "1");
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
    "[data-zt-hidden-file='1']{display:none!important}" +
    "html[data-zt-suppress-login='1'] #root," +
    "html[data-zt-platform-embed] .login-page," +
    "html[data-zt-platform-embed] [class*='login-page']," +
    "html[data-zt-platform-embed] [class*='loginPage']" +
    "{visibility:hidden!important;opacity:0!important;pointer-events:none!important}";
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
    suppressKnowflowLoginPage();
    if (brandingTick % 4 === 0) applyPlatformLogo();
    if (PLATFORM_DISPLAY_NAME) patchWelcomeNickname(PLATFORM_DISPLAY_NAME);
    patchKnowflowKbLabels();
    hideUnauthorizedKnowledgeBases();
    if (document.documentElement.getAttribute("data-zt-platform-embed")) {
      applyEmbedLayoutChrome();
    }
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
      suppressKnowflowLoginPage();
    }, 0);
  };
  history.replaceState = function () {
    _replace.apply(history, arguments);
    setTimeout(function () {
      hideFileManagerMenu();
      redirectFromFileManager();
      suppressKnowflowLoginPage();
    }, 0);
  };

  bootstrapEmbedFromUrl();
  suppressKnowflowLoginPage();
})();
