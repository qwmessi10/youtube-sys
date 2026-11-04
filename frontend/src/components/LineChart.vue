<script setup>
// 轻量 SVG 折线图（零依赖，避免引入 ECharts 增加构建网络风险）。
// 用于视频指标趋势、排名趋势。支持多条数据线、y 轴反转（排名：1 在顶部）。
import { computed } from "vue";

const props = defineProps({
  labels: { type: Array, default: () => [] },                 // x 轴标签
  series: { type: Array, default: () => [] },                 // [{name, color, values:[...]}]
  height: { type: Number, default: 280 },
  invertY: { type: Boolean, default: false },                 // true=数值越小越靠上（排名）
});

const W = 660;
const PAD = { top: 18, right: 16, bottom: 42, left: 56 };
const H = computed(() => props.height);

const allValues = computed(() =>
  props.series.flatMap((s) => s.values).filter((v) => v !== null && v !== undefined)
);

const minVal = computed(() => (allValues.value.length ? Math.min(...allValues.value) : 0));
const maxVal = computed(() => (allValues.value.length ? Math.max(...allValues.value) : 1));

const xFor = (i) => {
  const n = Math.max(props.labels.length - 1, 1);
  return PAD.left + (i / n) * (W - PAD.left - PAD.right);
};

const yFor = (v) => {
  const range = maxVal.value - minVal.value || 1;
  const ratio = (v - minVal.value) / range;
  const norm = props.invertY ? 1 - ratio : ratio;
  return PAD.top + norm * (H.value - PAD.top - PAD.bottom);
};

const paths = computed(() =>
  props.series.map((s) => {
    const pts = s.values.map((v, i) => [xFor(i).toFixed(1), yFor(v).toFixed(1)]);
    const d = pts.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(" ");
    return { name: s.name, color: s.color, d, points: pts };
  })
);

const yTicks = computed(() => {
  const ticks = [];
  const count = 5;
  for (let i = 0; i <= count; i++) {
    const v = minVal.value + (maxVal.value - minVal.value) * (i / count);
    ticks.push({ v, y: yFor(v) });
  }
  return ticks;
});

const xTicks = computed(() =>
  props.labels.map((label, i) => ({ label, x: xFor(i) }))
);

function fmt(v) {
  if (v === null || v === undefined) return "";
  const n = Number(v);
  if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(1) + "亿";
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(1) + "万";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(1);
}
</script>

<template>
  <div class="linechart">
    <svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMidYMid meet" style="width: 100%; height: auto">
      <!-- y 轴网格与刻度 -->
      <g v-for="t in yTicks" :key="'y' + t.y">
        <line :x1="PAD.left" :y1="t.y" :x2="W - PAD.right" :y2="t.y" stroke="#e4e7ed" stroke-width="1" />
        <text :x="PAD.left - 8" :y="t.y + 4" text-anchor="end" font-size="11" fill="#909399">{{ fmt(t.v) }}</text>
      </g>
      <!-- x 轴刻度 -->
      <g v-for="(t, i) in xTicks" :key="'x' + i">
        <text :x="t.x" :y="H - 14" text-anchor="middle" font-size="10" fill="#909399">{{ t.label }}</text>
      </g>
      <!-- 数据线 -->
      <g v-for="(p, i) in paths" :key="'line' + i">
        <path :d="p.d" fill="none" :stroke="p.color" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        <circle v-for="(pt, j) in p.points" :key="j" :cx="pt[0]" :cy="pt[1]" :r="3" :fill="p.color" />
      </g>
    </svg>
    <!-- 图例 -->
    <div class="linechart-legend">
      <span v-for="(s, i) in series" :key="i" class="legend-item">
        <i :style="{ background: s.color }"></i>{{ s.name }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.linechart { width: 100%; }
.linechart-legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 6px; padding-left: 56px; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #606266; }
.legend-item i { display: inline-block; width: 14px; height: 3px; border-radius: 2px; }
</style>
