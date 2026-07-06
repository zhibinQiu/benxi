const STAGES = Object.freeze({
  NAVIGATE: 'navigate',
  AUTH_CHECK: 'auth_check',
  QUOTA_CHECK: 'quota_check',
  OVERLAY_CHECK: 'overlay_check',
  PRE_EDITOR: 'pre_editor',
  EDITOR_FIND: 'editor_find',
  INPUT: 'input',
  SEND: 'send',
  WAIT_RESPONSE: 'wait_response',
  EXTRACT: 'extract',
  IMAGE_UPLOAD: 'image_upload',
  IMAGE_GEN: 'image_gen',
});

const REASONS = Object.freeze({
  QUOTA: 'quota',
  AUTH: 'auth',
  ERROR: 'error',
  TIMEOUT: 'timeout',
  SAFETY: 'safety',
});

class ProviderError extends Error {
  constructor(cause, opts = {}) {
    const message = typeof cause === 'string' ? cause : (cause.message || '未知错误');
    super(message);
    this.name = 'ProviderError';
    this.originalName = (cause && cause.name) || 'Error';
    this.originalStack = (cause && cause.stack) || '';
    this.code = (cause && cause.code) || null;
    this.stage = opts.stage || 'unknown';
    this.provider = opts.provider || 'unknown';
    this.reason = opts.reason || REASONS.ERROR;
  }

  toResult() {
    return {
      success: false,
      reason: this.reason,
      error_details: {
        name: this.originalName,
        message: this.message,
        code: this.code,
        stage: this.stage,
        provider: this.provider,
      },
    };
  }
}

function classifyError(err, stage, provider, reason) {
  const pe = new ProviderError(err, { stage, provider, reason });
  return pe.toResult();
}

module.exports = { ProviderError, classifyError, STAGES, REASONS };
