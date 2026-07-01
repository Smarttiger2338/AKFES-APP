const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("AKFES_CONFIG", {
    SERVER_URL: process.env.AKFES_SERVER_URL || "http://127.0.0.1:5000"
});
