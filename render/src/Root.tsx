// 组件注册：把「纯文字动效模板」注册为一个 Composition。
// 视频尺寸 1080x1920（竖屏 Shorts），30fps；时长由 inputProps 的分镜总时长决定。
import { Composition } from "remotion";
import { PromoVideo, promoSchema, defaultPromoProps } from "./PromoVideo";
import { SplitScreenPromo, splitScreenSchema, defaultSplitScreenProps } from "./SplitScreenPromo";
import { RegistrationPromo, registrationSchema, defaultRegistrationProps } from "./RegistrationPromo";
import { RegistrationPromoV2, registrationV2Schema, defaultRegistrationV2Props } from "./RegistrationPromoV2";
import { Flow3SegmentB, flow3SegBSchema, defaultFlow3SegBProps } from "./Flow3SegmentB";

const FPS = 30;

// 时长按实际 inputProps.totalDuration 覆盖，默认 16s。
const durationFromProps = ({ props }: { props: { totalDuration?: number } }) => {
  const total = props.totalDuration && props.totalDuration > 0 ? props.totalDuration : 16;
  return { durationInFrames: Math.round(total * FPS), fps: FPS };
};

// 流程3 SegB：时长 = segDuration（TTS 旁白实际总时长）。
const durationFromSegDuration = ({ props }: { props: { segDuration?: number } }) => {
  const total = props.segDuration && props.segDuration > 0 ? props.segDuration : 23;
  return { durationInFrames: Math.round(total * FPS), fps: FPS };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* 竖屏纯文字动效模板（流程一初版） */}
      <Composition
        id="PromoVideo"
        component={PromoVideo}
        durationInFrames={16 * FPS}
        fps={FPS}
        width={1080}
        height={1920}
        schema={promoSchema}
        defaultProps={defaultPromoProps}
        calculateMetadata={durationFromProps}
      />
      {/* 横屏左右分屏模板（复刻 1xBet 教程视频） */}
      <Composition
        id="SplitScreenPromo"
        component={SplitScreenPromo}
        durationInFrames={16 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        schema={splitScreenSchema}
        defaultProps={defaultSplitScreenProps}
        calculateMetadata={durationFromProps}
      />
      {/* 注册教程推广模板（复刻 1xBet，左 AI 背景+优惠码 / 右人工录屏） */}
      <Composition
        id="RegistrationPromo"
        component={RegistrationPromo}
        durationInFrames={16 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        schema={registrationSchema}
        defaultProps={defaultRegistrationProps}
        calculateMetadata={durationFromProps}
      />
      {/* 注册教程推广模板 V2（按 Gemini 精细分析复刻：黄底+开场免责声明+左金边绿徽章+右录屏）*/}
      <Composition
        id="RegistrationPromoV2"
        component={RegistrationPromoV2}
        durationInFrames={16 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        schema={registrationV2Schema}
        defaultProps={defaultRegistrationV2Props}
        calculateMetadata={durationFromProps}
      />
      {/* 流程3 · Segment B 画中画（横屏，模糊底图+Promo文字+9:16录屏，左右随机） */}
      <Composition
        id="Flow3SegmentB"
        component={Flow3SegmentB}
        durationInFrames={23 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        schema={flow3SegBSchema}
        defaultProps={defaultFlow3SegBProps}
        calculateMetadata={durationFromSegDuration}
      />
    </>
  );
};
