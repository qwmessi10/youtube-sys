/**
 * 注册教程推广模板（横屏 1920x1080）—— 复刻 1xBet 注册教程视频结构。
 *
 * 【模板拆解 / 数据来源】(依据 Gemini 分析 + 用户声明)
 *   - 左侧约 40%：品牌宣传区。
 *       · 背景图 = 素材 assets.bg_image（AI 生成的风景图；缺省时用深绿纯色）。
 *       · 标题 title、固定文案（app_name/bonus_offer 等写死在本文件常量里）。
 *       · 红色 "PROMO CODE" 标签 + 金框大号优惠码 = 变量 variables.promo_code（每条视频不同）。
 *   - 右侧约 60%：手机操作录屏区 = 素材 assets.screen_record（必须人工上传的 mp4）。
 *   - 旁白音频：按 shots 分段对齐播放（画面不随分镜切换）。
 *
 * 【key 约定】(声明 = 填写 = 本文件访问，三处必须一致)
 *   变量：promo_code
 *   素材：bg_image（AI 生成）、screen_record（人工上传）
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Freeze,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";

// —— 固定文案（写死，不做成变量）——
// 用户声明 app_name / country_name / currency / bonus_offer 固定，这里集中管理，改模板时改这里。
const FIXED = {
  appName: "1xBet",
  bonusOffer: "100% Welcome Bonus",
};

const shotSchema = z.object({
  index: z.number(),
  duration: z.number(),
  scene: z.string().optional().default(""),
  narration: z.string().optional().default(""),
  audioSrc: z.string().optional().default(""),
});

export const registrationSchema = z.object({
  title: z.string().optional().default(""),
  keyword: z.string().optional().default(""),
  promoCode: z.string().optional().default(""),
  coverSrc: z.string().optional().default(""),
  totalDuration: z.number().optional().default(16),
  shots: z.array(shotSchema).default([]),
  // 变量组：promo_code（前端每条视频填写）
  variables: z.record(z.string(), z.any()).optional().default({}),
  // 素材映射：bg_image（左侧背景，AI 生成）、screen_record（右侧录屏，人工上传）
  assets: z.record(z.string(), z.string()).optional().default({}),
  // 素材真实时长映射 {key: 秒}，后端 ffprobe 探测所得。用于「素材播完冻结在最后一帧」。
  assetDurations: z.record(z.string(), z.number()).optional().default({}),
});

export type RegistrationProps = z.infer<typeof registrationSchema>;

export const defaultRegistrationProps: RegistrationProps = {
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

// 左侧品牌宣传区：AI 背景图 + 标题 + 固定 app 名 + 优惠码 + 底部关键词
const BrandPanel: React.FC<{ title: string; keyword: string; promoCode: string; bgSrc: string }> = ({
  title,
  keyword,
  promoCode,
  bgSrc,
}) => {
  const titleStyle = useEntrance(0);
  const labelStyle = useEntrance(6);
  const codeStyle = useEntrance(12);
  const kwStyle = useEntrance(18);
  return (
    <AbsoluteFill style={{ width: "40%", left: 0, backgroundColor: "#0B4F37" }}>
      {bgSrc ? (
        <AbsoluteFill>
          <Img src={bgSrc} style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.4 }} />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill
        style={{
          background: "linear-gradient(180deg, rgba(11,79,55,0.65) 0%, rgba(8,40,28,0.82) 100%)",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 60px",
          textAlign: "center",
        }}
      >
        {/* 固定 app 名称徽标 */}
        <div style={{ ...titleStyle, fontSize: 40, fontWeight: 900, color: "#FFD54A", letterSpacing: 2, marginBottom: 16 }}>
          {FIXED.appName}
        </div>
        <div style={{ ...titleStyle, fontSize: 50, fontWeight: 800, color: "#fff", lineHeight: 1.2, marginBottom: 40 }}>
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
        {/* 固定优惠语 */}
        <div style={{ ...kwStyle, marginTop: 28, fontSize: 30, fontWeight: 700, color: "#fff" }}>{FIXED.bonusOffer}</div>
        <div style={{ ...kwStyle, marginTop: 40, fontSize: 30, fontWeight: 600, color: "#ffd54a" }}>{keyword}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 右侧手机录屏区
// 关键：素材时长往往 < 视频总时长。素材播完后「冻结在最后一帧」，画面继续（配音不停）。
// 做法：时长由后端 ffprobe 探测后通过 durationSec 直接传入（不在渲染容器里用浏览器读，
//       否则容器内 <video> 加载失败会拿不到时长，冻结永远不触发）。
//       当前帧超过素材帧数时，用 <Freeze> 把画面定格在素材最后一帧。
const ScreenPanel: React.FC<{ videoSrc: string; durationSec: number }> = ({ videoSrc, durationSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // 素材总帧数：durationSec>0 时按真实时长换算；<=0（未知）则当作足够长、正常播放不冻结。
  const videoFrames = durationSec && durationSec > 0
    ? Math.max(1, Math.floor(durationSec * fps))
    : Number.POSITIVE_INFINITY;

  if (!videoSrc) {
    return (
      <AbsoluteFill style={{ width: "60%", left: "40%", backgroundColor: "#0a0f14" }}>
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <div style={{ color: "#5b6b78", fontSize: 30 }}>（未提供操作录屏素材 screen_record）</div>
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  const videoStyle: React.CSSProperties = { height: "100%", objectFit: "contain" };
  // 素材已播完（当前帧 >= 素材帧数）→ 冻结在最后一帧；否则正常播放。
  const ended = Number.isFinite(videoFrames) && frame >= videoFrames;
  return (
    <AbsoluteFill style={{ width: "60%", left: "40%", backgroundColor: "#0a0f14" }}>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        {ended ? (
          // 定格：把时间轴冻结在素材最后一帧
          <Freeze frame={(videoFrames as number) - 1}>
            <OffthreadVideo src={videoSrc} style={videoStyle} />
          </Freeze>
        ) : (
          <OffthreadVideo src={videoSrc} style={videoStyle} />
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const RegistrationPromo: React.FC<RegistrationProps> = ({
  title,
  keyword,
  promoCode,
  shots,
  variables,
  assets,
  assetDurations,
}) => {
  const { fps } = useVideoConfig();
  // 变量：优惠码。promoCode 顶层缺省时回退 variables.promo_code
  const code = promoCode || (variables && variables.promo_code) || "";
  // 素材：左侧 AI 背景图 + 右侧人工录屏
  const bgSrc = (assets && assets.bg_image) || "";
  const screenSrc = (assets && assets.screen_record) || "";
  // 录屏素材真实时长（秒），后端 ffprobe 探测所得。缺省 0 = 未知，不冻结。
  const screenDur = (assetDurations && assetDurations.screen_record) || 0;
  let acc = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#0B4F37" }}>
      <BrandPanel title={title} keyword={keyword} promoCode={code} bgSrc={bgSrc} />
      <ScreenPanel videoSrc={screenSrc} durationSec={screenDur} />
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
