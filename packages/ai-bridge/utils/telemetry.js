const fs = require('fs');
const path = require('path');

const MAX_TELEMETRY_BYTES = 10 * 1024 * 1024;
const MAX_ROTATIONS = 3;

function appendWithRotation(filePath, line) {
  try { fs.mkdirSync(path.dirname(filePath), { recursive: true }); } catch (_) {}
  try {
    if (fs.existsSync(filePath) && fs.statSync(filePath).size > MAX_TELEMETRY_BYTES) {
      for (let i = MAX_ROTATIONS; i >= 1; i--) {
        const oldPath = i === 1 ? filePath : `${filePath}.${i - 1}`;
        const newPath = `${filePath}.${i}`;
        try { if (fs.existsSync(oldPath)) fs.renameSync(oldPath, newPath); } catch (_) {}
      }
    }
  } catch (_) {}
  try {
    fs.appendFileSync(filePath, line);
  } catch (_) {}
}

module.exports = { appendWithRotation };
