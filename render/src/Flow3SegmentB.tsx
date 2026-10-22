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
  promoVariant: z.number().optional().default(0),  // Promo 面板样式变体 0~4
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
  promoVariant: 0,
  shots: [{ index: 1, duration: 7, narration: "", audioSrc: "" }],
};

const VH = 1080;
const fs = (pct: number) => Math.round((pct / 100) * VH);

// ====== Promo 面板：5 套样式变体，按 promoVariant 随机选用 ======
const PANEL_WRAP: React.CSSProperties = {
  position: "absolute", top: "0%", width: "50%", height: "100%",
  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
  padding: "0 3%", boxSizing: "border-box",
};
const sh = (o = 0.6) => `0 4px 18px rgba(0,0,0,${o})`;

// 变体0：绿底金框徽章（原始款）
const V0: React.FC<{ c: string }> = ({ c }) => (
  <>
    <div style={{ fontSize: fs(4.2), fontWeight: 800, color: "#FFF", textAlign: "center", textShadow: sh(), marginBottom: "6%", lineHeight: 1.2 }}>Use Promo Code</div>
    <div style={{ backgroundColor: "#0B4F37", border: "6px solid #FFD54A", borderRadius: 20, padding: "5% 8%", boxShadow: "0 0 40px rgba(0,0,0,0.4), inset 0 0 30px rgba(255,213,74,0.18)" }}>
      <div style={{ fontSize: fs(9), fontWeight: 900, color: "#FFD54A", letterSpacing: 4, textShadow: "0 4px 16px rgba(0,0,0,0.5)" }}>{c}</div>
    </div>
    <div style={{ fontSize: fs(3), fontWeight: 700, color: "#FFF", textAlign: "center", marginTop: "6%", textShadow: sh() }}>Register Now &amp; Claim Your Bonus</div>
  </>
);

// 变体1：优惠券/票券式（白底虚线剪裁边）
const V1: React.FC<{ c: string }> = ({ c }) => (
  <div style={{ backgroundColor: "#FFFFFF", border: "4px dashed #0B4F37", borderRadius: 16, padding: "7% 6%", width: "88%", textAlign: "center", boxShadow: "0 10px 40px rgba(0,0,0,0.35)" }}>
    <div style={{ fontSize: fs(3), fontWeight: 700, color: "#0B4F37", letterSpacing: 2, marginBottom: "5%" }}>PROMO CODE</div>
    <div style={{ fontSize: fs(8.5), fontWeight: 900, color: "#111", letterSpacing: 4, borderTop: "2px dashed #bbb", borderBottom: "2px dashed #bbb", padding: "4% 0" }}>{c}</div>
    <div style={{ fontSize: fs(2.6), fontWeight: 700, color: "#0B4F37", marginTop: "5%" }}>Apply at Registration</div>
  </div>
);

// 变体2：App 界面风（顶部标签 + 输入框样式码 + 大号 CTA 按钮）
const V2: React.FC<{ c: string }> = ({ c }) => (
  <div style={{ width: "90%", display: "flex", flexDirection: "column", gap: fs(2.4) }}>
    <div style={{ fontSize: fs(3.4), fontWeight: 800, color: "#FFF", textShadow: sh() }}>Enter Promo Code</div>
    <div style={{ backgroundColor: "rgba(255,255,255,0.96)", borderRadius: 14, padding: "4% 5%", display: "flex", alignItems: "center", justifyContent: "space-between", boxShadow: "0 8px 30px rgba(0,0,0,0.3)" }}>
      <span style={{ fontSize: fs(6.5), fontWeight: 900, color: "#111", letterSpacing: 3 }}>{c}</span>
      <span style={{ fontSize: fs(2.4), fontWeight: 700, color: "#0B4F37" }}>COPY</span>
    </div>
    <div style={{ backgroundColor: "#1FA366", borderRadius: 14, padding: "4% 0", textAlign: "center", fontSize: fs(3.4), fontWeight: 900, color: "#FFF", boxShadow: "0 8px 24px rgba(31,163,102,0.5)" }}>REGISTER NOW</div>
  </div>
);

// 变体3：通知/聊天气泡（本地化亲和感）
const V3: React.FC<{ c: string }> = ({ c }) => (
  <div style={{ width: "92%", backgroundColor: "rgba(17,20,24,0.78)", borderRadius: 22, padding: "7% 6%", border: "2px solid rgba(255,255,255,0.15)" }}>
    <div style={{ fontSize: fs(2.8), fontWeight: 700, color: "#9fe3c0", marginBottom: "4%" }}>🎁 Special Offer</div>
    <div style={{ fontSize: fs(3.2), fontWeight: 700, color: "#FFF", lineHeight: 1.35, marginBottom: "5%" }}>Sign up today and use code</div>
    <div style={{ display: "inline-block", backgroundColor: "#FFD54A", color: "#111", fontSize: fs(6.5), fontWeight: 900, letterSpacing: 3, borderRadius: 12, padding: "3% 7%" }}>{c}</div>
  </div>
);

// 变体4：极简白底深字（官方、克制）
const V4: React.FC<{ c: string }> = ({ c }) => (
  <div style={{ width: "88%", backgroundColor: "rgba(255,255,255,0.94)", borderRadius: 14, padding: "8% 6%", textAlign: "center", boxShadow: "0 10px 36px rgba(0,0,0,0.3)" }}>
    <div style={{ fontSize: fs(2.8), fontWeight: 700, color: "#555", letterSpacing: 3, marginBottom: "5%" }}>OFFICIAL PROMO CODE</div>
    <div style={{ fontSize: fs(8.5), fontWeight: 900, color: "#0B4F37", letterSpacing: 5 }}>{c}</div>
    <div style={{ height: 4, width: "40%", backgroundColor: "#0B4F37", margin: "6% auto 5%" }} />
    <div style={{ fontSize: fs(2.6), fontWeight: 700, color: "#333" }}>Register &amp; Claim Your Bonus</div>
  </div>
);

// 按 variant 选变体（0~4，越界取模兜底）。
const PromoPanel: React.FC<{ promoCode: string; side: "left" | "right"; variant: number }> = ({ promoCode, side, variant }) => {
  const c = promoCode || "—";
  const variants = [<V0 c={c} />, <V1 c={c} />, <V2 c={c} />, <V3 c={c} />, <V4 c={c} />];
  const idx = ((Math.floor(variant) % 5) + 5) % 5;
  return <div style={{ ...PANEL_WRAP, [side]: "0%" }}>{variants[idx]}</div>;
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
  promoVariant,
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
      <PromoPanel promoCode={promoCode} side={promoSide} variant={promoVariant} />
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
