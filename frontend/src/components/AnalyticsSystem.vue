<script setup>
// 数据分析系统：视频库（我的视频看板）/ 竞品 SEO 分析 / 排名追踪。
// 由 App.vue 二级菜单通过 view 控制：analytics-videos / analytics-competitor / analytics-rankings
import { onMounted, ref, watch } from "vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";
import LineChart from "./LineChart.vue";

const props = defineProps({ view: { type: String, default: "analytics-videos" } });

const COUNTRIES = [
  { value: "US", label: "美国" }, { value: "GB", label: "英国" }, { value: "CA", label: "加拿大" },
  { value: "AU", label: "澳大利亚" }, { value: "NZ", label: "新西兰" }, { value: "DE", label: "德国" },
  { value: "FR", label: "法国" }, { value: "ES", label: "西班牙" }, { value: "IT", label: "意大利" },
  { value: "BR", label: "巴西" }, { value: "MX", label: "墨西哥" }, { value: "JP", label: "日本" },
  { value: "KR", label: "韩国" }, { value: "IN", label: "印度" }, { value: "SG", label: "新加坡" },
  { value: "AE", label: "阿联酋" },
];
const LANGUAGES = [
  { value: "en", label: "英语" }, { value: "zh-CN", label: "简体中文" }, { value: "zh-TW", label: "繁体中文" },
  { value: "es", label: "西班牙语" }, { value: "pt", label: "葡萄牙语" }, { value: "de", label: "德语" },
  { value: "fr", label: "法语" }, { value: "it", label: "意大利语" }, { value: "ja", label: "日语" },
  { value: "ko", label: "韩语" }, { value: "hi", label: "印地语" }, { value: "ar", label: "阿拉伯语" },
];

function number(value) {
  return value === null || value === undefined ? "—" : new Intl.NumberFormat("zh-CN").format(value);
}
function datetime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}
function thumb(videoId) {
  return videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : "";
}

const LINE_COLORS = ["#4d9cf8", "#e33a4b", "#2eb872", "#f0a020", "#8a5cf6"];

// ============ 板块 A：视频库 ============
const videos = ref([]);
const videoTotal = ref(0);
const videoPage = ref(1);
const videoLoading = ref(false);
const videoDialog = ref(false);
const videoSaving = ref(false);
const videoForm = ref({ video_url: "", remark: "" });
const refreshingId = ref(null);
const syncing = ref(false);
const trendDialog = ref(false);
const trendTitle = ref("");
const trendLabels = ref([]);
const trendSeries = ref([]);

async function loadVideos(page = videoPage.value) {
  videoPage.value = page;
  videoLoading.value = true;
  try {
    const { data } = await axios.get("/api/analytics-videos/", { params: { page } });
    videos.value = data.results;
    videoTotal.value = data.count;
  } catch {
    ElMessage.error("加载视频库失败");
  } finally {
    videoLoading.value = false;
  }
}

function openAddVideo() {
  videoForm.value = { video_url: "", remark: "" };
  videoDialog.value = true;
}

async function saveVideo() {
  if (!videoForm.value.video_url.trim()) return ElMessage.warning("请填写视频链接");
  videoSaving.value = true;
  try {
    await axios.post("/api/analytics-videos/", videoForm.value);
    ElMessage.success("已添加");
    videoDialog.value = false;
    await loadVideos();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "添加失败");
  } finally {
    videoSaving.value = false;
  }
}

async function refreshVideo(row) {
  refreshingId.value = row.id;
  try {
    await axios.post(`/api/analytics-videos/${row.id}/refresh/`);
    ElMessage.success("已刷新");
    await loadVideos();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "刷新失败");
  } finally {
    refreshingId.value = null;
  }
}

async function syncVideos() {
  syncing.value = true;
  try {
    const { data } = await axios.post("/api/analytics-videos/sync/");
    ElMessage.success(`同步完成：新增 ${data.created} 个，跳过 ${data.skipped} 个`);
    await loadVideos();
  } catch {
    ElMessage.error("同步失败");
  } finally {
    syncing.value = false;
  }
}

async function deleteVideo(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title || row.video_id}」？`, "确认删除", { type: "warning" });
    await axios.delete(`/api/analytics-videos/${row.id}/`);
    ElMessage.success("已删除");
    await loadVideos();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

async function showVideoTrend(row) {
  try {
    const { data } = await axios.get(`/api/analytics-videos/${row.id}/snapshots/`);
    if (!data.length) return ElMessage.warning("暂无历史快照");
    trendTitle.value = `「${row.title || row.video_id}」指标趋势`;
    trendLabels.value = data.map((s) => new Date(s.captured_at).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }));
    trendSeries.value = [
      { name: "播放", color: LINE_COLORS[0], values: data.map((s) => s.view_count ?? 0) },
      { name: "点赞", color: LINE_COLORS[1], values: data.map((s) => s.like_count ?? 0) },
      { name: "评论", color: LINE_COLORS[2], values: data.map((s) => s.comment_count ?? 0) },
    ];
    trendDialog.value = true;
  } catch {
    ElMessage.error("加载趋势失败");
  }
}

// ============ 板块 B：竞品 SEO 分析 ============
const analysisForm = ref({ keyword: "", country: "US", language: "en", top_n: 10 });
const analyzing = ref(false);
const analyses = ref([]);
const analysisTotal = ref(0);
const analysisPage = ref(1);
const analysisLoading = ref(false);
const detailDialog = ref(false);
const detailData = ref(null);

async function loadAnalyses(page = analysisPage.value) {
  analysisPage.value = page;
  analysisLoading.value = true;
  try {
    const { data } = await axios.get("/api/analytics-competitor/", { params: { page } });
    analyses.value = data.results;
    analysisTotal.value = data.count;
  } catch {
    ElMessage.error("加载分析记录失败");
  } finally {
    analysisLoading.value = false;
  }
}

async function runAnalyze() {
  if (!analysisForm.value.keyword.trim()) return ElMessage.warning("请填写关键词");
  analyzing.value = true;
  try {
    const { data } = await axios.post("/api/analytics-competitor/analyze/", analysisForm.value);
    if (data.status === "failed") {
      ElMessage.error("分析失败：" + (data.error_message || "未知错误"));
    } else {
      ElMessage.success("分析完成");
      detailData.value = data;
      detailDialog.value = true;
    }
    await loadAnalyses();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "分析失败");
  } finally {
    analyzing.value = false;
  }
}

async function viewAnalysis(row) {
  detailData.value = row.result ? row : null;
  // 列表已含 result，直接展示
  if (row.result && row.result.videos) {
    detailData.value = row;
    detailDialog.value = true;
    return;
  }
  detailDialog.value = true;
}

async function deleteAnalysis(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.keyword}」的分析记录？`, "确认删除", { type: "warning" });
    await axios.delete(`/api/analytics-competitor/${row.id}/`);
    ElMessage.success("已删除");
    await loadAnalyses();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

// ============ 板块 C：排名追踪 ============
const trackings = ref([]);
const trackingTotal = ref(0);
const trackingPage = ref(1);
const trackingLoading = ref(false);
const trackingDialog = ref(false);
const trackingSaving = ref(false);
const trackingForm = ref({ keyword: "", country: "US", language: "en", top_n: 10, enabled: true });
const capturingId = ref(null);
const rankTrendDialog = ref(false);
const rankTrendTitle = ref("");
const rankTrendLabels = ref([]);
const rankTrendSeries = ref([]);

async function loadTrackings(page = trackingPage.value) {
  trackingPage.value = page;
  trackingLoading.value = true;
  try {
    const { data } = await axios.get("/api/analytics-rank-trackings/", { params: { page } });
    trackings.value = data.results;
    trackingTotal.value = data.count;
  } catch {
    ElMessage.error("加载追踪列表失败");
  } finally {
    trackingLoading.value = false;
  }
}

function openAddTracking() {
  trackingForm.value = { keyword: "", country: "US", language: "en", top_n: 10, enabled: true };
  trackingDialog.value = true;
}

async function saveTracking() {
  if (!trackingForm.value.keyword.trim()) return ElMessage.warning("请填写关键词");
  trackingSaving.value = true;
  try {
    await axios.post("/api/analytics-rank-trackings/", trackingForm.value);
    ElMessage.success("已添加追踪");
    trackingDialog.value = false;
    await loadTrackings();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "添加失败");
  } finally {
    trackingSaving.value = false;
  }
}

async function toggleTracking(row) {
  try {
    await axios.patch(`/api/analytics-rank-trackings/${row.id}/`, { enabled: row.enabled });
    ElMessage.success(row.enabled ? "已启用" : "已停用");
  } catch {
    ElMessage.error("更新失败");
  }
}

async function captureTracking(row) {
  capturingId.value = row.id;
  try {
    await axios.post(`/api/analytics-rank-trackings/${row.id}/capture/`);
    ElMessage.success("抓取完成");
    await loadTrackings();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "抓取失败");
  } finally {
    capturingId.value = null;
  }
}

async function deleteTracking(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.keyword}」的追踪？`, "确认删除", { type: "warning" });
    await axios.delete(`/api/analytics-rank-trackings/${row.id}/`);
    ElMessage.success("已删除");
    await loadTrackings();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

async function showRankTrend(row) {
  try {
    const { data } = await axios.get(`/api/analytics-rank-trackings/${row.id}/snapshots/`);
    if (!data.length) return ElMessage.warning("暂无快照，先抓取一次");
    // 取第一个快照的 top N 视频，追踪它们在各快照的排名（掉榜用 top_n+1 表示）
    const topVideos = (data[0].videos || []).slice(0, Math.min(5, row.top_n));
    rankTrendTitle.value = `「${row.keyword}」排名趋势`;
    rankTrendLabels.value = data.map((s) => new Date(s.captured_at).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }));
    rankTrendSeries.value = topVideos.map((v, i) => {
      const values = data.map((s) => {
        const found = (s.videos || []).find((x) => x.video_id === v.video_id);
        return found ? found.rank : row.top_n + 1;
      });
      return { name: v.title?.slice(0, 12) || v.video_id, color: LINE_COLORS[i % LINE_COLORS.length], values };
    });
    rankTrendDialog.value = true;
  } catch {
    ElMessage.error("加载趋势失败");
  }
}

function openView() {
  if (props.view === "analytics-videos") loadVideos();
  else if (props.view === "analytics-competitor") loadAnalyses();
  else if (props.view === "analytics-rankings") loadTrackings();
}

watch(() => props.view, openView);
onMounted(openView);
</script>

<template>
  <div>
    <!-- ===================== 视频库 ===================== -->
    <div v-if="view === 'analytics-videos'">
      <el-alert
        title="视频库"
        description="自动关联 AdsPower 上传的视频，或手动添加视频链接；点击「刷新」拉取最新播放/点赞/评论数据，点「趋势」查看指标变化。"
        type="success" :closable="false" class="agent-intro" show-icon
      />
      <el-card shadow="never" class="toolbar-card">
        <div class="toolbar">
          <div class="toolbar-left">
            <el-button type="primary" @click="openAddVideo">手动添加视频</el-button>
            <el-button :loading="syncing" @click="syncVideos">从上传记录同步</el-button>
          </div>
          <div class="toolbar-right">
            <el-button @click="loadVideos()">刷新</el-button>
          </div>
        </div>
      </el-card>
      <el-card shadow="never" class="table-card">
        <el-table :data="videos" size="small" v-loading="videoLoading" empty-text="暂无视频，点「手动添加」或「从上传记录同步」">
          <el-table-column label="缩略图" width="100">
            <template #default="{ row }"><img :src="thumb(row.video_id)" class="video-thumb" alt="" /></template>
          </el-table-column>
          <el-table-column label="标题" min-width="240" show-overflow-tooltip>
            <template #default="{ row }"><a :href="row.video_url" target="_blank" rel="noreferrer" class="video-link">{{ row.title || row.video_id }}</a></template>
          </el-table-column>
          <el-table-column prop="channel_name" label="频道" min-width="130" show-overflow-tooltip />
          <el-table-column label="来源" width="90">
            <template #default="{ row }"><el-tag size="small" :type="row.source === 'auto' ? 'success' : 'info'" effect="plain">{{ row.source_label }}</el-tag></template>
          </el-table-column>
          <el-table-column label="播放" width="100"><template #default="{ row }">{{ number(row.view_count) }}</template></el-table-column>
          <el-table-column label="点赞" width="90"><template #default="{ row }">{{ number(row.like_count) }}</template></el-table-column>
          <el-table-column label="评论" width="90"><template #default="{ row }">{{ number(row.comment_count) }}</template></el-table-column>
          <el-table-column label="更新时间" min-width="150"><template #default="{ row }">{{ datetime(row.snapshot_at) }}</template></el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain :loading="refreshingId === row.id" @click="refreshVideo(row)">刷新</el-button>
              <el-button size="small" @click="showVideoTrend(row)">趋势</el-button>
              <el-button size="small" type="danger" plain @click="deleteVideo(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="videoPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="videoTotal" @current-change="loadVideos" />
      </el-card>
    </div>

    <!-- ===================== 竞品 SEO 分析 ===================== -->
    <div v-else-if="view === 'analytics-competitor'">
      <el-alert
        title="竞品 SEO 分析"
        description="输入关键词，搜索该词下 top N 视频，逐条拆解标题/描述/Tag，并汇总共性规律。分析实时调用 SerpApi + YouTube，可能耗时数秒。"
        type="success" :closable="false" class="agent-intro" show-icon
      />
      <el-card class="create-card" shadow="never">
        <template #header><strong>新建分析</strong></template>
        <el-form :inline="true" @submit.prevent="runAnalyze">
          <el-form-item label="关键词"><el-input v-model="analysisForm.keyword" placeholder="例如：1win promo code" style="width: 240px" /></el-form-item>
          <el-form-item label="国家"><el-select v-model="analysisForm.country" filterable style="width: 140px"><el-option v-for="c in COUNTRIES" :key="c.value" :label="`${c.label} (${c.value})`" :value="c.value" /></el-select></el-form-item>
          <el-form-item label="语言"><el-select v-model="analysisForm.language" filterable style="width: 140px"><el-option v-for="l in LANGUAGES" :key="l.value" :label="`${l.label} (${l.value})`" :value="l.value" /></el-select></el-form-item>
          <el-form-item label="取前 N"><el-input-number v-model="analysisForm.top_n" :min="1" :max="50" /></el-form-item>
          <el-button type="primary" :loading="analyzing" @click="runAnalyze">开始分析</el-button>
        </el-form>
      </el-card>
      <el-card shadow="never" class="table-card">
        <template #header><div class="card-title"><strong>分析历史</strong><el-button size="small" @click="loadAnalyses()">刷新</el-button></div></template>
        <el-table :data="analyses" size="small" v-loading="analysisLoading" empty-text="暂无分析记录">
          <el-table-column prop="keyword" label="关键词" min-width="160" />
          <el-table-column prop="country" label="国家" width="70" />
          <el-table-column prop="language" label="语言" width="80" />
          <el-table-column prop="top_n" label="top N" width="70" />
          <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag size="small" :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" effect="light">{{ row.status_label }}</el-tag></template></el-table-column>
          <el-table-column label="时间" min-width="160"><template #default="{ row }">{{ datetime(row.created_at) }}</template></el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain :disabled="row.status !== 'completed'" @click="viewAnalysis(row)">查看</el-button>
              <el-button size="small" type="danger" plain @click="deleteAnalysis(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="analysisPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="analysisTotal" @current-change="loadAnalyses" />
      </el-card>
    </div>

    <!-- ===================== 排名追踪 ===================== -->
    <div v-else-if="view === 'analytics-rankings'">
      <el-alert
        title="关键词排名追踪"
        description="维护要追踪的关键词，定时（频率在全局设置配置）抓取 top N 排名存快照，点「趋势」查看排名变化；也可点「抓取」手动立即抓一次。"
        type="success" :closable="false" class="agent-intro" show-icon
      />
      <el-card shadow="never" class="toolbar-card">
        <div class="toolbar">
          <div class="toolbar-left"><el-button type="primary" @click="openAddTracking">新增追踪</el-button></div>
          <div class="toolbar-right"><el-button @click="loadTrackings()">刷新</el-button></div>
        </div>
      </el-card>
      <el-card shadow="never" class="table-card">
        <el-table :data="trackings" size="small" v-loading="trackingLoading" empty-text="暂无追踪关键词">
          <el-table-column prop="keyword" label="关键词" min-width="160" />
          <el-table-column prop="country" label="国家" width="70" />
          <el-table-column prop="language" label="语言" width="80" />
          <el-table-column prop="top_n" label="top N" width="70" />
          <el-table-column label="启用" width="80"><template #default="{ row }"><el-switch v-model="row.enabled" @change="toggleTracking(row)" /></template></el-table-column>
          <el-table-column label="快照数" width="80"><template #default="{ row }">{{ row.snapshot_count }}</template></el-table-column>
          <el-table-column label="最近抓取" min-width="150"><template #default="{ row }">{{ datetime(row.last_captured_at) }}</template></el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain :loading="capturingId === row.id" @click="captureTracking(row)">抓取</el-button>
              <el-button size="small" @click="showRankTrend(row)">趋势</el-button>
              <el-button size="small" type="danger" plain @click="deleteTracking(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="trackingPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="trackingTotal" @current-change="loadTrackings" />
      </el-card>
    </div>

    <!-- 视频指标趋势对话框 -->
    <el-dialog v-model="trendDialog" :title="trendTitle" width="720px">
      <LineChart :labels="trendLabels" :series="trendSeries" :height="280" />
    </el-dialog>

    <!-- 排名趋势对话框 -->
    <el-dialog v-model="rankTrendDialog" :title="rankTrendTitle" width="720px">
      <el-alert title="排名越小越靠上（1 为第 1 名）；掉出榜单按最差名次显示。" type="info" :closable="false" style="margin-bottom: 10px" />
      <LineChart :labels="rankTrendLabels" :series="rankTrendSeries" :height="280" :invert-y="true" />
    </el-dialog>

    <!-- 竞品 SEO 详情对话框 -->
    <el-dialog v-model="detailDialog" :title="detailData ? `「${detailData.keyword}」SEO 分析` : '分析详情'" width="900px">
      <div v-if="detailData && detailData.result">
        <el-card v-if="detailData.result.summary" shadow="never" class="seo-summary">
          <template #header><strong>汇总洞察</strong></template>
          <div class="summary-stats">
            <span v-if="detailData.result.summary.avg_title_length != null">标题均长 {{ detailData.result.summary.avg_title_length }}</span>
            <span v-if="detailData.result.summary.avg_desc_length != null">描述均长 {{ detailData.result.summary.avg_desc_length }}</span>
            <span v-if="detailData.result.summary.avg_tags != null">Tag 均数 {{ detailData.result.summary.avg_tags }}</span>
            <span v-if="detailData.result.summary.keyword_in_title_ratio != null">标题含关键词比例 {{ Math.round(detailData.result.summary.keyword_in_title_ratio * 100) }}%</span>
          </div>
          <div v-if="detailData.result.summary.top_tags?.length" class="summary-tags">
            <span class="summary-label">高频 Tag：</span>
            <el-tag v-for="t in detailData.result.summary.top_tags" :key="t" size="small" class="log-tag" type="info">{{ t }}</el-tag>
          </div>
          <ul v-if="detailData.result.summary.insights?.length" class="summary-insights">
            <li v-for="(ins, i) in detailData.result.summary.insights" :key="i">{{ ins }}</li>
          </ul>
        </el-card>
        <el-table :data="detailData.result.videos" border size="small">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="seo-detail">
                <div class="seo-block"><strong>标题（{{ row.seo?.title?.length }} 字符）</strong><span class="seo-meta">关键词开头：{{ row.seo?.title?.has_keyword_start ? '是' : '否' }} · 数字：{{ row.seo?.title?.has_number ? '有' : '无' }} · emoji：{{ row.seo?.title?.has_emoji ? '有' : '无' }} · 大小写：{{ row.seo?.title?.case_style }}</span><p class="seo-text">{{ row.title }}</p></div>
                <div class="seo-block"><strong>描述（{{ row.seo?.description?.length }} 字符）</strong><span class="seo-meta">链接：{{ row.seo?.description?.has_link ? '有' : '无' }} · 时间戳：{{ row.seo?.description?.has_timestamps ? '有' : '无' }} · 关键词密度：{{ row.seo?.description?.keyword_density }}</span><p class="seo-text">{{ row.description || '（无描述）' }}</p></div>
                <div class="seo-block"><strong>Tag（{{ row.seo?.tags?.count }} 个）</strong><span class="seo-meta">含关键词：{{ row.seo?.tags?.keyword_in_tags ? '是' : '否' }}</span><div class="summary-tags"><el-tag v-for="t in (row.tags || [])" :key="t" size="small" class="log-tag" :type="t.includes(' ') ? 'warning' : 'info'">{{ t }}</el-tag></div></div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="rank" label="#" width="50" />
          <el-table-column label="标题" min-width="260" show-overflow-tooltip><template #default="{ row }"><a :href="row.video_url" target="_blank" rel="noreferrer" class="video-link">{{ row.title }}</a></template></el-table-column>
          <el-table-column prop="channel_name" label="频道" min-width="130" show-overflow-tooltip />
          <el-table-column label="订阅" width="90"><template #default="{ row }">{{ number(row.subscriber_count) }}</template></el-table-column>
          <el-table-column label="播放" width="90"><template #default="{ row }">{{ number(row.view_count) }}</template></el-table-column>
          <el-table-column label="点赞" width="80"><template #default="{ row }">{{ number(row.like_count) }}</template></el-table-column>
          <el-table-column label="发布" min-width="130"><template #default="{ row }">{{ datetime(row.published_at) }}</template></el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="暂无分析结果" />
    </el-dialog>

    <!-- 手动添加视频对话框 -->
    <el-dialog v-model="videoDialog" title="手动添加视频" width="520px">
      <el-form label-width="90px">
        <el-form-item label="视频链接" required><el-input v-model="videoForm.video_url" placeholder="https://youtu.be/..." /></el-form-item>
        <el-form-item label="备注"><el-input v-model="videoForm.remark" placeholder="选填" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="videoDialog = false">取消</el-button>
        <el-button type="primary" :loading="videoSaving" @click="saveVideo">添加</el-button>
      </template>
    </el-dialog>

    <!-- 新增排名追踪对话框 -->
    <el-dialog v-model="trackingDialog" title="新增排名追踪" width="520px">
      <el-form label-width="90px">
        <el-form-item label="关键词" required><el-input v-model="trackingForm.keyword" placeholder="例如：1win promo code" /></el-form-item>
        <el-form-item label="国家"><el-select v-model="trackingForm.country" filterable style="width: 100%"><el-option v-for="c in COUNTRIES" :key="c.value" :label="`${c.label} (${c.value})`" :value="c.value" /></el-select></el-form-item>
        <el-form-item label="语言"><el-select v-model="trackingForm.language" filterable style="width: 100%"><el-option v-for="l in LANGUAGES" :key="l.value" :label="`${l.label} (${l.value})`" :value="l.value" /></el-select></el-form-item>
        <el-form-item label="取前 N"><el-input-number v-model="trackingForm.top_n" :min="1" :max="50" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="trackingForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="trackingDialog = false">取消</el-button>
        <el-button type="primary" :loading="trackingSaving" @click="saveTracking">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.video-thumb { width: 80px; height: 45px; object-fit: cover; border-radius: 4px; display: block; }
.video-link { color: #2468c5; text-decoration: none; }
.seo-summary { margin-bottom: 14px; }
.summary-stats { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.summary-stats span { padding: 4px 10px; background: #eef3f8; border-radius: 4px; color: #52606d; font-size: 13px; }
.summary-tags { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.summary-label { color: #606266; font-size: 13px; }
.summary-insights { margin: 0; padding-left: 18px; color: #52606d; font-size: 13px; line-height: 1.7; }
.seo-detail { padding: 10px 16px; background: #f8fafc; }
.seo-block { margin-bottom: 14px; }
.seo-block strong { display: block; margin-bottom: 4px; color: #303133; }
.seo-meta { display: block; color: #909399; font-size: 12px; margin-bottom: 6px; }
.seo-text { margin: 0; color: #52606d; font-size: 13px; white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow: auto; }
</style>
