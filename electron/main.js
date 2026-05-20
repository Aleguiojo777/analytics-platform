const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const DEFAULT_PORT = 3000;
const START_TIMEOUT_MS = 30000;
const DEPENDENCY_STAMP = '.datalens-dependencies';
let mainWindow;
let backendProcess;
let backendOutput = [];

function appendBackendOutput(data) {
  const text = data.toString().trim();
  if (!text) return;

  backendOutput.push(text);
  backendOutput = backendOutput.slice(-12);
}

function appRoot() {
  return app.isPackaged ? path.join(process.resourcesPath, 'app') : path.join(__dirname, '..');
}

function pythonEnvironmentRoot() {
  return app.isPackaged ? app.getPath('userData') : appRoot();
}

function backendScriptPath() {
  return path.join(appRoot(), 'server.py');
}

function localPythonPath() {
  const root = pythonEnvironmentRoot();
  return process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
}

function runCommand(command, args, options = {}) {
  const { cwd = appRoot(), ...spawnOptions } = options;
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    windowsHide: true,
    ...spawnOptions
  });

  if (result.stdout) appendBackendOutput(result.stdout);
  if (result.stderr) appendBackendOutput(result.stderr);

  if (result.error) throw result.error;
  if (result.status !== 0) {
    const detail = [result.stdout, result.stderr].filter(Boolean).join('\n').trim();
    throw new Error(`${command} ${args.join(' ')} failed${detail ? `\n${detail}` : ''}`);
  }
}

function requirementsStampPath() {
  return path.join(pythonEnvironmentRoot(), '.venv', DEPENDENCY_STAMP);
}

function dependenciesAreCurrent(requirementsPath, stampPath) {
  if (!fs.existsSync(requirementsPath) || !fs.existsSync(stampPath)) return false;

  const requirementsTime = fs.statSync(requirementsPath).mtimeMs;
  const stampTime = fs.statSync(stampPath).mtimeMs;
  return stampTime >= requirementsTime;
}

function pythonBootstrapCandidates() {
  if (process.env.DATALENS_PYTHON) return [process.env.DATALENS_PYTHON];
  return process.platform === 'win32' ? ['py', 'python'] : ['python3', 'python'];
}

function createVirtualEnvironment(venvPython) {
  if (fs.existsSync(venvPython)) return;

  fs.mkdirSync(pythonEnvironmentRoot(), { recursive: true });

  const errors = [];
  for (const python of pythonBootstrapCandidates()) {
    try {
      const args = python === 'py' ? ['-3', '-m', 'venv', '.venv'] : ['-m', 'venv', '.venv'];
      runCommand(python, args, { cwd: pythonEnvironmentRoot() });
      if (fs.existsSync(venvPython)) return;
    } catch (error) {
      errors.push(`${python}: ${error.message}`);
    }
  }

  throw new Error(`Could not create a Python virtual environment. Tried: ${errors.join('; ')}`);
}

function ensurePythonEnvironment() {
  const requirementsPath = path.join(appRoot(), 'requirements.txt');
  const venvPython = localPythonPath();

  createVirtualEnvironment(venvPython);

  const stampPath = requirementsStampPath();
  if (process.env.DATALENS_SKIP_PIP === '1' || dependenciesAreCurrent(requirementsPath, stampPath)) {
    return venvPython;
  }

  runCommand(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip']);
  runCommand(venvPython, ['-m', 'pip', 'install', '-r', requirementsPath]);

  fs.writeFileSync(stampPath, new Date().toISOString(), 'utf8');
  return venvPython;
}

function pythonCandidates() {
  const candidates = [];

  if (process.env.DATALENS_PYTHON) candidates.push(process.env.DATALENS_PYTHON);

  const localPython = localPythonPath();
  if (fs.existsSync(localPython)) candidates.push(localPython);

  if (process.platform === 'win32') candidates.push('py', 'python');
  else candidates.push('python3', 'python');

  return [...new Set(candidates)];
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

function spawnCandidate(python, script, env) {
  return new Promise((resolve, reject) => {
    const args = python === 'py' ? ['-3', script] : [script];
    const child = spawn(python, args, {
      cwd: appRoot(),
      env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let settled = false;

    child.stdout.on('data', (data) => {
      appendBackendOutput(data);
      console.log(`[backend] ${data}`);
    });
    child.stderr.on('data', (data) => {
      appendBackendOutput(data);
      console.error(`[backend] ${data}`);
    });

    child.once('spawn', () => {
      settled = true;
      backendProcess = child;
      resolve(child);
    });

    child.once('error', (error) => {
      if (!settled) {
        reject(error);
        return;
      }

      appendBackendOutput(error.message);
      console.error(`[backend] ${error.message}`);
    });

    child.on('exit', (code, signal) => {
      if (backendProcess === child) backendProcess = null;
      console.log(`[backend] exited code=${code} signal=${signal}`);
    });
  });
}

async function spawnBackend(port) {
  const script = backendScriptPath();
  if (!fs.existsSync(script)) {
    throw new Error(`Missing backend script: ${script}`);
  }

  const env = {
    ...process.env,
    PORT: String(port),
    FLASK_DEBUG: '',
    CORS_ORIGINS: `http://localhost:${port},http://127.0.0.1:${port},null`
  };

  const errors = [];
  backendOutput = [];

  try {
    ensurePythonEnvironment();
  } catch (error) {
    appendBackendOutput(error.message);
  }

  const candidates = pythonCandidates();
  for (const python of candidates) {
    try {
      await spawnCandidate(python, script, env);
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
    await spawnBackend(port);
    await waitForServer(appUrl);
    await mainWindow.loadURL(appUrl);
  } catch (error) {
    const output = backendOutput.length ? `\n\nBackend output:\n${backendOutput.join('\n')}` : '';
    await dialog.showMessageBox(mainWindow, {
      type: 'error',
      title: 'DataLens failed to start',
      message: 'DataLens could not start the local Python backend.',
      detail: `${error.message}${output}`
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
