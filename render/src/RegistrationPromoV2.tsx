/**
 * 注册教程推广模板 V2（横屏 1920x1080）—— 依据 Gemini 精细化分析复刻。
 *
 * 【视频结构 / 数据来源】(依据 video/ 参考视频的结构化 spec)
 *   画布：16:9，底色 #F4C44E（亮黄）。
 *   ┌ 开场（0~1.5s）：全屏黄底免责声明 Disclaimer（DISCLAIMER 标题 + fair use 长文案），1.5s 淡出。
 *   ├ 左侧徽章区（1.5s 起常驻，x4 y22 w44 h55）：深绿 #0B4F37 底 + 金色金属边框，
 *   │    「Promo Code」标签 + 大号优惠码 {promo_code}（变量，每条视频不同）。
 *   └ 右侧录屏区（x51 y3 w46 h94）：白底，播放人工上传的手机操作录屏 screen_record。
 *   旁白音频：按 shots 分段对齐播放（画面不随分镜切换）。
 *
 * 【key 约定】(声明 = 填写 = 本文件访问，三处必须一致)
 *   变量：promo_code
 *   素材：screen_record（人工上传的手机录屏 mp4）
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Freeze,
  OffthreadVideo,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";

// 开场免责声明时长（秒）。spec：视频开头约 1.5 秒黄底黑字英文免责声明。
const DISCLAIMER_SEC = 1.5;

// 免责声明正文（fair use 声明，固定文案，写死）。
const DISCLAIMER_TEXT =
  'Video is for educational purpose only. Copyright Disclaimer Under Section 107 ' +
  'of the Copyright Act 1976, allowance is made for "fair use" for purposes such as ' +
  "criticism, comment, news reporting, teaching, scholarship, and research. Fair use " +
  "is a use permitted by copyright statute that might otherwise be infringing. " +
  "Non-profit, educational or personal use tips the balance in favor of fair use.";

const shotSchema = z.object({
  index: z.number(),
  duration: z.number(),
  scene: z.string().optional().default(""),
  narration: z.string().optional().default(""),
  audioSrc: z.string().optional().default(""),
});

export const registrationV2Schema = z.object({
  title: z.string().optional().default(""),
  keyword: z.string().optional().default(""),
  promoCode: z.string().optional().default(""),
  coverSrc: z.string().optional().default(""),
  totalDuration: z.number().optional().default(16),
  shots: z.array(shotSchema).default([]),
  // 变量组：promo_code（前端每条视频填写）
  variables: z.record(z.string(), z.any()).optional().default({}),
  // 素材映射：screen_record（右侧录屏，人工上传）
  assets: z.record(z.string(), z.string()).optional().default({}),
  // 素材真实时长映射 {key: 秒}，后端 ffprobe 探测所得。用于「素材播完冻结在最后一帧」。
  assetDurations: z.record(z.string(), z.number()).optional().default({}),
});

export type RegistrationV2Props = z.infer<typeof registrationV2Schema>;

export const defaultRegistrationV2Props: RegistrationV2Props = {
  title: "1xBet Registration Guide",
  keyword: "1xbet promo code",
  promoCode: "75EPL",
  coverSrc: "",
  totalDuration: 16,
  shots: [
    { index: 1, duration: 8, scene: "", narration: "", audioSrc: "" },
    { index: 2, duration: 8, scene: "", narration: "", audioSrc: "" },
  ],
  variables: {},
  assets: {},
  assetDurations: {},
};

// 字号换算：spec 里的 font_size_pct 相对画布高度（1080）。
const VH = 1080;
const fs = (pct: number) => Math.round((pct / 100) * VH);

// 开场免责声明面板：全屏黄底，DISCLAIMER 标题 + fair use 长文案，1.5s 后淡出。
const DisclaimerPanel: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const endFrame = DISCLAIMER_SEC * fps;
  // 最后 0.3s 淡出，切到主体画面。
  const fadeFrames = Math.round(0.3 * fps);
  const opacity = interpolate(
    frame,
    [endFrame - fadeFrames, endFrame],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  return (
    <AbsoluteFill style={{ backgroundColor: "#F4C44E", opacity }}>
      {/* DISCLAIMER 标题：x10 y10 w80 h12，font 5.5% 黑色加粗居中 */}
      <div
        style={{
          position: "absolute",
          left: "10%",
          top: "10%",
          width: "80%",
          height: "12%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: fs(5.5),
          fontWeight: 800,
          color: "#000000",
          letterSpacing: 2,
        }}
      >
        DISCLAIMER
      </div>
      {/* fair use 长文案：x6 y25 w88 h65，font 3.2% 黑色加粗居中 */}
      <div
        style={{
          position: "absolute",
          left: "6%",
          top: "25%",
          width: "88%",
          height: "65%",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
          textAlign: "center",
          fontSize: fs(3.2),
          fontWeight: 700,
          color: "#000000",
          lineHeight: 1.4,
        }}
      >
        {DISCLAIMER_TEXT}
      </div>
    </AbsoluteFill>
  );
};

// 左侧优惠码徽章区：深绿底 + 金色金属边框，Promo Code 标签 + 大号优惠码。
// spec：box x4 y22 w44 h55；1.5s 起常驻。
const PromoBadge: React.FC<{ promoCode: string }> = ({ promoCode }) => {
  return (
    <div
      style={{
        position: "absolute",
        left: "4%",
        top: "22%",
        width: "44%",
        height: "55%",
        backgroundColor: "#0B4F37",
        // 金色金属边框 + 高光
        border: "6px solid #FFD54A",
        borderRadius: 20,
        boxShadow: "0 0 40px rgba(0,0,0,0.35), inset 0 0 30px rgba(255,213,74,0.15)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {/* Promo Code 标签：font 3.8% 白色加粗 */}
      <div
        style={{
          fontSize: fs(3.8),
          fontWeight: 700,
          color: "#FFFFFF",
          letterSpacing: 3,
          marginBottom: "8%",
        }}
      >
        Promo Code
      </div>
      {/* 优惠码（变量）：font 8.5% 白色加粗 */}
      <div
        style={{
          fontSize: fs(8.5),
          fontWeight: 900,
          color: "#FFFFFF",
          letterSpacing: 4,
          textShadow: "0 4px 16px rgba(0,0,0,0.5)",
        }}
      >
        {promoCode || "—"}
      </div>
    </div>
  );
};

// 右侧手机录屏区：白底，播放 screen_record。素材播完冻结在最后一帧（配音不停）。
// spec：box x51 y3 w46 h94。
const ScreenPanel: React.FC<{ videoSrc: string; durationSec: number }> = ({ videoSrc, durationSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const videoFrames =
    durationSec && durationSec > 0
      ? Math.max(1, Math.floor(durationSec * fps))
      : Number.POSITIVE_INFINITY;

  const boxStyle: React.CSSProperties = {
    position: "absolute",
    left: "51%",
    top: "3%",
    width: "46%",
    height: "94%",
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };

  if (!videoSrc) {
    return (
      <div style={boxStyle}>
        <div style={{ color: "#8a949c", fontSize: fs(2.2) }}>（未提供操作录屏素材 screen_record）</div>
      </div>
    );
  }

  const videoStyle: React.CSSProperties = { width: "100%", height: "100%", objectFit: "contain" };
  const ended = Number.isFinite(videoFrames) && frame >= videoFrames;
  return (
    <div style={boxStyle}>
      {ended ? (
        <Freeze frame={(videoFrames as number) - 1}>
          <OffthreadVideo src={videoSrc} style={videoStyle} />
        </Freeze>
      ) : (
        <OffthreadVideo src={videoSrc} style={videoStyle} />
      )}
    </div>
  );
};

export const RegistrationPromoV2: React.FC<RegistrationV2Props> = ({
  promoCode,
  shots,
  variables,
  assets,
  assetDurations,
}) => {
  const { fps } = useVideoConfig();
  // 变量：优惠码。promoCode 顶层缺省时回退 variables.promo_code
  const code = promoCode || (variables && variables.promo_code) || "";
  // 素材：右侧人工录屏
  const screenSrc = (assets && assets.screen_record) || "";
  const screenDur = (assetDurations && assetDurations.screen_record) || 0;
  let acc = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#F4C44E" }}>
      {/* 主体：左徽章 + 右录屏（免责声明淡出后可见） */}
      <PromoBadge promoCode={code} />
      <ScreenPanel videoSrc={screenSrc} durationSec={screenDur} />
      {/* 开场免责声明覆盖在最上层，1.5s 淡出 */}
      <Sequence from={0} durationInFrames={Math.round(DISCLAIMER_SEC * fps)}>
        <DisclaimerPanel />
      </Sequence>
      {/* 逐段播放旁白音频（画面不随分镜切换，音频按段对齐） */}
      {shots.map((shot) => {
        const from = Math.round(acc * fps);
        const durationInFrames = Math.max(1, Math.round(shot.duration * fps));
        acc += shot.duration;
        if (!shot.audioSrc) return null;
        return (
          <Sequence key={shot.index} from={from} durationInFrames={durationInFrames}>
            <Audio src={shot.audioSrc} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
