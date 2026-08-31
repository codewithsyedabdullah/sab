const { app, BrowserWindow, dialog, Tray, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const PORT = process.env.SAB_PORT || 3000;
const HOST = 'http://localhost:' + PORT;
const START_URL = HOST + '/';

let serverProc = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let isWindows = process.platform === 'win32';

// Only allow one running instance (opencode-style). A second launch just
// focuses the existing window and gets out of the way.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

function appIcon() {
  // Use the repo's existing SAB icon when available, else none.
  const ico = path.join(sabRoot(), 'static', 'icon.ico');
  return fs.existsSync(ico) ? ico : undefined;
}

// Where SAB's server + static files live.
// Dev: desktop/electron/main.js -> repo root (desktop/..).
// Packaged: shipped into resources/sab-server.
function sabRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'sab-server');
  }
  return path.join(__dirname, '..', '..');
}

function pythonPath() {
  // Allow override, else use known-good Python locations on Windows, else `python`.
  const override = (process.env.SAB_PYTHON || '').trim();
  if (override) return override;
  const candidates = ['C:\\Python314\\python.exe', 'C:\\Python313\\python.exe', 'C:\\Python312\\python.exe', 'python'];
  for (const c of candidates) {
    if (c === 'python') return 'python';
    if (fs.existsSync(c)) return c;
  }
  return 'python';
}

function serverReady() {
  return new Promise((resolve) => {
    const deadline = Date.now() + 60000;
    const probe = () => {
      if (Date.now() > deadline) return resolve(false);
      const req = http.get(START_URL + 'api/auth/status', { timeout: 1500 }, (res) => {
        res.resume();
        if (res.statusCode) return resolve(true);
      });
      req.on('error', () => setTimeout(probe, 400));
      req.setTimeout(1500, () => { req.destroy(); setTimeout(probe, 400); });
    };
    probe();
  });
}

function logPath() {
  try {
    const dir = app.getPath('userData');
    return path.join(dir, 'sab-server.log');
  } catch (e) {
    return path.join(require('os').tmpdir(), 'sab-server.log');
  }
}

function startServer() {
  const root = sabRoot();
  const serverFile = path.join(root, 'server.py');
  if (!fs.existsSync(serverFile)) {
    dialog.showErrorBox('SAB', 'Could not find server.py at ' + serverFile);
    app.quit();
    return;
  }
  const py = pythonPath();
  const log = logPath();
  fs.mkdirSync(path.dirname(log), { recursive: true });
  const logStream = fs.createWriteStream(log, { flags: 'a' });
  logStream.write('\n[' + new Date().toISOString() + '] launching: ' + py + ' -u ' + serverFile + '\n');
  serverProc = spawn(py, ['-u', serverFile], {
    cwd: root,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  serverProc.stdout.on('data', (d) => logStream.write(d));
  serverProc.stderr.on('data', (d) => logStream.write('[err] ' + d));
  serverProc.on('error', (err) => {
    logStream.write('server error: ' + err.message + '\n');
    dialog.showErrorBox('SAB', 'Failed to start server: ' + err.message);
    app.quit();
  });
  serverProc.on('exit', (code, sig) => {
    logStream.write('server exited code=' + code + ' sig=' + sig + '\n');
  });
}

function stopServer() {
  if (!serverProc || serverProc.killed) return;
  try {
    if (process.platform === 'win32') {
      // Kill the whole process tree on Windows.
      spawn('taskkill', ['/pid', String(serverProc.pid), '/t', '/f']);
    } else {
      serverProc.kill('SIGTERM');
    }
  } catch (e) {
    serverProc.kill();
  } finally {
    serverProc = null;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 820,
    minHeight: 600,
    title: 'SAB',
    icon: appIcon(),
    backgroundColor: '#282c34',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(START_URL);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Open external links in the system browser.
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('did-fail-load', () => {
    // Server not up yet — retry shortly.
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.loadURL(START_URL);
      }
    }, 1200);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  if (!isWindows || app.isPackaged === false) {
    // In dev, a tray icon can clutter the taskbar; skip it unless packaged.
    tray = null;
    return;
  }
  try {
    const ico = appIcon() || path.join(sabRoot(), 'static', 'icon.ico');
    tray = new Tray(ico);
    const menu = Menu.buildFromTemplate([
      { label: 'Open SAB', click: () => showWindow() },
      { type: 'separator' },
      { label: 'Quit SAB', click: () => { isQuitting = true; app.quit(); } },
    ]);
    tray.setToolTip('SAB');
    tray.setContextMenu(menu);
    tray.on('click', () => showWindow());
  } catch (e) {
    tray = null;
  }
}

function showWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

app.whenReady().then(async () => {
  if (isWindows && gotLock) app.setAppUserModelId('ai.sab.desktop');
  startServer();
  // Show the window immediately; it will retry loading until the server is up.
  createWindow();
  createTray();
  const ok = await serverReady();
  if (!ok) {
    dialog.showErrorBox('SAB', 'The SAB server did not start in time.\nSee ' + logPath());
    app.quit();
    return;
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(START_URL);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  stopServer();
});

app.on('window-all-closed', () => {
  // On Windows, a proper desktop app keeps running in the tray when the
  // window is dismissed, and only fully exits via Quit.
  if (isWindows && !isQuitting) return;
  app.quit();
});
