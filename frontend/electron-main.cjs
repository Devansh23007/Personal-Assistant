const { app, BrowserWindow, dialog, ipcMain, screen, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');

let mainWindow;
let backendProcess;
let backendPort;

function reserveLocalPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close((error) => {
        if (error) reject(error);
        else resolve(port);
      });
    });
  });
}

function waitForBackend(port, child, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    let startupError;
    let ready = false;

    child.once('error', (error) => {
      startupError = error;
    });
    child.once('exit', (code) => {
      if (!ready) {
        startupError = new Error(`Backend exited before becoming ready (code ${code}).`);
      }
    });

    const check = () => {
      if (startupError) {
        reject(startupError);
        return;
      }
      if (Date.now() >= deadline) {
        reject(new Error('Backend did not become healthy within 30 seconds.'));
        return;
      }

      const request = http.get(
        { hostname: '127.0.0.1', port, path: '/api/health', timeout: 1000 },
        (response) => {
          response.resume();
          if (response.statusCode === 200) {
            ready = true;
            resolve();
          } else {
            setTimeout(check, 250);
          }
        },
      );
      request.on('error', () => setTimeout(check, 250));
      request.on('timeout', () => request.destroy());
    };

    check();
  });
}

async function startBackend() {
  const backendPython = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
  const backendDir = path.join(__dirname, '..', 'backend');
  backendPort = await reserveLocalPort();

  backendProcess = spawn(backendPython, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], {
    cwd: backendDir,
    stdio: 'ignore',
    detached: false,
  });
  await waitForBackend(backendPort, backendProcess);
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
    // Keep the desktop assistant as an overlay widget only; don't create a
    // separate taskbar button or Alt+Tab app window for the collapsed widget.
    skipTaskbar: true,
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
    mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`).catch(() => {
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

  startBackend()
    .then(createWindow)
    .catch((error) => {
      console.error('Failed to start the V.I.P.E.R. backend:', error);
      dialog.showErrorBox(
        'V.I.P.E.R. could not start',
        `The app could not start its own backend. Close older V.I.P.E.R. instances and try again.\n\n${error.message}`,
      );
      app.quit();
    });

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
