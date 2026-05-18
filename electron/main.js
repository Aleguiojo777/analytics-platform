const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const DEFAULT_PORT = 3000;
const START_TIMEOUT_MS = 30000;
let mainWindow;
let backendProcess;

function appRoot() {
  return app.isPackaged ? path.join(process.resourcesPath, 'app') : path.join(__dirname, '..');
}

function backendScriptPath() {
  return path.join(appRoot(), 'server.py');
}

function pythonCandidates() {
  const root = appRoot();
  const candidates = [];

  if (process.env.DATALENS_PYTHON) candidates.push(process.env.DATALENS_PYTHON);

  if (process.platform === 'win32') {
    candidates.push(path.join(root, '.venv', 'Scripts', 'python.exe'));
    candidates.push('py');
    candidates.push('python');
  } else {
    candidates.push(path.join(root, '.venv', 'bin', 'python'));
    candidates.push('python3');
    candidates.push('python');
  }

  return candidates;
}

function waitForServer(url, timeoutMs = START_TIMEOUT_MS) {
  const start = Date.now();

  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });

      req.on('error', () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Timed out waiting for ${url}`));
          return;
        }
        setTimeout(check, 500);
      });

      req.setTimeout(1000, () => req.destroy());
    };

    check();
  });
}

function spawnBackend(port) {
  const script = backendScriptPath();
  if (!fs.existsSync(script)) {
    throw new Error(`Missing backend script: ${script}`);
  }

  const env = {
    ...process.env,
    PORT: String(port),
    FLASK_DEBUG: '',
    CORS_ORIGINS: `http://localhost:${port},http://127.0.0.1:${port}`
  };

  const candidates = pythonCandidates();
  const errors = [];

  for (const python of candidates) {
    try {
      const args = python === 'py' ? ['-3', script] : [script];
      const child = spawn(python, args, {
        cwd: appRoot(),
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      });

      child.stdout.on('data', (data) => console.log(`[backend] ${data}`));
      child.stderr.on('data', (data) => console.error(`[backend] ${data}`));
      child.on('exit', (code, signal) => {
        if (backendProcess === child) backendProcess = null;
        console.log(`[backend] exited code=${code} signal=${signal}`);
      });

      backendProcess = child;
      return;
    } catch (error) {
      errors.push(`${python}: ${error.message}`);
    }
  }

  throw new Error(`Could not start Python backend. Tried: ${errors.join('; ')}`);
}

async function createWindow() {
  const port = Number(process.env.PORT || DEFAULT_PORT);
  const appUrl = `http://127.0.0.1:${port}`;

  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: '#0a0b0e',
    title: 'DataLens',
    icon: path.join(appRoot(), 'assets', process.platform === 'win32' ? 'datalens.ico' : 'datalens.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  try {
    spawnBackend(port);
    await waitForServer(appUrl);
    await mainWindow.loadURL(appUrl);
  } catch (error) {
    await dialog.showMessageBox(mainWindow, {
      type: 'error',
      title: 'DataLens failed to start',
      message: 'DataLens could not start the local Python backend.',
      detail: error.message
    });
    app.quit();
  }
}

app.whenReady().then(createWindow);

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
    backendProcess = null;
  }
});
