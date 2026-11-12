const { app, BrowserWindow, ipcMain, screen, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let backendProcess;

function startBackend() {
  const backendPython = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
  const backendDir = path.join(__dirname, '..', 'backend');

  try {
    backendProcess = spawn(backendPython, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], {
      cwd: backendDir,
      stdio: 'ignore',
      detached: false,
    });
  } catch (err) {
    console.error('Failed to spawn backend:', err);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 100,
    height: 100,
    minWidth: 64,
    minHeight: 64,
    backgroundColor: '#00000000',
    transparent: true,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    hasShadow: false,
    show: false,
    title: 'V.I.P.E.R. - Virtual Intelligent Personal Electronic Respondent',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'electron-preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  positionWidget(false);

  const loadApp = () => {
    mainWindow.loadURL('http://127.0.0.1:8000/').catch(() => {
      setTimeout(loadApp, 500);
    });
  };

  loadApp();

  mainWindow.once('ready-to-show', () => mainWindow?.show());

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function positionWidget(expanded) {
  if (!mainWindow) return;
  const display = screen.getDisplayMatching(mainWindow.getBounds());
  const { x: areaX, y: areaY, width: areaWidth, height: areaHeight } = display.workArea;
  const width = expanded ? Math.min(920, areaWidth - 24) : 100;
  const height = expanded ? Math.min(660, areaHeight - 24) : 100;
  mainWindow.setMinimumSize(expanded ? 600 : 64, expanded ? 440 : 64);
  mainWindow.setResizable(expanded);
  mainWindow.setBounds({
    x: areaX + areaWidth - width - 12,
    y: areaY + areaHeight - height - 12,
    width,
    height,
  }, false);
  mainWindow.setAlwaysOnTop(true, 'floating');
}

app.whenReady().then(() => {
  // Explicitly grant microphone permissions in Electron
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (permission === 'media') {
      return callback(true);
    }
    callback(false);
  });

  session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
    if (permission === 'media') {
      return true;
    }
    return false;
  });

  ipcMain.handle('viper-widget:set-expanded', (_event, expanded) => {
    positionWidget(Boolean(expanded));
  });

  startBackend();
  setTimeout(createWindow, 800);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    try {
      backendProcess.kill();
    } catch {}
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (backendProcess) {
    try {
      backendProcess.kill();
    } catch {}
  }
});
