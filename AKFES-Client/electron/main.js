const { app, BrowserWindow, session, dialog, shell } = require("electron");
const path = require("path");

const SERVER_URL = process.env.AKFES_SERVER_URL || "http://127.0.0.1:5000";

let mainWindow = null;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1100,
        height: 780,
        minWidth: 920,
        minHeight: 650,
        title: "AKFES",
        backgroundColor: "#0b0f14",
        show: false,
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
            devTools: false,
            webSecurity: true,
            enableBlinkFeatures: "Serial"
        }
    });

    mainWindow.removeMenu();

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        if (url.startsWith("https://") || url.startsWith("http://")) {
            shell.openExternal(url);
        }

        return { action: "deny" };
    });

    mainWindow.webContents.on("will-navigate", (event, url) => {
        const currentUrl = mainWindow.webContents.getURL();

        if (url !== currentUrl && (url.startsWith("https://") || url.startsWith("http://"))) {
            event.preventDefault();
            shell.openExternal(url);
        }
    });

    session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
        return permission === "serial";
    });

    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
        callback(permission === "serial");
    });

    session.defaultSession.setDevicePermissionHandler((details) => {
        return details.deviceType === "serial";
    });

    session.defaultSession.on("select-serial-port", async (event, portList, webContents, callback) => {
        event.preventDefault();

        if (!portList || portList.length === 0) {
            dialog.showMessageBox(mainWindow, {
                type: "warning",
                title: "AKFES",
                message: "연결 가능한 시리얼 포트를 찾지 못했습니다.",
                detail: "아두이노 USB 연결, 드라이버, COM 포트를 확인하세요."
            });

            callback("");
            return;
        }

        const labels = portList.map((port, index) => {
            const name = port.displayName || port.portName || port.portId || `Serial Port ${index + 1}`;
            const vendorId = port.vendorId ? `VID:${port.vendorId}` : "";
            const productId = port.productId ? `PID:${port.productId}` : "";
            return `${index + 1}. ${name} ${vendorId} ${productId}`.trim();
        });

        const result = await dialog.showMessageBox(mainWindow, {
            type: "question",
            title: "아두이노 포트 선택",
            message: "연결할 아두이노 시리얼 포트를 선택하세요.",
            detail: labels.join("\n"),
            buttons: [...labels.map((_, i) => `${i + 1}`), "Cancel"],
            cancelId: labels.length,
            defaultId: 0
        });

        if (result.response >= 0 && result.response < portList.length) {
            callback(portList[result.response].portId);
        } else {
            callback("");
        }
    });

    mainWindow.once("ready-to-show", () => {
        mainWindow.show();
    });

    mainWindow.loadFile(path.join(__dirname, "..", "client", "templates", "index.html"));
}

app.whenReady().then(() => {
    process.env.AKFES_SERVER_URL = SERVER_URL;
    createWindow();

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        app.quit();
    }
});
