/**
 * 左右分屏推广模板（横屏 1920x1080）。
 * 复刻参考视频结构：
 *   - 左侧约 40%：固定品牌宣传区。深绿背景（可用封面图垫底）+ 顶部标题 +
 *     红色 "Promo Code" 标签 + 金绿框大号优惠码 + 底部关键词。
 *   - 右侧约 60%：手机操作录屏区（assets.screen_record），竖屏视频居中铺放。
 * 全部数据由 inputProps 注入：优惠码来自 variables.promo_code；录屏来自 assets.screen_record；
 * 旁白音频按 shots 分段对齐播放。同一模板换数据即批量出不同视频。
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";

const shotSchema = z.object({
  index: z.number(),
  duration: z.number(),
  scene: z.string().optional().default(""),
  narration: z.string().optional().default(""),
  audioSrc: z.string().optional().default(""),
});

export const splitScreenSchema = z.object({
  title: z.string().optional().default(""),
  keyword: z.string().optional().default(""),
  promoCode: z.string().optional().default(""),
  coverSrc: z.string().optional().default(""),
  totalDuration: z.number().optional().default(16),
  shots: z.array(shotSchema).default([]),
  // 模板变量组（promo_code 等）；promoCode 缺省时回退到 variables.promo_code
  variables: z.record(z.string(), z.any()).optional().default({}),
  // 素材映射：screen_record = 右侧手机录屏（HTTP URL，已由 render 服务改写）
  assets: z.record(z.string(), z.string()).optional().default({}),
});

export type SplitScreenProps = z.infer<typeof splitScreenSchema>;

export const defaultSplitScreenProps: SplitScreenProps = {
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
};

// 文字入场：弹簧上浮 + 淡入。
const useEntrance = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return {
    transform: `translateY(${interpolate(p, [0, 1], [30, 0])}px)`,
    opacity: interpolate(p, [0, 1], [0, 1]),
  };
};

// 左侧品牌宣传区
const BrandPanel: React.FC<{ title: string; keyword: string; promoCode: string; coverSrc: string }> = ({
  title,
  keyword,
  promoCode,
  coverSrc,
}) => {
  const titleStyle = useEntrance(0);
  const labelStyle = useEntrance(6);
  const codeStyle = useEntrance(12);
  const kwStyle = useEntrance(18);
  return (
    <AbsoluteFill style={{ width: "40%", left: 0, backgroundColor: "#0B4F37" }}>
      {coverSrc ? (
        <AbsoluteFill>
          <Img src={coverSrc} style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.35 }} />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill
        style={{
          background: "linear-gradient(180deg, rgba(11,79,55,0.7) 0%, rgba(8,40,28,0.85) 100%)",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 60px",
          textAlign: "center",
        }}
      >
        <div style={{ ...titleStyle, fontSize: 58, fontWeight: 800, color: "#fff", lineHeight: 1.2, marginBottom: 50 }}>
          {title}
        </div>
        <div
          style={{
            ...labelStyle,
            background: "#e53935",
            color: "#fff",
            fontSize: 34,
            fontWeight: 700,
            padding: "10px 30px",
            borderRadius: 10,
            letterSpacing: 2,
          }}
        >
          PROMO CODE
        </div>
        <div
          style={{
            ...codeStyle,
            marginTop: 24,
            padding: "24px 50px",
            fontSize: 84,
            fontWeight: 900,
            color: "#0B4F37",
            background: "#FFD54A",
            border: "6px solid #fff",
            borderRadius: 18,
            letterSpacing: 4,
            boxShadow: "0 12px 40px rgba(0,0,0,0.4)",
          }}
        >
          {promoCode || "—"}
        </div>
        <div style={{ ...kwStyle, marginTop: 50, fontSize: 32, fontWeight: 600, color: "#ffd54a" }}>{keyword}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 右侧手机录屏区
const ScreenPanel: React.FC<{ videoSrc: string }> = ({ videoSrc }) => {
  return (
    <AbsoluteFill style={{ width: "60%", left: "40%", backgroundColor: "#0a0f14" }}>
      {videoSrc ? (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <OffthreadVideo src={videoSrc} style={{ height: "100%", objectFit: "contain" }} />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <div style={{ color: "#5b6b78", fontSize: 30 }}>（未提供操作录屏素材 screen_record）</div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

export const SplitScreenPromo: React.FC<SplitScreenProps> = ({
  title,
  keyword,
  promoCode,
  coverSrc,
  shots,
  variables,
  assets,
}) => {
  const { fps } = useVideoConfig();
  const code = promoCode || (variables && variables.promo_code) || "";
  const screenSrc = (assets && assets.screen_record) || "";
  let acc = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#0B4F37" }}>
      <BrandPanel title={title} keyword={keyword} promoCode={code} coverSrc={coverSrc} />
      <ScreenPanel videoSrc={screenSrc} />
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
