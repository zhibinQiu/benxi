<script setup>
defineOptions({ name: "NoteView" });
import { ref, computed, onMounted, onActivated, watch, nextTick, onUnmounted, h } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AddOutline,
  ArrowRedoOutline,
  ArrowUndoOutline,
  CheckmarkOutline,
  ChevronForwardOutline,
  CloseOutline,
  CreateOutline,
  DocumentTextOutline,
  EyeOutline,
  FolderOutline,
  MenuOutline,
  PinOutline,
  SearchOutline,
  FolderOpenOutline,
  ShareSocialOutline,
  SparklesOutline,
  SwapHorizontalOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import IconAction from "../components/IconAction.vue";
import AdminFormModal from "../components/AdminFormModal.vue";
import ShareLinkModal from "../components/ShareLinkModal.vue";
import TodosPanel from "../components/TodosPanel.vue";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension";
import { renderMarkdown } from "../utils/markdown.js";
import {
  fetchNoteMenus,
  createNoteMenu,
  updateNoteMenu,
  deleteNoteMenu,
  fetchNoteFiles,
  fetchNoteFile,
  createNoteFile,
  updateNoteFile,
  deleteNoteFile,
  uploadNoteImage,
  polishNoteContent,
  publishNoteFile,
  shareNoteFile,
  unshareNoteFile,
  getNoteShareUrl,
} from "../api/notes";

const ui = usePlatformUi();
const route = useRoute();
const router = useRouter();
const { headerExtensionActive } = usePageHeaderExtension();
const headerTeleportReady = ref(false);

const SIDEBAR_KEY = "note-sidebar-collapsed";
const FOLDER_KEY = "note-current-folder";
const FILES_PAGE_SIZE = 8;
const PAGE_TABS = [
  { key: "notes", label: "笔记" },
  { key: "todos", label: "待办" },
];

function resolvePageTab(tab) {
  return tab === "todos" ? "todos" : "notes";
}

const activePageTab = ref(resolvePageTab(route.query.tab));
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_KEY) === "1");

const menus = ref([]);
const menuFiles = ref({});
const filesLoading = ref(false);

const currentNote = ref(null);
const currentMenuId = ref(localStorage.getItem(FOLDER_KEY) || null);
const searchQuery = ref("");
const filePage = ref(1);

const saving = ref(false);
const polishing = ref(false);
const sharing = ref(false);
const importingLibrary = ref(false);
const editorMode = ref("edit");

const showPolishModal = ref(false);
const polishDirection = ref("");
const polishSelection = ref(null); // { start, end, text } | null

const showShareModal = ref(false);
const lastGeneratedShareUrl = ref("");

const renamingInline = ref(false);
const renameText = ref("");

const creatingFolder = ref(false);
const newMenuName = ref("");

const editorContent = ref("");
const textareaRef = ref(null);
let saveTimer = null;
let historyTimer = null;
let applyingHistory = false;
let selectSeq = 0;
const noteContentCache = new Map();

const HISTORY_MAX = 80;
const editHistory = ref([""]);
const historyIndex = ref(0);

const canUndo = computed(() => historyIndex.value > 0);
const canRedo = computed(() => historyIndex.value < editHistory.value.length - 1);

const isEditingTitle = ref(false);
const titleEditValue = ref("");

const renderedHtml = computed(() => {
  if (!editorContent.value) return '<p class="ed-placeholder">开始编写…</p>';
  return renderMarkdown(editorContent.value);
});

const currentNoteTitle = computed(() =>
  currentNote.value ? currentNote.value.title || "无标题" : ""
);

const currentShareUrl = computed(() =>
  currentNote.value?.share_token ? getNoteShareUrl(currentNote.value.share_token) : ""
);

const currentMenu = computed(() =>
  menus.value.find((m) => m.id === currentMenuId.value) || null
);

const currentMenuName = computed(() => currentMenu.value?.name || "选择文件夹");

const currentMenuFiles = computed(() => menuFiles.value[currentMenuId.value] || []);

const filteredFiles = computed(() => {
  let list = currentMenuFiles.value;
  const q = searchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (n) =>
        (n.title || "").toLowerCase().includes(q) ||
        (n.content || "").toLowerCase().includes(q)
    );
  }
  return list;
});

const filePageCount = computed(() =>
  Math.max(1, Math.ceil(filteredFiles.value.length / FILES_PAGE_SIZE) || 1)
);

const pagedFiles = computed(() => {
  const start = (filePage.value - 1) * FILES_PAGE_SIZE;
  return filteredFiles.value.slice(start, start + FILES_PAGE_SIZE);
});

const folderDropdownOptions = computed(() => {
  const opts = menus.value.map((m) => ({
    label: m.name,
    key: `folder:${m.id}`,
    icon: () =>
      h(NIcon, {
        size: 14,
        component: m.id === currentMenuId.value ? CheckmarkOutline : FolderOutline,
      }),
  }));
  if (opts.length) opts.push({ type: "divider", key: "d1" });
  opts.push({
    label: "新建文件夹",
    key: "action:create",
    icon: () => h(NIcon, { size: 14, component: AddOutline }),
  });
  if (currentMenuId.value) {
    opts.push({
      label: "重命名当前",
      key: "action:rename",
      icon: () => h(NIcon, { size: 14, component: CreateOutline }),
    });
    opts.push({
      label: "删除当前",
      key: "action:delete",
      icon: () => h(NIcon, { size: 14, component: TrashOutline }),
    });
  }
  return opts;
});

watch(searchQuery, () => {
  filePage.value = 1;
});

watch(currentMenuId, () => {
  filePage.value = 1;
});

watch(filteredFiles, (list) => {
  const maxPage = Math.max(1, Math.ceil(list.length / FILES_PAGE_SIZE) || 1);
  if (filePage.value > maxPage) filePage.value = maxPage;
});

const mdTools = [
  { key: "h1", label: "H1", prefix: "# ", suffix: "", placeholder: "标题" },
  { key: "h2", label: "H2", prefix: "## ", suffix: "", placeholder: "标题" },
  { key: "h3", label: "H3", prefix: "### ", suffix: "", placeholder: "标题" },
  { key: "bold", label: "B", prefix: "**", suffix: "**", placeholder: "粗体" },
  { key: "italic", label: "I", prefix: "*", suffix: "*", placeholder: "斜体" },
  { key: "ul", label: "列表", prefix: "- ", suffix: "", placeholder: "列表项" },
  { key: "ol", label: "有序", prefix: "1. ", suffix: "", placeholder: "列表项" },
  { key: "quote", label: "引用", prefix: "> ", suffix: "", placeholder: "引用" },
  { key: "code", label: "代码", prefix: "```\n", suffix: "\n```", placeholder: "code" },
  { key: "link", label: "链接", prefix: "[", suffix: "](url)", placeholder: "文字" },
  { key: "hr", label: "分割", prefix: "\n---\n", suffix: "", placeholder: "" },
];

function formatDate(s) {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "";
  const n = new Date();
  const time = d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === n.toDateString()) return `今天 ${time}`;
  const y = new Date(n);
  y.setDate(y.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return `昨天 ${time}`;
  const datePart =
    d.getFullYear() === n.getFullYear()
      ? `${d.getMonth() + 1}月${d.getDate()}日`
      : `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
  return `${datePart} ${time}`;
}

function switchPageTab(key) {
  if (key === activePageTab.value) return;
  activePageTab.value = key;
  router.replace({
    name: "notes",
    query: key === "todos" ? { tab: "todos" } : {},
  });
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? "1" : "0");
}

async function loadMenus() {
  try {
    const d = await fetchNoteMenus();
    menus.value = (d || []).map((m) => ({ ...m, note_count: m.note_count || 0 }));
  } catch {
    menus.value = [];
  }

  const saved = currentMenuId.value;
  const exists = saved && menus.value.some((m) => m.id === saved);
  if (exists) {
    await selectFolder(saved, { keepNote: true });
  } else if (menus.value.length) {
    await selectFolder(menus.value[0].id, { keepNote: false });
  } else {
    currentMenuId.value = null;
    localStorage.removeItem(FOLDER_KEY);
  }
}

async function loadMenuFiles(menuId, { quiet = false } = {}) {
  if (!menuId) return;
  const hasCache = Array.isArray(menuFiles.value[menuId]);
  if (!quiet && !hasCache) filesLoading.value = true;
  try {
    const list = (await fetchNoteFiles(menuId)) || [];
    menuFiles.value[menuId] = list;
  } catch {
    if (!hasCache) menuFiles.value[menuId] = [];
  } finally {
    filesLoading.value = false;
  }
}

async function selectFolder(menuId, { keepNote = false } = {}) {
  if (!menuId) return;
  const sameFolder = currentMenuId.value === menuId;
  currentMenuId.value = menuId;
  localStorage.setItem(FOLDER_KEY, menuId);
  if (!sameFolder) {
    searchQuery.value = "";
    filePage.value = 1;
  }
  creatingFolder.value = false;
  renamingInline.value = false;
  if (!keepNote) {
    currentNote.value = null;
    applyingHistory = true;
    editorContent.value = "";
    resetEditHistory("");
    applyingHistory = false;
  }
  await loadMenuFiles(menuId, { quiet: sameFolder && keepNote });
}

function onFolderDropdownSelect(key) {
  if (typeof key !== "string") return;
  if (key.startsWith("folder:")) {
    selectFolder(key.slice(7));
    return;
  }
  if (key === "action:create") {
    creatingFolder.value = true;
    renamingInline.value = false;
    newMenuName.value = "";
    nextTick(() => {
      document.querySelector(".sb-inline-input")?.focus();
    });
    return;
  }
  if (key === "action:rename") {
    if (!currentMenu.value) return;
    renamingInline.value = true;
    creatingFolder.value = false;
    renameText.value = currentMenu.value.name;
    nextTick(() => {
      document.querySelector(".sb-inline-input")?.focus();
    });
    return;
  }
  if (key === "action:delete" && currentMenu.value) {
    deleteMenuDirect(currentMenu.value);
  }
}

async function addMenu() {
  const n = newMenuName.value.trim();
  if (!n) return;
  try {
    const created = await createNoteMenu(n);
    newMenuName.value = "";
    creatingFolder.value = false;
    if (created?.id) {
      menus.value = [...menus.value, { ...created, note_count: 0 }];
      await selectFolder(created.id);
    }
  } catch (e) {
    ui.error(e?.message || "创建失败");
  }
}

async function confirmRenameMenu() {
  if (!renamingInline.value || !currentMenuId.value) return;
  renamingInline.value = false;
  const n = renameText.value.trim();
  if (!n || n === currentMenu.value?.name) return;
  try {
    await updateNoteMenu(currentMenuId.value, { name: n });
    const idx = menus.value.findIndex((m) => m.id === currentMenuId.value);
    if (idx >= 0) {
      menus.value[idx] = { ...menus.value[idx], name: n };
    }
  } catch (e) {
    ui.error(e?.message || "重命名失败");
  }
}

function cancelInlineFolderEdit() {
  creatingFolder.value = false;
  renamingInline.value = false;
  newMenuName.value = "";
  renameText.value = "";
}

async function deleteMenuDirect(m) {
  if (!m?.id) return;
  try {
    await deleteNoteMenu(m.id);
    delete menuFiles.value[m.id];
    menus.value = menus.value.filter((x) => x.id !== m.id);
    if (currentMenuId.value === m.id) {
      const next = menus.value[0];
      if (next) {
        await selectFolder(next.id);
      } else {
        currentMenuId.value = null;
        localStorage.removeItem(FOLDER_KEY);
        currentNote.value = null;
        applyingHistory = true;
        editorContent.value = "";
        resetEditHistory("");
        applyingHistory = false;
      }
    }
  } catch (e) {
    ui.error(e?.message || "删除失败");
  }
}

async function selectFile(file) {
  if (!file?.id || currentNote.value?.id === file.id) return;

  // 离开前缓存并异步落盘，不阻塞切换
  if (currentNote.value?.id) {
    noteContentCache.set(currentNote.value.id, {
      ...currentNote.value,
      content: editorContent.value,
      _full: true,
    });
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
      void saveNoteContent();
    }
  }

  const cached = noteContentCache.get(file.id);
  const instant = {
    id: file.id,
    folder_id: file.folder_id,
    title: file.title || cached?.title || "新文件",
    content: cached?.content ?? "",
    is_pinned: file.is_pinned ?? cached?.is_pinned ?? false,
    share_token: file.share_token ?? cached?.share_token ?? null,
    sort_order: file.sort_order ?? cached?.sort_order ?? 0,
    created_at: file.created_at || cached?.created_at,
    updated_at: file.updated_at || cached?.updated_at,
    view_count: cached?.view_count ?? 0,
  };

  const seq = ++selectSeq;
  currentNote.value = instant;
  applyingHistory = true;
  editorContent.value = instant.content || "";
  resetEditHistory(editorContent.value);
  applyingHistory = false;
  currentMenuId.value = file.folder_id || currentMenuId.value;
  isEditingTitle.value = false;
  editorMode.value = "edit";

  // 已有完整缓存时后台轻量刷新；否则立即拉正文
  try {
    const d = await fetchNoteFile(file.id);
    if (seq !== selectSeq || currentNote.value?.id !== file.id) return;
    noteContentCache.set(file.id, { ...d, _full: true });
    const stillPristine = editorContent.value === (instant.content || "");
    currentNote.value = d;
    if (stillPristine) {
      applyingHistory = true;
      editorContent.value = d.content || "";
      resetEditHistory(editorContent.value);
      applyingHistory = false;
    }
  } catch {
    if (seq === selectSeq && !cached) ui.error("加载文件失败");
  }
}

async function addFile() {
  if (!currentMenuId.value) {
    ui.warning("请先选择文件夹");
    return;
  }
  try {
    const d = await createNoteFile({
      folder_id: currentMenuId.value,
      title: "新文件",
      content: "",
    });
    if (!d?.id) {
      ui.error("创建文件失败");
      return;
    }
    const mid = currentMenuId.value;
    const list = menuFiles.value[mid] ? [...menuFiles.value[mid]] : [];
    list.unshift(d);
    menuFiles.value[mid] = list;
    await selectFile(d);
    editorMode.value = "edit";
  } catch (e) {
    ui.error(e?.message || "创建文件失败");
  }
}

function moveMenuOptions(file) {
  return menus.value
    .filter((m) => m.id !== file.folder_id)
    .map((m) => ({ label: m.name, key: m.id }));
}

async function moveFileToMenu(file, targetMenuId) {
  try {
    const fromId = file.folder_id;
    await updateNoteFile(file.id, { folder_id: targetMenuId });
    if (fromId && menuFiles.value[fromId]) {
      menuFiles.value[fromId] = menuFiles.value[fromId].filter((f) => f.id !== file.id);
    }
    const moved = { ...file, folder_id: targetMenuId };
    const targetList = menuFiles.value[targetMenuId] ? [...menuFiles.value[targetMenuId]] : [];
    targetList.unshift(moved);
    menuFiles.value[targetMenuId] = targetList;
    if (currentNote.value?.id === file.id) {
      currentNote.value = { ...currentNote.value, folder_id: targetMenuId };
      currentMenuId.value = targetMenuId;
    }
  } catch {
    ui.error("移动失败");
  }
}

async function deleteFileDirect(file, ev) {
  ev?.stopPropagation();
  try {
    const mid = file.folder_id;
    await deleteNoteFile(file.id);
    if (currentNote.value?.id === file.id) {
      currentNote.value = null;
      applyingHistory = true;
      editorContent.value = "";
      resetEditHistory("");
      applyingHistory = false;
    }
    if (mid && menuFiles.value[mid]) {
      menuFiles.value[mid] = menuFiles.value[mid].filter((f) => f.id !== file.id);
    }
  } catch {
    ui.error("删除失败");
  }
}

function resetEditHistory(content = "") {
  if (historyTimer) {
    clearTimeout(historyTimer);
    historyTimer = null;
  }
  editHistory.value = [content ?? ""];
  historyIndex.value = 0;
}

function pushEditHistory(content) {
  if (applyingHistory) return;
  const value = content ?? "";
  const cur = editHistory.value[historyIndex.value];
  if (cur === value) return;
  const next = editHistory.value.slice(0, historyIndex.value + 1);
  next.push(value);
  while (next.length > HISTORY_MAX) next.shift();
  editHistory.value = next;
  historyIndex.value = next.length - 1;
}

function schedulePushHistory(content) {
  if (applyingHistory) return;
  if (historyTimer) clearTimeout(historyTimer);
  historyTimer = setTimeout(() => pushEditHistory(content), 280);
}

function applyHistoryContent(content) {
  applyingHistory = true;
  editorContent.value = content ?? "";
  nextTick(() => {
    applyingHistory = false;
    const el = textareaRef.value;
    if (el) {
      const pos = el.value.length;
      el.selectionStart = el.selectionEnd = pos;
      el.focus();
    }
  });
}

function undoEdit() {
  if (historyTimer) {
    clearTimeout(historyTimer);
    historyTimer = null;
    pushEditHistory(editorContent.value);
  }
  if (historyIndex.value <= 0) return;
  historyIndex.value -= 1;
  applyHistoryContent(editHistory.value[historyIndex.value]);
}

function redoEdit() {
  if (historyTimer) {
    clearTimeout(historyTimer);
    historyTimer = null;
    pushEditHistory(editorContent.value);
  }
  if (historyIndex.value >= editHistory.value.length - 1) return;
  historyIndex.value += 1;
  applyHistoryContent(editHistory.value[historyIndex.value]);
}

function onEditorKeydown(e) {
  const mod = e.metaKey || e.ctrlKey;
  if (!mod) return;
  const key = e.key.toLowerCase();
  if (key === "z" && !e.shiftKey) {
    e.preventDefault();
    undoEdit();
  } else if ((key === "z" && e.shiftKey) || key === "y") {
    e.preventDefault();
    redoEdit();
  }
}

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNoteContent, 800);
}

async function saveNoteContent() {
  if (!currentNote.value) return;
  saving.value = true;
  try {
    const c = editorContent.value;
    const fl = c
      .split("\n")
      .map((l) => l.trim())
      .find((l) => l && !l.startsWith("#") && !l.startsWith("!["));
    const tm = c.match(/^#\s+(.+)/m);
    const t = tm ? tm[1].trim().slice(0, 200) : (fl || "新文件").slice(0, 200);
    await updateNoteFile(currentNote.value.id, { content: c, title: t });
    const now = new Date().toISOString();
    currentNote.value = { ...currentNote.value, content: c, title: t, updated_at: now };
    noteContentCache.set(currentNote.value.id, { ...currentNote.value, _full: true });
    const mid = currentNote.value.folder_id;
    if (mid && menuFiles.value[mid]) {
      const idx = menuFiles.value[mid].findIndex((f) => f.id === currentNote.value.id);
      if (idx >= 0) {
        menuFiles.value[mid][idx] = {
          ...menuFiles.value[mid][idx],
          title: t,
          updated_at: now,
        };
      }
    }
  } catch {
    /* 静默 */
  } finally {
    saving.value = false;
  }
}

function startEditTitle() {
  if (!currentNote.value) return;
  titleEditValue.value = currentNote.value.title || "";
  isEditingTitle.value = true;
  nextTick(() => document.querySelector(".ed-title-input")?.focus());
}

async function confirmEditTitle() {
  if (!isEditingTitle.value || !currentNote.value) return;
  isEditingTitle.value = false;
  const newTitle = titleEditValue.value.trim().slice(0, 200);
  if (!newTitle || newTitle === currentNote.value.title) return;
  try {
    await updateNoteFile(currentNote.value.id, { title: newTitle });
    currentNote.value = { ...currentNote.value, title: newTitle };
    const mid = currentNote.value.folder_id;
    if (mid && menuFiles.value[mid]) {
      const idx = menuFiles.value[mid].findIndex((f) => f.id === currentNote.value.id);
      if (idx >= 0) menuFiles.value[mid][idx] = { ...menuFiles.value[mid][idx], title: newTitle };
    }
  } catch {
    ui.error("重命名失败");
  }
}

function cancelEditTitle() {
  isEditingTitle.value = false;
}

async function togglePin(file, ev) {
  ev?.stopPropagation();
  if (!file?.id) return;
  try {
    const pinned = !file.is_pinned;
    await updateNoteFile(file.id, { is_pinned: pinned });
    const mid = file.folder_id;
    if (mid && menuFiles.value[mid]) {
      const list = menuFiles.value[mid].map((f) =>
        f.id === file.id ? { ...f, is_pinned: pinned } : f
      );
      list.sort((a, b) => {
        if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      });
      menuFiles.value[mid] = list;
    }
    if (currentNote.value?.id === file.id) {
      currentNote.value = { ...currentNote.value, is_pinned: pinned };
    }
  } catch {
    ui.error("操作失败");
  }
}

function applyNoteShareToken(token) {
  if (!currentNote.value) return;
  currentNote.value = { ...currentNote.value, share_token: token || null };
  const mid = currentNote.value.folder_id;
  if (mid && menuFiles.value[mid]) {
    const idx = menuFiles.value[mid].findIndex((f) => f.id === currentNote.value.id);
    if (idx >= 0) {
      menuFiles.value[mid][idx] = {
        ...menuFiles.value[mid][idx],
        share_token: token || null,
      };
    }
  }
  lastGeneratedShareUrl.value = token ? getNoteShareUrl(token) : "";
}

async function flushNoteBeforeShare() {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  await saveNoteContent();
}

async function importCurrentNoteToLibrary() {
  if (!currentNote.value || importingLibrary.value) return;
  importingLibrary.value = true;
  try {
    await flushNoteBeforeShare();
    const res = await publishNoteFile(currentNote.value.id, { toLibrary: true });
    ui.success(res?.message || "正在后台加入文档库");
  } catch (e) {
    ui.error(e?.message || "加入文档库失败");
  } finally {
    importingLibrary.value = false;
  }
}

async function generateOrRefreshNoteShare({ regenerate = true } = {}) {
  if (!currentNote.value || sharing.value) return;
  sharing.value = true;
  try {
    await flushNoteBeforeShare();
    const res = await shareNoteFile(currentNote.value.id, { regenerate });
    const token = res?.share_token;
    if (!token) throw new Error("未返回分享令牌");
    applyNoteShareToken(token);
    try {
      await navigator.clipboard.writeText(getNoteShareUrl(token));
      ui.success(regenerate ? "已重新分享，链接已复制" : "链接已复制");
    } catch {
      ui.success(regenerate ? "已重新分享" : "分享链接已生成");
    }
  } catch (e) {
    ui.error(e?.message || "生成分享链接失败");
  } finally {
    sharing.value = false;
  }
}

async function shareCurrentNote() {
  if (!currentNote.value) return;
  lastGeneratedShareUrl.value = currentShareUrl.value;
  showShareModal.value = true;
  if (!currentShareUrl.value) {
    await generateOrRefreshNoteShare({ regenerate: true });
  }
}

async function reshareCurrentNote() {
  await generateOrRefreshNoteShare({ regenerate: true });
}

async function unshareCurrentNote() {
  if (!currentNote.value || sharing.value) return;
  sharing.value = true;
  try {
    await unshareNoteFile(currentNote.value.id);
    applyNoteShareToken(null);
    ui.success("已取消分享");
  } catch (e) {
    ui.error(e?.message || "取消分享失败");
  } finally {
    sharing.value = false;
  }
}

async function copyShareUrl() {
  const url = currentShareUrl.value || lastGeneratedShareUrl.value;
  if (!url) return;
  try {
    await navigator.clipboard.writeText(url);
    ui.success("链接已复制");
  } catch {
    ui.error("复制失败");
  }
}

function capturePolishSelection() {
  const el = textareaRef.value;
  let sel = null;
  if (el && typeof el.selectionStart === "number") {
    const start = el.selectionStart;
    const end = el.selectionEnd;
    if (end > start) {
      sel = {
        start,
        end,
        text: editorContent.value.substring(start, end),
      };
    }
  }
  polishSelection.value = sel;
}

let polishClickTimer = null;

function onPolishClick() {
  capturePolishSelection();
  if (polishClickTimer) clearTimeout(polishClickTimer);
  polishClickTimer = setTimeout(() => {
    polishClickTimer = null;
    runPolish();
  }, 280);
}

function onPolishDblClick(e) {
  e.preventDefault();
  if (polishClickTimer) {
    clearTimeout(polishClickTimer);
    polishClickTimer = null;
  }
  capturePolishSelection();
  showPolishModal.value = true;
}

function savePolishDirection() {
  showPolishModal.value = false;
}

async function runPolish() {
  if (polishing.value) return;
  const sel = polishSelection.value;
  const target = (sel?.text || editorContent.value || "").trim();
  if (!target) {
    ui.warning("请先输入或选中内容");
    return;
  }
  polishing.value = true;
  try {
    const r = await polishNoteContent(target, polishDirection.value.trim());
    if (!r?.content) {
      ui.error("润色失败");
      return;
    }
    if (sel && sel.end > sel.start) {
      editorContent.value =
        editorContent.value.substring(0, sel.start) +
        r.content +
        editorContent.value.substring(sel.end);
      nextTick(() => {
        const el = textareaRef.value;
        if (!el) return;
        el.focus();
        el.selectionStart = sel.start;
        el.selectionEnd = sel.start + r.content.length;
      });
    } else {
      editorContent.value = r.content;
    }
  } catch (e) {
    ui.error(e?.message || "润色失败");
  } finally {
    polishing.value = false;
  }
}

function insertMarkdown({ prefix, suffix, placeholder }) {
  const el = textareaRef.value;
  if (!el) return;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  const selected = editorContent.value.substring(start, end);
  const text = selected || placeholder || "";
  const insert = prefix + text + suffix;
  editorContent.value =
    editorContent.value.substring(0, start) + insert + editorContent.value.substring(end);
  nextTick(() => {
    if (selected) {
      el.selectionStart = start;
      el.selectionEnd = start + insert.length;
    } else if (placeholder) {
      el.selectionStart = start + prefix.length;
      el.selectionEnd = start + prefix.length + text.length;
    } else {
      const pos = start + insert.length;
      el.selectionStart = el.selectionEnd = pos;
    }
    el.focus();
  });
}

async function handlePaste(ev) {
  const items = ev.clipboardData?.items;
  if (!items) return;
  for (const item of items) {
    if (!item.type.startsWith("image/")) continue;
    ev.preventDefault();
    const file = item.getAsFile();
    if (!file) continue;
    try {
      const r = await uploadNoteImage(file);
      if (r?.url) {
        const tag = `![](${r.url})`;
        const el = ev.target;
        const s = el.selectionStart;
        const e = el.selectionEnd;
        editorContent.value =
          editorContent.value.substring(0, s) + tag + editorContent.value.substring(e);
        nextTick(() => {
          el.selectionStart = el.selectionEnd = s + tag.length;
          el.focus();
        });
      }
    } catch {
      ui.error("图片上传失败");
    }
    break;
  }
}

watch(editorContent, (val) => {
  if (applyingHistory) return;
  schedulePushHistory(val);
  if (currentNote.value) debounceSave();
});

watch(
  () => route.query.tab,
  (tab) => {
    activePageTab.value = resolvePageTab(tab);
  }
);

onMounted(() => {
  const markReady = () => {
    headerTeleportReady.value = !!document.getElementById("header-actions");
  };
  nextTick(() => {
    markReady();
    if (!headerTeleportReady.value) {
      requestAnimationFrame(markReady);
    }
  });
  loadMenus();
});
onUnmounted(() => {
  if (saveTimer) clearTimeout(saveTimer);
  if (historyTimer) clearTimeout(historyTimer);
});
onActivated(() => {
  nextTick(() => {
    headerTeleportReady.value = !!document.getElementById("header-actions");
  });
});
</script>

<template>
  <div class="note-page">
    <Teleport v-if="headerTeleportReady && headerExtensionActive" to="#header-actions">
      <div class="note-header-tools">
        <div class="note-tabs">
          <button
            v-for="tab in PAGE_TABS"
            :key="tab.key"
            type="button"
            class="note-tab"
            :class="{ active: activePageTab === tab.key }"
            @click="switchPageTab(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>
        <IconAction
          v-if="activePageTab === 'notes'"
          :label="sidebarCollapsed ? '展开侧栏' : '折叠侧栏'"
          :icon="MenuOutline"
          size="tiny"
          @click="toggleSidebar"
        />
      </div>
    </Teleport>

    <!-- 待办 -->
    <div v-if="activePageTab === 'todos'" class="note-todos">
      <TodosPanel variant="page" />
    </div>

    <!-- 笔记 -->
    <div v-else class="note-root" :class="{ 'note-root--collapsed': sidebarCollapsed }">
      <!-- 折叠窄条 -->
      <button
        v-if="sidebarCollapsed"
        type="button"
        class="sidebar-expand"
        title="展开侧栏"
        @click="toggleSidebar"
      >
        <n-icon :size="12" :component="ChevronForwardOutline" />
      </button>

      <!-- 侧栏：当前文件夹的文件列表 -->
      <aside v-show="!sidebarCollapsed" class="note-sidebar">
        <div class="sb-top">
          <div v-show="!creatingFolder && !renamingInline" class="sb-folder-row">
            <n-dropdown
              trigger="click"
              placement="bottom-start"
              :options="folderDropdownOptions"
              @select="onFolderDropdownSelect"
            >
              <button type="button" class="sb-folder-trigger">
                <n-icon :size="14" :component="FolderOutline" class="sb-folder-trigger__icon" />
                <span class="sb-folder-trigger__name">{{ currentMenuName }}</span>
                <n-icon :size="12" :component="ChevronForwardOutline" class="sb-folder-trigger__chevron" />
              </button>
            </n-dropdown>
            <button
              v-if="currentMenuId"
              type="button"
              class="sb-new-btn"
              title="新建文件"
              @click="addFile"
            >
              <n-icon :size="14" :component="AddOutline" />
            </button>
          </div>

          <div v-show="creatingFolder || renamingInline" class="sb-inline-edit">
            <input
              v-if="creatingFolder"
              v-model="newMenuName"
              class="sb-inline-input"
              placeholder="新文件夹名称"
              @keyup.enter="addMenu"
              @keyup.escape="cancelInlineFolderEdit"
            />
            <input
              v-else
              v-model="renameText"
              class="sb-inline-input"
              placeholder="文件夹名称"
              @keyup.enter="confirmRenameMenu"
              @keyup.escape="cancelInlineFolderEdit"
            />
            <div class="sb-inline-actions">
              <n-button size="tiny" tertiary @click="creatingFolder ? addMenu() : confirmRenameMenu()">
                确定
              </n-button>
              <n-button size="tiny" quaternary @click="cancelInlineFolderEdit">取消</n-button>
            </div>
          </div>

          <div v-if="currentMenuId" class="sb-search">
            <n-icon :size="12" :component="SearchOutline" class="sb-search-icon" />
            <input v-model="searchQuery" placeholder="搜索文件…" class="sb-search-input" />
            <button v-if="searchQuery" type="button" class="sb-search-clear" @click="searchQuery = ''">
              <n-icon :size="11" :component="CloseOutline" />
            </button>
          </div>
        </div>

        <div class="sb-file-list">
          <div v-if="!currentMenuId" class="sb-empty-hint sb-empty-hint--center">
            请先选择文件夹
          </div>
          <div v-else-if="filesLoading && !currentMenuFiles.length" class="sb-empty-hint">
            加载中…
          </div>
          <template v-else>
            <button
              v-for="file in pagedFiles"
              :key="file.id"
              type="button"
              class="sb-file"
              :class="{ active: currentNote?.id === file.id }"
              @click="selectFile(file)"
            >
              <div class="sb-file__body">
                <div class="sb-file__title-row">
                  <n-icon v-if="file.is_pinned" :size="10" :component="PinOutline" class="sb-pin" />
                  <n-icon :size="13" :component="DocumentTextOutline" class="sb-file-icon" />
                  <span class="sb-file-name">{{ file.title || "新文件" }}</span>
                </div>
                <div class="sb-file-date">{{ formatDate(file.updated_at || file.created_at) }}</div>
              </div>
              <div class="sb-file-actions" @click.stop>
                <IconAction
                  :label="file.is_pinned ? '取消置顶' : '置顶'"
                  :icon="PinOutline"
                  size="tiny"
                  variant="table"
                  :active="!!file.is_pinned"
                  @click="togglePin(file, $event)"
                />
                <n-dropdown
                  v-if="moveMenuOptions(file).length"
                  trigger="click"
                  :options="moveMenuOptions(file)"
                  @select="(key) => moveFileToMenu(file, key)"
                >
                  <span>
                    <IconAction
                      label="移动"
                      :icon="SwapHorizontalOutline"
                      size="tiny"
                      variant="table"
                    />
                  </span>
                </n-dropdown>
                <IconAction
                  label="删除"
                  :icon="TrashOutline"
                  size="tiny"
                  variant="table"
                  type="error"
                  @click="deleteFileDirect(file, $event)"
                />
              </div>
            </button>

            <div v-if="!filteredFiles.length" class="sb-empty-hint sb-empty-hint--center">
              {{ searchQuery ? "未找到" : "暂无文件" }}
            </div>
          </template>
        </div>

        <div v-if="currentMenuId && filteredFiles.length > FILES_PAGE_SIZE" class="sb-pager">
          <n-pagination
            v-model:page="filePage"
            :page-size="FILES_PAGE_SIZE"
            :item-count="filteredFiles.length"
            :page-slot="5"
            size="small"
            simple
          />
        </div>
      </aside>

      <!-- 编辑器 -->
      <div class="note-editor">
        <template v-if="currentNote">
          <div class="ed-top">
            <div class="ed-top-main">
              <div class="ed-title-wrap">
                <input
                  v-if="isEditingTitle"
                  v-model="titleEditValue"
                  class="ed-title-input"
                  autofocus
                  @keyup.enter="confirmEditTitle"
                  @keyup.escape="cancelEditTitle"
                  @blur="confirmEditTitle"
                />
                <span v-else class="ed-title" title="点击编辑标题" @click="startEditTitle">
                  {{ currentNoteTitle }}
                </span>
                <span class="ed-ext">.md</span>
                <span v-if="saving" class="ed-saving">保存中…</span>
              </div>
              <div class="ed-actions">
                <IconAction
                  :label="editorMode === 'edit' ? '预览' : '编辑'"
                  :icon="EyeOutline"
                  :active="editorMode === 'preview'"
                  size="tiny"
                  @click="editorMode = editorMode === 'edit' ? 'preview' : 'edit'"
                />
                <IconAction
                  label="加入文档库"
                  :icon="FolderOpenOutline"
                  size="tiny"
                  :loading="importingLibrary"
                  @click="importCurrentNoteToLibrary"
                />
                <IconAction
                  label="分享"
                  :icon="ShareSocialOutline"
                  size="tiny"
                  :loading="sharing"
                  :active="!!currentShareUrl"
                  @click="shareCurrentNote"
                />
              </div>
            </div>
          </div>

          <div v-if="editorMode === 'edit'" class="ed-toolbar">
            <button
              type="button"
              class="md-btn"
              title="撤销 ⌘Z"
              :disabled="!canUndo"
              @click="undoEdit"
            >
              <n-icon :size="12" :component="ArrowUndoOutline" />
            </button>
            <button
              type="button"
              class="md-btn"
              title="重做 ⌘⇧Z"
              :disabled="!canRedo"
              @click="redoEdit"
            >
              <n-icon :size="12" :component="ArrowRedoOutline" />
            </button>
            <span class="ed-toolbar-divider" />
            <button
              v-for="tool in mdTools"
              :key="tool.key"
              type="button"
              class="md-btn"
              @click="insertMarkdown(tool)"
            >
              {{ tool.label }}
            </button>
            <span class="ed-toolbar-divider" />
            <button
              type="button"
              class="md-btn md-btn--ai"
              title="单击润色 · 双击设置方向"
              :disabled="polishing"
              @click="onPolishClick"
              @dblclick="onPolishDblClick"
            >
              <n-icon :size="11" :component="SparklesOutline" :class="{ 'md-btn__spin': polishing }" />
              <span>{{ polishing ? "润色中" : "润色" }}</span>
            </button>
          </div>

          <div class="ed-body">
            <textarea
              v-if="editorMode === 'edit'"
              ref="textareaRef"
              v-model="editorContent"
              class="ed-textarea"
              placeholder="开始编写 Markdown…"
              @paste="handlePaste"
              @keydown="onEditorKeydown"
            />
            <div v-else class="ed-preview-wrap">
              <div class="ed-preview" v-html="renderedHtml" />
            </div>
          </div>
        </template>

        <div v-else class="ed-empty">
          <n-icon :size="44" :component="DocumentTextOutline" class="ed-empty-icon" />
          <h3>工作笔记</h3>
          <p>{{ currentMenuId ? "从左侧选择文件开始编辑" : "先选择一个文件夹" }}</p>
        </div>
      </div>
    </div>

    <AdminFormModal
      v-model:show="showPolishModal"
      title="润色方向"
      width="420px"
    >
      <n-input
        v-model:value="polishDirection"
        type="textarea"
        :rows="3"
        maxlength="500"
        show-count
        placeholder="例如：更简洁、偏正式、适合汇报"
      />
      <template #footer>
        <n-button size="small" @click="showPolishModal = false">取消</n-button>
        <n-button size="small" type="primary" @click="savePolishDirection">保存</n-button>
      </template>
    </AdminFormModal>

    <ShareLinkModal
      v-model:show="showShareModal"
      title="分享笔记"
      :url="lastGeneratedShareUrl || currentShareUrl"
      :shared="!!(lastGeneratedShareUrl || currentShareUrl)"
      :loading="sharing"
      hint="链接可公开访问笔记最新内容；重新分享将更新链接，旧链接失效。"
      @generate="generateOrRefreshNoteShare({ regenerate: true })"
      @reshare="reshareCurrentNote"
      @unshare="unshareCurrentNote"
      @copy="copyShareUrl"
    />
  </div>
</template>

<style scoped>
.note-page {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  width: 100%;
  background: var(--platform-bg);
  color: var(--platform-text);
  font-size: var(--platform-font-size-base);
  overflow: hidden;
}

.note-todos {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--platform-bg);
}

.note-root {
  display: flex !important;
  flex-direction: row !important;
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  overflow: hidden;
  align-items: stretch;
}

.note-root--collapsed .note-editor {
  width: auto;
  flex: 1 1 auto;
}

.sidebar-expand {
  width: 16px;
  min-width: 16px;
  max-width: 16px;
  border: none;
  border-right: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-secondary);
  color: var(--platform-text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 16px;
  transition: background 0.15s, color 0.15s;
}

.sidebar-expand:hover {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
}

.note-sidebar {
  width: 280px;
  min-width: 280px;
  max-width: 280px;
  flex: 0 0 280px !important;
  align-self: stretch;
  background: var(--platform-bg-secondary);
  border-right: 1px solid var(--platform-border-strong);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.sb-top {
  flex-shrink: 0;
  padding: 8px 8px 0;
}

.sb-folder-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sb-folder-row .sb-folder-trigger {
  flex: 1;
  min-width: 0;
}

.sb-new-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--platform-border-strong);
  border-radius: var(--platform-radius-sm, 6px);
  background: var(--platform-bg-elevated);
  color: var(--platform-text-secondary);
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.sb-new-btn:hover {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
}

.sb-folder-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  border: 1px solid var(--platform-border-strong);
  border-radius: var(--platform-radius-sm, 6px);
  background: var(--platform-bg-elevated);
  color: var(--platform-text);
  padding: 6px 8px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s ease;
}
.sb-folder-trigger:hover {
  background: var(--platform-bg-tertiary);
}
.sb-folder-trigger__icon {
  flex-shrink: 0;
  color: var(--platform-text-secondary);
}
.sb-folder-trigger__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
}
.sb-folder-trigger__chevron {
  flex-shrink: 0;
  color: var(--platform-text-tertiary);
  transform: rotate(90deg);
}
.sb-inline-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sb-inline-input {
  width: 100%;
  border: 1px solid var(--platform-accent);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
  outline: none;
  background: var(--platform-bg-elevated);
  color: var(--platform-text);
  box-sizing: border-box;
}
.sb-inline-actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}
.sb-search {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 6px 0 0;
  padding: 4px 7px;
  background: var(--platform-bg-tertiary);
  border-radius: 6px;
}
.sb-search-icon {
  color: var(--platform-text-tertiary);
  flex-shrink: 0;
}
.sb-search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 12px;
  background: transparent;
  color: var(--platform-text);
}
.sb-search-input::placeholder {
  color: var(--platform-text-tertiary);
}
.sb-search-clear {
  display: flex;
  border: none;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
  padding: 0;
}
.sb-file-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 6px 8px;
  min-height: 0;
  contain: content;
}
.sb-empty-hint {
  padding: 10px 6px;
  color: var(--platform-text-tertiary);
  font-size: 11px;
}
.sb-empty-hint--center {
  text-align: center;
  padding: 24px 10px;
}
.sb-file {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  min-height: 36px;
  margin: 0 0 2px;
  padding: 6px 8px;
  border: none;
  border-radius: var(--platform-radius-sm, 6px);
  background: transparent;
  color: var(--platform-text);
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: background 0.12s ease;
}
.sb-file:hover:not(.active) {
  background: var(--platform-bg-tertiary);
}
.sb-file.active {
  background: var(--platform-bg-tertiary);
}
.sb-file__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.sb-file__title-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.sb-pin {
  color: var(--platform-text-secondary);
  flex-shrink: 0;
}
.sb-file-icon {
  flex-shrink: 0;
  color: var(--platform-text-secondary);
}
.sb-file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.3;
}
.sb-file-date {
  padding-left: 18px;
  font-size: 10px;
  color: var(--platform-text-tertiary);
  line-height: 1.3;
}
.sb-file-actions {
  visibility: hidden;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.sb-file-actions :deep(.n-button.table-icon-action) {
  width: 22px !important;
  height: 22px !important;
  min-width: 22px !important;
}
.sb-file-actions :deep(.n-icon) {
  font-size: 13px !important;
}
.sb-file:hover .sb-file-actions,
.sb-file.active .sb-file-actions {
  visibility: visible;
}

.sb-pager {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  padding: 8px 6px 10px;
  border-top: 1px solid var(--platform-border);
}
.note-editor {
  flex: 1 1 auto !important;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  width: auto !important;
  overflow: hidden;
  background: var(--platform-bg-elevated);
}

.ed-top {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--platform-border-strong);
  flex-shrink: 0;
  min-height: 42px;
}

.ed-top-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.ed-title-wrap {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  flex: 1;
}

.ed-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.ed-actions :deep(.n-button.icon-action) {
  width: 22px !important;
  height: 22px !important;
  min-width: 22px !important;
  padding: 0 !important;
}

.ed-actions :deep(.n-icon) {
  font-size: 13px !important;
  width: 13px !important;
  height: 13px !important;
}

.ed-title {
  font-size: var(--platform-font-size-lg);
  font-weight: var(--platform-font-weight-strong);
  color: var(--platform-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: text;
  padding: 2px 4px;
  border-radius: 4px;
  border: 1px solid transparent;
  transition: border-color 0.15s;
}

.ed-title:hover {
  border-color: var(--platform-border-strong);
}

.ed-title-input {
  font-size: var(--platform-font-size-lg);
  font-weight: var(--platform-font-weight-strong);
  color: var(--platform-text);
  border: 1px solid var(--platform-accent);
  border-radius: 4px;
  padding: 2px 6px;
  outline: none;
  background: var(--platform-bg-elevated);
  width: 100%;
  max-width: 400px;
}

.ed-ext {
  font-size: var(--platform-font-size-xs);
  color: var(--platform-text-tertiary);
  flex-shrink: 0;
}

.ed-saving {
  font-size: var(--platform-font-size-xs);
  color: var(--platform-text-tertiary);
  flex-shrink: 0;
}

.ed-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--platform-border-strong);
  background: var(--platform-bg);
  flex-shrink: 0;
}

.md-btn {
  border: none;
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: var(--platform-font-size-xs);
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.md-btn:hover {
  background: var(--platform-bg-secondary);
  color: var(--platform-text);
}

.md-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.md-btn--ai {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  padding: 2px 6px;
  color: var(--platform-text-tertiary);
}

.md-btn--ai:disabled {
  opacity: 0.65;
  cursor: wait;
}

.md-btn__spin {
  animation: note-md-spin 0.8s linear infinite;
}

@keyframes note-md-spin {
  to { transform: rotate(360deg); }
}

.ed-toolbar-divider {
  width: 1px;
  height: 16px;
  background: var(--platform-border-strong);
  margin: 0 4px;
}

.ed-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.ed-textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  padding: 20px 28px;
  font-family: var(--platform-font-mono);
  font-size: var(--platform-font-size-base);
  line-height: 1.8;
  color: var(--platform-text);
  background: transparent;
}

.ed-textarea::placeholder {
  color: var(--platform-text-tertiary);
}

.ed-preview-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 20px 28px;
}

.ed-preview {
  max-width: 700px;
  margin: 0 auto;
  line-height: 1.8;
  font-size: var(--platform-font-size-lg);
  color: var(--platform-text);
}

.ed-preview :deep(h1),
.ed-preview :deep(h2),
.ed-preview :deep(h3) {
  margin-top: 1.2em;
  margin-bottom: 0.4em;
  font-weight: var(--platform-font-weight-strong);
}

.ed-preview :deep(h1) {
  font-size: 1.6em;
}

.ed-preview :deep(h2) {
  font-size: 1.3em;
}

.ed-preview :deep(h3) {
  font-size: 1.1em;
}

.ed-preview :deep(p) {
  margin: 0.6em 0;
}

.ed-preview :deep(.ed-placeholder) {
  color: var(--platform-text-tertiary);
}

.ed-preview :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  margin: 10px 0;
}

.ed-preview :deep(code) {
  background: var(--platform-bg-secondary);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.9em;
}

.ed-preview :deep(pre) {
  background: var(--platform-bg-secondary);
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
}

.ed-preview :deep(pre code) {
  background: none;
  padding: 0;
}

.ed-preview :deep(blockquote) {
  border-left: 3px solid var(--platform-accent);
  padding-left: 14px;
  margin-left: 0;
  color: var(--platform-text-secondary);
}

.ed-preview :deep(ul),
.ed-preview :deep(ol) {
  padding-left: 22px;
}

.ed-preview :deep(li) {
  margin: 0.3em 0;
}

.ed-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--platform-text-tertiary);
  text-align: center;
  padding: 40px;
}

.ed-empty-icon {
  opacity: 0.15;
  color: var(--platform-text);
}

.ed-empty h3 {
  font-size: var(--platform-font-size-xl);
  font-weight: var(--platform-font-weight-strong);
  margin: 12px 0 4px;
  color: var(--platform-text);
}

.ed-empty p {
  margin: 0;
  font-size: var(--platform-font-size-base);
}

.sb-file-list::-webkit-scrollbar,
.ed-preview-wrap::-webkit-scrollbar {
  width: 4px;
}

.sb-file-list::-webkit-scrollbar-thumb,
.ed-preview-wrap::-webkit-scrollbar-thumb {
  background: var(--platform-border-strong);
  border-radius: 2px;
}
</style>

<!-- Teleport 到顶栏的切换条（非 scoped，避免挂载后样式丢失） -->
<style>
.note-header-tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.note-header-tools .note-tabs {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  background: var(--platform-bg-secondary);
  border-radius: 8px;
}
.note-header-tools .note-tab {
  border: none;
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: var(--platform-font-size-sm, 12px);
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  line-height: 1.3;
}
.note-header-tools .note-tab:hover {
  color: var(--platform-text);
}
.note-header-tools .note-tab.active {
  background: var(--platform-bg-elevated-solid, #fff);
  color: var(--platform-text);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
</style>
