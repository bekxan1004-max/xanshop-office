import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

function findBrowserExecutable() {
  const candidates = [
    process.env.REMOTION_CHROME_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

async function main() {
  const args = process.argv.slice(2);
  const propsFile = args[0];
  const outputMp4 = args[1];
  if (!propsFile || !outputMp4) {
    console.error("Usage: node render_reel.mjs <props.json> <output.mp4>");
    process.exit(2);
  }
  const inputProps = JSON.parse(fs.readFileSync(propsFile, "utf-8"));
  const studioDir = path.dirname(fileURLToPath(import.meta.url));
  const entryPoint = path.join(studioDir, "src", "index.ts");

  const bundleLocation = await bundle({ entryPoint });
  const browserExecutable = findBrowserExecutable();
  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: "LookReel",
    inputProps,
    ...(browserExecutable ? { browserExecutable } : {}),
  });

  fs.mkdirSync(path.dirname(path.resolve(outputMp4)), { recursive: true });
  await renderMedia({
    composition,
    serveUrl: bundleLocation,
    codec: "h264",
    outputLocation: path.resolve(outputMp4),
    inputProps,
    crf: 18,
    ...(browserExecutable ? { browserExecutable } : {}),
  });
  console.log("REMOTION_RENDER_OK:", path.resolve(outputMp4));
}

main().catch((err) => {
  console.error("REMOTION_RENDER_ERR:", err);
  process.exit(1);
});
