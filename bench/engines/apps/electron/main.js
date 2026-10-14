// Loads $BENCH_DIR/$BENCH_PAGE in a 1280x720 window and forwards the page's console to stdout.
// Always on top and unthrottled, as the other windowed hosts: a covered window gets no frames.
const { app, BrowserWindow } = require('electron');
const path = require('path');
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 1280, height: 720, useContentSize: true, alwaysOnTop: true,
    webPreferences: { backgroundThrottling: false } });
  win.webContents.on('console-message', (e) => { process.stdout.write(String(e.message) + '\n'); });
  win.loadFile(path.join(process.env.BENCH_DIR, process.env.BENCH_PAGE || 'bench.html'));
});
app.on('window-all-closed', () => app.quit());
