/**
 * 纯文字动效模板 v1（流程一）。
 * 画面构成：封面图作背景（可选）+ 深色渐变遮罩 + 标题/关键词/promo code 文字动画；
 * 按分镜分段，每段展示该段分镜文字，并对齐播放该段旁白音频。
 * 全部数据由 inputProps 注入，同一模板换数据即批量出不同视频。
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from "remotion";
import { z } from "zod";

// 单个分镜：画面文字 + 时长 + 可选旁白音频路径（相对 public 或绝对 URL）。
const shotSchema = z.object({
  index: z.number(),
  duration: z.number(),
  scene: z.string().optional().default(""),
  narration: z.string().optional().default(""),
  audioSrc: z.string().optional().default(""),
});

export const promoSchema = z.object({
  title: z.string(),
  keyword: z.string(),
  promoCode: z.string().optional().default(""),
  coverSrc: z.string().optional().default(""), // 封面图，作背景
  totalDuration: z.number().optional().default(16),
  shots: z.array(shotSchema).default([]),
});

export type PromoProps = z.infer<typeof promoSchema>;

export const defaultPromoProps: PromoProps = {
  title: "1xBet Promo Code 2026",
  keyword: "1xbet promo code",
  promoCode: "NEW100",
  coverSrc: "",
  totalDuration: 16,
  shots: [
    { index: 1, duration: 8, scene: "Intro", narration: "", audioSrc: "" },
    { index: 2, duration: 8, scene: "Bonus guide", narration: "", audioSrc: "" },
  ],
};

// 文字入场动画：弹簧上浮 + 淡入。
const useEntrance = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  const translateY = interpolate(p, [0, 1], [40, 0]);
  const opacity = interpolate(p, [0, 1], [0, 1]);
  return { transform: `translateY(${translateY}px)`, opacity };
};

const HeaderBlock: React.FC<{ title: string; keyword: string; promoCode: string }> = ({
  title,
  keyword,
  promoCode,
}) => {
  const titleStyle = useEntrance(0);
  const kwStyle = useEntrance(6);
  const promoStyle = useEntrance(12);
  return (
    <div style={{ padding: "120px 70px 0", textAlign: "center" }}>
      <div
        style={{
          ...titleStyle,
          fontSize: 82,
          fontWeight: 800,
          color: "#fff",
          lineHeight: 1.15,
          textShadow: "0 6px 30px rgba(0,0,0,0.6)",
        }}
      >
        {title}
      </div>
      <div
        style={{
          ...kwStyle,
          marginTop: 28,
          fontSize: 44,
          fontWeight: 600,
          color: "#ffd54a",
          textShadow: "0 4px 18px rgba(0,0,0,0.6)",
        }}
      >
        {keyword}
      </div>
      {promoCode ? (
        <div
          style={{
            ...promoStyle,
            marginTop: 40,
            display: "inline-block",
            padding: "20px 44px",
            fontSize: 60,
            fontWeight: 900,
            color: "#0b1f3a",
            background: "#00e676",
            borderRadius: 20,
            letterSpacing: 3,
            boxShadow: "0 10px 40px rgba(0,230,118,0.5)",
          }}
        >
          {promoCode}
        </div>
      ) : null}
    </div>
  );
};

// 单段分镜的画面文字（每段居中大字，弹入）。
const ShotCaption: React.FC<{ text: string }> = ({ text }) => {
  const style = useEntrance(4);
  if (!text) return null;
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", padding: "0 70px 200px" }}>
      <div
        style={{
          ...style,
          fontSize: 54,
          fontWeight: 700,
          color: "#fff",
          textAlign: "center",
          lineHeight: 1.3,
          background: "rgba(0,0,0,0.35)",
          padding: "24px 36px",
          borderRadius: 18,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

const resolveSrc = (src: string) => {
  if (!src) return "";
  // 已是完整 URL / data URI / file 协议：原样使用
  if (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("data:") ||
    src.startsWith("file://")
  ) {
    return src;
  }
  // 容器内绝对路径（共享 media 卷，如 /app/media/...）：转 file:// 供 SSR 直接读盘
  if (src.startsWith("/")) return `file://${src}`;
  // 其余当作 public 目录下的相对路径
  return staticFile(src);
};

export const PromoVideo: React.FC<PromoProps> = ({
  title,
  keyword,
  promoCode,
  coverSrc,
  shots,
}) => {
  const { fps } = useVideoConfig();
  let acc = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#0b1f3a" }}>
      {/* 背景：封面图（有则铺满）+ 深色渐变遮罩，保证文字可读 */}
      {coverSrc ? (
        <AbsoluteFill>
          <Img src={resolveSrc(coverSrc)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(11,31,58,0.85) 0%, rgba(11,31,58,0.45) 40%, rgba(11,31,58,0.85) 100%)",
        }}
      />

      {/* 顶部固定信息：标题 / 关键词 / promo code */}
      <HeaderBlock title={title} keyword={keyword} promoCode={promoCode} />

      {/* 按分镜分段：每段展示该段文字 + 播放该段旁白音频 */}
      {shots.map((shot) => {
        const from = Math.round(acc * fps);
        const durationInFrames = Math.max(1, Math.round(shot.duration * fps));
        acc += shot.duration;
        const caption = shot.scene || shot.narration || "";
        const audio = resolveSrc(shot.audioSrc || "");
        return (
          <Sequence key={shot.index} from={from} durationInFrames={durationInFrames}>
            <ShotCaption text={caption} />
            {audio ? <Audio src={audio} /> : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
