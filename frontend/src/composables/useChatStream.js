import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import {
  mergeAuthScreenshotMarkdownBlocks,
  normalizeChatAttachmentUrl,
} from "../utils/authenticatedImage.js";
import { handleAgentWorkflowForNotifications } from "./useNotificationAlerts.js";
import {
  emptyAgentWorkflow,
  applyAgentWorkflowEvent,
  finalizeWorkflowProcess,
  getWorkflowLastError,
} from "../utils/agentWorkflow.js";

/**
 * SSE 流式发送、中止、思考计时与消息队列。
 */
export function useChatStream({
  props,
  ui,
  t,
  messages,
  input,
  conversationId,
  started,
  attachmentSessionId,
  selectedModelProviderId,
  buildChatHistory,
  scrollToBottom,
  reportChatState,
  persistSessionState,
  syncMessageScreenshots,
}) {
  const sending = ref(false);
  const resumingCheckpoint = ref(null);
  const messageQueue = ref([]);
  const thinkingStartTime = ref(0);
  const elapsedMs = ref(0);

  let queueSeq = 0;
  let streamAbort = null;
  let streamGeneration = 0;
  let thinkingTimer = null;
  const streamedScreenshotBlocks = [];

  const queueEnabled = computed(() => props.chatScope === "ai-home");

  function emptyWorkflow() {
    return emptyAgentWorkflow();
  }

  function applyWorkflowEvent(workflow, ev) {
    return applyAgentWorkflowEvent(workflow, ev);
  }

  function formatElapsed(ms) {
    const totalSec = Math.floor(ms / 1000);
    if (totalSec < 60) return `已处理 ${totalSec} 秒`;
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `已处理 ${min} 分 ${sec} 秒`;
  }

  function stopThinkingTimer() {
    if (thinkingTimer) {
      clearInterval(thinkingTimer);
      thinkingTimer = null;
    }
  }

  function startThinkingTimer() {
    thinkingStartTime.value = Date.now();
    elapsedMs.value = 0;
    thinkingTimer = setInterval(() => {
      elapsedMs.value = Date.now() - thinkingStartTime.value;
    }, 200);
  }

  function resumeThinkingTimerIfSending() {
    if (sending.value && props.chatScope === "ai-home" && !thinkingTimer) {
      thinkingStartTime.value = Date.now() - elapsedMs.value;
      thinkingTimer = setInterval(() => {
        elapsedMs.value = Date.now() - thinkingStartTime.value;
      }, 200);
    }
  }

  watch(sending, (val) => {
    if (val && props.chatScope === "ai-home") {
      startThinkingTimer();
    } else {
      stopThinkingTimer();
    }
  });

  onDeactivated(() => {
    stopThinkingTimer();
  });

  onActivated(() => {
    resumeThinkingTimerIfSending();
  });

  onBeforeUnmount(() => {
    stopThinkingTimer();
    if (sending.value) {
      streamGeneration += 1;
    }
  });

  function clearFollowUpQuestions() {
    for (const msg of messages.value) {
      if (msg.followUpQuestions) delete msg.followUpQuestions;
    }
  }

  function stripFollowUpMarkdown(text) {
    return String(text || "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/[*_~]+/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function applyFollowUpQuestions(row, questions) {
    if (props.chatScope !== "ai-home" || !row) return;
    if (!Array.isArray(questions) || !questions.length) return;
    row.followUpQuestions = questions
      .map((q) => stripFollowUpMarkdown(q))
      .filter((q) => q.length >= 4);
  }

  function enqueueMessage(text) {
    const content = String(text || "").trim();
    if (!content) return false;
    queueSeq += 1;
    messageQueue.value.push({
      id: `q-${Date.now()}-${queueSeq}`,
      text: content,
    });
    return true;
  }

  function removeQueuedMessage(id) {
    messageQueue.value = messageQueue.value.filter((item) => item.id !== id);
  }

  function updateQueuedMessage(id, text) {
    const item = messageQueue.value.find((q) => q.id === id);
    if (!item) return;
    item.text = String(text || "");
  }

  async function drainMessageQueue() {
    if (!queueEnabled.value || sending.value) return;
    while (messageQueue.value.length) {
      const next = messageQueue.value.shift();
      const content = String(next?.text || "").trim();
      if (!content) continue;
      await dispatchMessage(content);
      return;
    }
  }

  function showFollowUpForMessage(index, message) {
    if (props.chatScope !== "ai-home") return false;
    if (message?.role !== "assistant" || message.streaming || message.error) return false;
    if (!Array.isArray(message.followUpQuestions) || !message.followUpQuestions.length) {
      return false;
    }
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i]?.role === "assistant") {
        return i === index;
      }
    }
    return false;
  }

  function useFollowUpQuestion(text) {
    const q = stripFollowUpMarkdown(text);
    if (!q) return;
    if (sending.value && queueEnabled.value) {
      enqueueMessage(q);
      return;
    }
    if (sending.value) return;
    void dispatchMessage(q);
  }

  function applyScreenshotAttachments(row, attachments) {
    if (!row || !Array.isArray(attachments)) return;
    if (!row.browserScreenshots) row.browserScreenshots = [];
    for (const att of attachments) {
      if (att?.type !== "image" || !att.url) continue;
      const src = normalizeChatAttachmentUrl(att.url);
      if (!src) continue;
      const title = att.title || "浏览器截图";
      const block = `![${title}](${src})`;
      if (!streamedScreenshotBlocks.includes(block)) {
        streamedScreenshotBlocks.push(block);
      }
      if (!row.browserScreenshots.some((shot) => shot.url === src)) {
        row.browserScreenshots.push({ url: src, title });
      }
    }
    row.content = mergeAuthScreenshotMarkdownBlocks(
      row.content || "",
      streamedScreenshotBlocks
    );
  }

  function mergeScreenshotBlocksIntoContent(text) {
    return mergeAuthScreenshotMarkdownBlocks(text, streamedScreenshotBlocks);
  }

  function finalizeStoppedAssistant(assistantIdx) {
    const row = messages.value[assistantIdx];
    if (!row || row.role !== "assistant") return;
    row.streaming = false;
    if (row.workflow) finalizeWorkflowProcess(row.workflow);
    if (!row.content.trim()) {
      row.content = t("chat.stoppedGeneration");
    }
  }

  async function sendMessageStreaming(content, assistantIdx, history) {
    streamAbort?.abort();
    streamAbort = new AbortController();

    let scrollTick = 0;
    const typewriterActive = false;
    streamedScreenshotBlocks.length = 0;

    try {
      await props.streamChat(
        {
          message: content,
          history,
          conversationId: conversationId.value,
          attachmentSessionId: attachmentSessionId.value,
          model_provider_id: selectedModelProviderId.value || undefined,
        },
        {
          signal: streamAbort.signal,
          onWorkflow: (ev) => {
            handleAgentWorkflowForNotifications(ev);
            if (!props.showWorkflowProgress) return;
            const row = messages.value[assistantIdx];
            if (!row) return;
            if (!row.workflow) row.workflow = emptyWorkflow();
            applyWorkflowEvent(row.workflow, ev);
            scrollTick += 1;
            if (scrollTick % 2 === 0) scrollToBottom();
          },
          onReplace: (text) => {
            const row = messages.value[assistantIdx];
            if (!row) return;
            const formatted = mergeScreenshotBlocksIntoContent(text);
            row.content = formatted;
            syncMessageScreenshots(row);
            scrollToBottom();
          },
          onCitations: (citations) => {
            if ((!props.showCitations && !props.showReportTools) || !Array.isArray(citations)) return;
            const row = messages.value[assistantIdx];
            if (row) row.citations = citations;
          },
          onAttachments: (attachments) => {
            const row = messages.value[assistantIdx];
            applyScreenshotAttachments(row, attachments);
            scrollToBottom();
          },
          onDelta: (delta) => {
            const row = messages.value[assistantIdx];
            if (!row) return;
            row.content += delta;
            syncMessageScreenshots(row);
            scrollTick += 1;
            if (scrollTick % 4 === 0) scrollToBottom();
          },
          onError: (err) => {
            const row = messages.value[assistantIdx];
            if (row?.content?.trim()) {
              row.streaming = false;
              if (row.workflow) {
                finalizeWorkflowProcess(row.workflow);
              }
              return;
            }
            if (row) {
              row.streaming = false;
              const wfErr = row.workflow ? getWorkflowLastError(row.workflow) : "";
              if (!wfErr) {
                row.error = true;
              }
              row.content = err?.message?.trim() || wfErr || t("chat.sorryRetry");
              if (row.workflow) {
                finalizeWorkflowProcess(row.workflow);
              }
            }
            ui.error(err?.message || t("chat.sendFailed"));
          },
          onDone: (payload) => {
            if (
              !payload?.done &&
              !String(payload?.reply || "").trim() &&
              !(Array.isArray(payload?.attachments) && payload.attachments.length) &&
              !payload?.conversation_id
            ) {
              return;
            }
            const row = messages.value[assistantIdx];
            if (row) {
              applyScreenshotAttachments(row, payload?.attachments);
              if (payload?.suspended) {
                row.streaming = false;
                row.suspended = true;
                row.checkpointId = payload.checkpoint_id || null;
              } else if (!typewriterActive) {
                const merged = mergeScreenshotBlocksIntoContent(
                  payload?.reply || row.content || ""
                );
                if (merged) {
                  row.content = merged;
                }
                row.streaming = false;
              }
              syncMessageScreenshots(row);
              if (row.workflow) {
                finalizeWorkflowProcess(row.workflow);
              }
              if (props.showCitations || props.showReportTools) {
                if (Array.isArray(payload?.citations)) {
                  row.citations = payload.citations;
                }
              }
              applyFollowUpQuestions(row, payload?.follow_up_questions);
            }
            if (payload?.conversation_id) {
              conversationId.value = payload.conversation_id;
            }
            sending.value = false;
            reportChatState();
          },
          onFollowUpQuestions: (questions) => {
            const row = messages.value[assistantIdx];
            applyFollowUpQuestions(row, questions);
          },
          onConversationId: (id) => {
            if (id) conversationId.value = id;
          },
        }
      );
      const row = messages.value[assistantIdx];
      if (row && !typewriterActive) {
        row.streaming = false;
        if (row.workflow) {
          finalizeWorkflowProcess(row.workflow);
        }
        if (!row.content.trim()) {
          row.content = "";
        }
      }
    } catch (e) {
      if (e?.name === "AbortError") {
        finalizeStoppedAssistant(assistantIdx);
        return;
      }
      throw e;
    }
  }

  function stopGeneration() {
    if (!sending.value) return;
    streamGeneration += 1;
    const assistantIdx = messages.value.length - 1;
    streamAbort?.abort();
    finalizeStoppedAssistant(assistantIdx);
    sending.value = false;
    streamAbort = null;
    void drainMessageQueue();
  }

  async function revealContentTypewriter(row, fullText) {
    const text = (fullText || "").trim();
    if (!text) {
      row.streaming = false;
      row.content = "";
      return;
    }
    row.content = "";
    row.streaming = true;
    const step = Math.max(1, Math.floor(text.length / 100));
    for (let i = 0; i < text.length; i += step) {
      row.content = text.slice(0, Math.min(i + step, text.length));
      if (i % (step * 4) === 0) await scrollToBottom();
      await new Promise((r) => setTimeout(r, 14));
    }
    row.content = text;
    row.streaming = false;
  }

  async function resumeCheckpoint(checkpointId, assistantIdx, accepted) {
    const { resumeCheckpointStream } = await import("../api/rag.js");
    resumingCheckpoint.value = checkpointId;
    const row = messages.value[assistantIdx];
    if (row) {
      row.streaming = true;
      row.suspended = false;
    }

    try {
      await resumeCheckpointStream(checkpointId, { accepted })(
        {
          onDelta: (delta) => {
            if (row) row.content += delta;
          },
          onReplace: (text) => {
            if (row) row.content = text;
          },
          onWorkflow: (ev) => {
            if (!row) return;
            if (!row.workflow) row.workflow = emptyWorkflow();
            applyWorkflowEvent(row.workflow, ev);
          },
          onCitations: (citations) => {
            if (row && (props.showCitations || props.showReportTools)) {
              row.citations = citations;
            }
          },
          onAttachments: (attachments) => {
            if (row) applyScreenshotAttachments(row, attachments);
          },
          onFollowUpQuestions: (questions) => {
            if (row) applyFollowUpQuestions(row, questions);
          },
          onConversationId: (id) => {
            if (id) conversationId.value = id;
          },
          onError: (err) => {
            if (row) {
              row.streaming = false;
              if (!row.content.trim()) row.error = true;
            }
            ui.error(err?.message || "恢复执行失败");
          },
          onDone: (payload) => {
            if (row) {
              if (payload?.reply) {
                row.content = payload.reply;
              }
              row.streaming = false;
              if (row.workflow) finalizeWorkflowProcess(row.workflow);
              row.suspended = false;
              row.checkpointId = null;
            }
            if (payload?.conversation_id) conversationId.value = payload.conversation_id;
            reportChatState();
          },
        }
      );
    } catch (err) {
      if (row) {
        row.streaming = false;
        row.suspended = false;
      }
      ui.error(err?.message || "恢复执行失败");
    } finally {
      resumingCheckpoint.value = null;
    }
  }

  async function resumeCheckpointWithChoice(checkpointId, assistantIdx, choice) {
    resumingCheckpoint.value = checkpointId;
    const row = messages.value[assistantIdx];
    if (row) {
      row.streaming = true;
      row.suspended = false;
    }

    try {
      const { resumeCheckpointStream } = await import("../api/rag.js");
      await resumeCheckpointStream(checkpointId, { choice })(
        {
          onDelta: (delta) => { if (row) row.content += delta; },
          onReplace: (text) => { if (row) row.content = text; },
          onWorkflow: (ev) => {
            if (!row) return;
            if (!row.workflow) row.workflow = emptyWorkflow();
            applyWorkflowEvent(row.workflow, ev);
          },
          onCitations: (citations) => { if (row && props.showCitations) row.citations = citations; },
          onAttachments: (attachments) => { if (row) applyScreenshotAttachments(row, attachments); },
          onFollowUpQuestions: (questions) => { if (row) applyFollowUpQuestions(row, questions); },
          onConversationId: (id) => { if (id) conversationId.value = id; },
          onError: (err) => {
            if (row) { row.streaming = false; if (!row.content.trim()) row.error = true; }
            ui.error(err?.message || "恢复执行失败");
          },
          onDone: (payload) => {
            if (row) {
              if (payload?.reply) row.content = payload.reply;
              row.streaming = false;
              if (row.workflow) finalizeWorkflowProcess(row.workflow);
              row.suspended = false;
              row.checkpointId = null;
            }
            if (payload?.conversation_id) conversationId.value = payload.conversation_id;
            reportChatState();
          },
        }
      );
    } catch (err) {
      if (row) { row.streaming = false; row.suspended = false; }
      ui.error(err?.message || "恢复执行失败");
    } finally {
      resumingCheckpoint.value = null;
    }
  }

  async function sendMessageBlocking(content, assistantIdx, history) {
    messages.value.push({ role: "assistant", content: "", streaming: true });
    await scrollToBottom();

    const data = await props.chatSend({
      message: content,
      history,
      conversationId: conversationId.value,
      model_provider_id: selectedModelProviderId.value || undefined,
    });

    const row = messages.value[assistantIdx];
    if (row) {
      const reply = (data?.reply || "").trim();
      if (props.showCitations && Array.isArray(data?.citations)) {
        row.citations = data.citations;
      }
      if (data?.conversation_id) {
        conversationId.value = data.conversation_id;
      }
      if (reply) {
        await revealContentTypewriter(row, reply);
      } else {
        row.streaming = false;
        row.content = "";
      }
      applyFollowUpQuestions(row, data?.follow_up_questions);
    }
  }

  async function dispatchMessage(content) {
    const text = String(content || "").trim();
    if (!text) return;

    if (props.streaming && !props.streamChat) {
      ui.error(t("chat.streamNotConfigured"));
      return;
    }
    if (!props.streaming && !props.chatSend) {
      ui.error(t("chat.chatNotConfigured"));
      return;
    }

    const generation = ++streamGeneration;
    const firstTurn = !started.value;
    if (firstTurn) started.value = true;

    clearFollowUpQuestions();

    const history = buildChatHistory();
    messages.value.push({ role: "user", content: text });
    sending.value = true;

    if (firstTurn) {
      await nextTick();
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    }
    await scrollToBottom();

    const assistantIdx = messages.value.length;

    try {
      if (props.streaming) {
        messages.value.push({
          role: "assistant",
          content: "",
          streaming: true,
          workflow: props.showWorkflowProgress
            ? {
                ...emptyWorkflow(),
                running: true,
                currentTitle: t("chat.thinking"),
              }
            : null,
        });
        await scrollToBottom();
        await sendMessageStreaming(text, assistantIdx, history);
      } else {
        await sendMessageBlocking(text, assistantIdx, history);
      }
    } catch (e) {
      if (e?.name === "AbortError") {
        finalizeStoppedAssistant(assistantIdx);
        return;
      }
      ui.error(e.message || t("chat.sendFailed"));
      const row = messages.value[assistantIdx];
      if (row) {
        row.streaming = false;
        row.error = true;
        if (!row.content.trim()) {
          row.content = e.message?.trim() || t("chat.sorryRetry");
        }
      } else {
        messages.value.push({
          role: "assistant",
          content: t("chat.sorryRetry"),
          error: true,
        });
      }
    } finally {
      if (generation === streamGeneration) {
        sending.value = false;
        streamAbort = null;
      }
      await scrollToBottom();
      persistSessionState({ immediate: true });
      if (generation === streamGeneration) {
        await drainMessageQueue();
      }
    }
  }

  async function sendMessage(text) {
    const content = (text ?? input.value).trim();
    if (!content) return;

    if (sending.value && queueEnabled.value) {
      if (enqueueMessage(content)) {
        input.value = "";
      }
      return;
    }
    if (sending.value) return;

    input.value = "";
    await dispatchMessage(content);
  }

  function onComposerKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function abortActiveStream() {
    streamAbort?.abort();
  }

  function resetStreamControl() {
    streamAbort = null;
    sending.value = false;
  }

  function bumpStreamGeneration() {
    streamGeneration += 1;
  }

  function clearMessageQueue() {
    messageQueue.value = [];
  }

  async function retryFromUserMessage(index) {
    const message = messages.value[index];
    if (!message || message.role !== "user") return false;

    const content = (message.content || "").trim();
    if (!content) return false;

    abortActiveStream();
    bumpStreamGeneration();
    const lastIdx = messages.value.length - 1;
    const last = messages.value[lastIdx];
    if (last?.role === "assistant" && (last.streaming || sending.value)) {
      finalizeStoppedAssistant(lastIdx);
    }
    resetStreamControl();

    messages.value = messages.value.slice(0, index);
    if (!messages.value.length) {
      started.value = false;
    }

    await sendMessage(content);
    return true;
  }

  return {
    sending,
    resumingCheckpoint,
    messageQueue,
    thinkingStartTime,
    elapsedMs,
    queueEnabled,
    formatElapsed,
    enqueueMessage,
    removeQueuedMessage,
    updateQueuedMessage,
    drainMessageQueue,
    showFollowUpForMessage,
    useFollowUpQuestion,
    sendMessage,
    dispatchMessage,
    stopGeneration,
    onComposerKeydown,
    resumeCheckpoint,
    resumeCheckpointWithChoice,
    abortActiveStream,
    resetStreamControl,
    bumpStreamGeneration,
    clearMessageQueue,
    retryFromUserMessage,
    finalizeStoppedAssistant,
  };
}
