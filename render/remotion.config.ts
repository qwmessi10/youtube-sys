// Remotion 配置。渲染服务用 renderMedia API，这里主要给 studio 预览用。
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.overrideWebpackConfig((config) => config);
