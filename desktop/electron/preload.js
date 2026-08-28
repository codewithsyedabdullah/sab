const { contextBridge, ipcRenderer } = require('electron');

// Minimal, safe bridge. SAB is a normal web app; most of it needs nothing
// extra. Expose read-only server facts for future use without opening any
// node capability to the renderer.
contextBridge.exposeInMainWorld('sabDesktop', {
  platform: process.platform,
});
