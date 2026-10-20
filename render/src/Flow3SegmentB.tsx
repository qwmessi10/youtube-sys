/**
 * 流程3 · Segment B 画中画组件（横屏 1920x1080）。
 *
 * 结构：
 *   - 底层：高斯模糊底图 blurBgSrc（CSS filter: blur 铺满）。
 *   - 一侧：9:16 手机注册录屏 screenSrc（画中画，竖屏居中，素材播完冻结最后一帧）。
 *   - 另一侧：Promo Code 静态大字 + 引导文案。
 *   - 左右位置由 screenOnRight 决定（后端按 layout_seed 计算）。
 *   - 旁白音频按 shots 分段对齐播放。
 *
 * 时长：segDuration 秒（= TTS 旁白实际总时长），由后端传入并决定本段帧数。
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Freeze,
  Img,
  OffthreadVideo,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";

const shotSchema = z.object({
  index: z.number(),
  duration: z.number(),
  narration: z.string().optional().default(""),
  audioSrc: z.string().optional().default(""),
});

export const flow3SegBSchema = z.object({
  promoCode: z.string().optional().default(""),
  blurBgSrc: z.string().optional().default(""),
  screenSrc: z.string().optional().default(""),
  screenDuration: z.number().optional().default(0),
  segDuration: z.number().optional().default(23),
  screenOnRight: z.boolean().optional().default(true),
  shots: z.array(shotSchema).default([]),
});

export type Flow3SegBProps = z.infer<typeof flow3SegBSchema>;

export const defaultFlow3SegBProps: Flow3SegBProps = {
  promoCode: "ZH567",
  blurBgSrc: "",
  screenSrc: "",
  screenDuration: 0,
  segDuration: 23,
  screenOnRight: true,
  shots: [{ index: 1, duration: 7, narration: "", audioSrc: "" }],
};

const VH = 1080;
const fs = (pct: number) => Math.round((pct / 100) * VH);

// 左侧/右侧 Promo 文案面板。
const PromoPanel: React.FC<{ promoCode: string; side: "left" | "right" }> = ({ promoCode, side }) => {
  return (
    <div
      style={{
        position: "absolute",
        [side]: "0%",
        top: "0%",
        width: "50%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 3%",
        boxSizing: "border-box",
      }}
    >
      {/* 引导文案 */}
      <div
        style={{
          fontSize: fs(4.2),
          fontWeight: 800,
          color: "#FFFFFF",
          textAlign: "center",
          textShadow: "0 4px 18px rgba(0,0,0,0.6)",
          marginBottom: "6%",
          lineHeight: 1.2,
        }}
      >
        Use Promo Code
      </div>
      {/* Promo Code 大字徽章 */}
      <div
        style={{
          backgroundColor: "#0B4F37",
          border: "6px solid #FFD54A",
          borderRadius: 20,
          padding: "5% 8%",
          boxShadow: "0 0 40px rgba(0,0,0,0.4), inset 0 0 30px rgba(255,213,74,0.18)",
        }}
      >
        <div
          style={{
            fontSize: fs(9),
            fontWeight: 900,
            color: "#FFD54A",
            letterSpacing: 4,
            textShadow: "0 4px 16px rgba(0,0,0,0.5)",
          }}
        >
          {promoCode || "—"}
        </div>
      </div>
      {/* 行动号召 */}
      <div
        style={{
          fontSize: fs(3),
          fontWeight: 700,
          color: "#FFFFFF",
          textAlign: "center",
          marginTop: "6%",
          textShadow: "0 3px 12px rgba(0,0,0,0.6)",
        }}
      >
        Register Now &amp; Claim Your Bonus
      </div>
    </div>
  );
};

// 9:16 录屏画中画面板。素材播完冻结最后一帧（配音可能更长）。
const ScreenPanel: React.FC<{ videoSrc: string; durationSec: number; side: "left" | "right" }> = ({
  videoSrc,
  durationSec,
  side,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const videoFrames =
    durationSec && durationSec > 0 ? Math.max(1, Math.floor(durationSec * fps)) : Number.POSITIVE_INFINITY;

  // 9:16 竖屏框：高度占画面 90%，宽按 9:16 比例换算。
  const h = Math.round(VH * 0.9);
  const w = Math.round((h * 9) / 16);
  const boxStyle: React.CSSProperties = {
    position: "absolute",
    [side]: "6%",
    top: "5%",
    width: w,
    height: h,
    backgroundColor: "#000000",
    borderRadius: 18,
    overflow: "hidden",
    boxShadow: "0 0 50px rgba(0,0,0,0.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };

  if (!videoSrc) {
    return (
      <div style={boxStyle}>
        <div style={{ color: "#8a949c", fontSize: fs(2) }}>（未配置 9:16 录屏素材）</div>
      </div>
    );
  }
  const videoStyle: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover" };
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

export const Flow3SegmentB: React.FC<Flow3SegBProps> = ({
  promoCode,
  blurBgSrc,
  screenSrc,
  screenDuration,
  screenOnRight,
  shots,
}) => {
  const { fps } = useVideoConfig();
  const screenSide: "left" | "right" = screenOnRight ? "right" : "left";
  const promoSide: "left" | "right" = screenOnRight ? "left" : "right";
  let acc = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#111418" }}>
      {/* 高斯模糊底图铺满 */}
      {blurBgSrc ? (
        <AbsoluteFill>
          <Img
            src={blurBgSrc}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "blur(28px) brightness(0.6)",
              transform: "scale(1.1)",
            }}
          />
        </AbsoluteFill>
      ) : null}
      {/* 暗化遮罩，提升文字可读性 */}
      <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.25)" }} />
      {/* 录屏画中画 + Promo 文案（左右由 seed 决定） */}
      <ScreenPanel videoSrc={screenSrc} durationSec={screenDuration} side={screenSide} />
      <PromoPanel promoCode={promoCode} side={promoSide} />
      {/* 旁白音频按段对齐播放 */}
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
