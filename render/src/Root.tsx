// 组件注册：把「纯文字动效模板」注册为一个 Composition。
// 视频尺寸 1080x1920（竖屏 Shorts），30fps；时长由 inputProps 的分镜总时长决定。
import { Composition } from "remotion";
import { PromoVideo, promoSchema, defaultPromoProps } from "./PromoVideo";
import { SplitScreenPromo, splitScreenSchema, defaultSplitScreenProps } from "./SplitScreenPromo";

const FPS = 30;

// 时长按实际 inputProps.totalDuration 覆盖，默认 16s。
const durationFromProps = ({ props }: { props: { totalDuration?: number } }) => {
  const total = props.totalDuration && props.totalDuration > 0 ? props.totalDuration : 16;
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
    </>
  );
};
