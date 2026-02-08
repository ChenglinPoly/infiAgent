const fs = require('fs');
const path = require('path');

function rmrf(p) {
  try {
    if (fs.existsSync(p)) fs.rmSync(p, { recursive: true, force: true });
  } catch (_) {}
}

module.exports = async function afterPack(context) {
  // Goal: avoid @electron/universal merge conflicts by making each arch build
  // contain ONLY its own backend directory. Universal merge will then include both.
  //
  // In extraResources we copy:
  //   python-backend/darwin-arm64/**
  //   python-backend/darwin-x64/**
  //
  // Here we delete the opposite arch dir from each temp app before universal merge.
  if (context.electronPlatformName !== 'darwin') return;

  const appOutDir = context.appOutDir;
  const entries = fs.readdirSync(appOutDir);
  const appName = entries.find((e) => e.endsWith('.app'));
  if (!appName) return;

  const resourcesDir = path.join(appOutDir, appName, 'Contents', 'Resources');
  const backendRoot = path.join(resourcesDir, 'python-backend');

  // context.arch: 0=x64, 1=arm64
  const arch = context.arch;
  const isArm64 = arch === 1;
  const isX64 = arch === 0;

  if (isArm64) {
    rmrf(path.join(backendRoot, 'darwin-x64'));
  } else if (isX64) {
    rmrf(path.join(backendRoot, 'darwin-arm64'));
  }
};

