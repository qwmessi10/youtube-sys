// 组件注册：把「纯文字动效模板」注册为一个 Composition。
// 视频尺寸 1080x1920（竖屏 Shorts），30fps；时长由 inputProps 的分镜总时长决定。
import { Composition } from "remotion";
import { PromoVideo, promoSchema, defaultPromoProps } from "./PromoVideo";

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="PromoVideo"
      component={PromoVideo}
      // 默认 16s（2×8s）；渲染时按实际 inputProps.totalDuration 用 calculateMetadata 覆盖。
      durationInFrames={16 * FPS}
      fps={FPS}
      width={1080}
      height={1920}
      schema={promoSchema}
      defaultProps={defaultPromoProps}
      calculateMetadata={({ props }) => {
        const total = props.totalDuration && props.totalDuration > 0 ? props.totalDuration : 16;
        return { durationInFrames: Math.round(total * FPS), fps: FPS };
      }}
    />
  );
};
