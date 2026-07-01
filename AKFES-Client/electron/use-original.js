const fs = require("fs");
const path = require("path");

const htmlPath = path.join(__dirname, "..", "client", "templates", "index.html");

let html = fs.readFileSync(htmlPath, "utf8");
html = html.replace("../static/app.obf.js", "../static/app.js");

fs.writeFileSync(htmlPath, html, "utf8");
console.log("index.html now uses app.js");
