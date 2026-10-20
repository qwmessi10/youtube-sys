// 组件注册：流程3 的 SegB 画中画组件。
// 流程1/2 的旧模板（PromoVideo/SplitScreenPromo/RegistrationPromo/V2）已随流程1/2 删除。
import { Composition } from "remotion";
import { Flow3SegmentB, flow3SegBSchema, defaultFlow3SegBProps } from "./Flow3SegmentB";

const FPS = 30;

// 流程3 SegB：时长 = segDuration（TTS 旁白实际总时长）。
const durationFromSegDuration = ({ props }: { props: { segDuration?: number } }) => {
  const total = props.segDuration && props.segDuration > 0 ? props.segDuration : 23;
  return { durationInFrames: Math.round(total * FPS), fps: FPS };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
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
