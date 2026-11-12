const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('viperDesktop', {
  setExpanded: (expanded) => ipcRenderer.invoke('viper-widget:set-expanded', Boolean(expanded)),
});
