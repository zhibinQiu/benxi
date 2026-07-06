const IS_TTY = Boolean(process.stderr.isTTY);

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

function log(prefix, msg) {
  if (IS_TTY) process.stderr.write('\r\x1b[K');
  const ts = new Date().toISOString().slice(11, 19);
  process.stderr.write(`[${ts}][${prefix}] ${msg}\n`);
}

function startTimer(prefix, label) {
  if (!IS_TTY) return { stop() {} };
  const startTime = Date.now();
  let i = 0;
  const interval = setInterval(() => {
    const elapsedSec = Math.floor((Date.now() - startTime) / 1000);
    const mins = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
    const secs = String(elapsedSec % 60).padStart(2, '0');
    process.stderr.write(`\r[${prefix}] ${SPINNER_FRAMES[i]} ${label} (${mins}:${secs})`);
    i = (i + 1) % SPINNER_FRAMES.length;
  }, 100);
  return {
    stop() {
      clearInterval(interval);
      process.stderr.write('\r\x1b[K');
    }
  };
}

function spinner(ch) {
  if (IS_TTY) process.stderr.write(ch);
}

module.exports = { log, startTimer, spinner };
