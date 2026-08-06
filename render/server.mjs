/**
 * Remotion 渲染 HTTP 服务（流程一）。
 * 启动时 bundle 一次模板（较慢，只做一次）；收到 POST /render 用 renderMedia 出 mp4。
 * 与 Django/worker 通过共享 media volume 交换文件：
 *   - 入参里的 coverSrc / audioSrc 用容器内可访问的绝对路径
 *   - 出参 outPath 为容器内绝对路径，worker 按同一 volume 读取
 */
import express from "express";
import { bundle } from "@remotion/bundler";
import { selectComposition, renderMedia } from "@remotion/renderer";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;
const COMPOSITION_ID = "PromoVideo";
// 共享 media 卷在容器内的挂载点；渲染时把该前缀的绝对路径改写成本服务的 HTTP 地址，
// 让无头 Chromium 通过 HTTP 加载资源（file:// 会被 Chromium 安全策略拦截）。
const MEDIA_ROOT = "/app/media";
const MEDIA_URL_PREFIX = `http://localhost:${PORT}/media`;

// 把 inputProps 里指向共享卷的绝对路径（coverSrc / shots[].audioSrc）改写成 HTTP URL。
function rewriteMediaPaths(props) {
  const toUrl = (p) =>
    typeof p === "string" && p.startsWith(MEDIA_ROOT + "/")
      ? MEDIA_URL_PREFIX + p.slice(MEDIA_ROOT.length)
      : p;
  const next = { ...props };
  if (next.coverSrc) next.coverSrc = toUrl(next.coverSrc);
  if (Array.isArray(next.shots)) {
    next.shots = next.shots.map((s) => ({ ...s, audioSrc: toUrl(s.audioSrc) }));
  }
  return next;
}

let bundlePromise = null;

// 只 bundle 一次，后续渲染复用。首次请求触发。
function getBundle() {
  if (!bundlePromise) {
    console.log("[render] bundling Remotion project...");
    bundlePromise = bundle({
      entryPoint: path.join(__dirname, "src", "index.ts"),
      // webpack 缓存目录放共享临时区，避免每次冷启
      onProgress: (p) => {
        if (p % 25 === 0) console.log(`[render] bundle ${p}%`);
      },
    }).then((loc) => {
      console.log("[render] bundle done:", loc);
      return loc;
    });
  }
  return bundlePromise;
}

const app = express();
app.use(express.json({ limit: "20mb" }));
// 把共享 media 卷暴露成 HTTP 静态资源，供渲染时 Chromium 加载封面图/音频。
app.use("/media", express.static(MEDIA_ROOT));

app.get("/health", (_req, res) => res.json({ ok: true }));

app.post("/render", async (req, res) => {
  const { inputProps, outPath } = req.body || {};
  if (!inputProps || !outPath) {
    return res.status(400).json({ error: "缺少 inputProps 或 outPath" });
  }
  try {
    const serveUrl = await getBundle();
    // 把共享卷绝对路径改写成 HTTP URL，供 Chromium 加载
    const props = rewriteMediaPaths(inputProps);
    const composition = await selectComposition({
      serveUrl,
      id: COMPOSITION_ID,
      inputProps: props,
    });
    console.log(`[render] rendering ${outPath} (${composition.durationInFrames} frames)`);
    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      outputLocation: outPath,
      inputProps: props,
      // Docker 内 Chromium 建议开多进程，避免单进程渲染卡顿
      chromiumOptions: { enableMultiProcessOnLinux: true },
    });
    console.log(`[render] done ${outPath}`);
    return res.json({ ok: true, outPath, durationInFrames: composition.durationInFrames });
  } catch (err) {
    console.error("[render] failed:", err);
    return res.status(500).json({ error: String(err && err.message ? err.message : err) });
  }
});

app.listen(PORT, () => {
  console.log(`[render] service listening on ${PORT}`);
  // 预热 bundle，减少首个请求延迟
  getBundle().catch((e) => console.error("[render] prewarm bundle failed:", e));
});
