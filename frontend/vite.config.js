import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      // 封面图、成品视频等由后端 /media/ 提供，dev server 也要代理，否则 el-image 显示 FAILED
      "/media": "http://localhost:8000",
    },
  },
});

