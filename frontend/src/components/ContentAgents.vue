<script setup>
// 内容生成 Agent 管理：交互逻辑与关键词 Agent 管理一致，只是接口换成 content-agents。
import { onMounted, ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

const agents = ref([]);
const loading = ref(false);

async function loadAgents() {
  loading.value = true;
  try {
    const { data } = await axios.get("/api/content-agents/");
    agents.value = Array.isArray(data) ? data : data.results || [];
  } catch {
    ElMessage.error("加载内容生成 Agent 失败");
  } finally {
    loading.value = false;
  }
}

async function saveAgent(agent) {
  try {
    await axios.patch(`/api/content-agents/${agent.id}/`, { prompt: agent.prompt, enabled: agent.enabled });
    ElMessage.success(`已保存「${agent.name}」`);
  } catch {
    ElMessage.error("保存 Agent 失败");
  }
}

async function resetAgentPrompt(agent) {
  try {
    const { data } = await axios.get(`/api/content-agents/${agent.id}/default_prompt/`);
    if (!data.prompt) return ElMessage.warning("该 Agent 没有系统默认提示词");
    agent.prompt = data.prompt;  // 只填回编辑框，需点保存才写库
    ElMessage.success("已载入系统默认提示词，确认后请点击保存");
  } catch {
    ElMessage.error("获取默认提示词失败");
  }
}

onMounted(loadAgents);
</script>

<template>
  <div>
    <el-alert
      title="内容生成 Agent 管理"
      description="两个 Agent 的名称和用途固定，这里只编辑它的提示词。占位符 [input] 会替换成关键词，[output] 会替换成固定的 JSON 输出格式说明（请勿删除）。"
      type="success"
      :closable="false"
      class="agent-intro"
      show-icon
    />
    <div v-loading="loading">
      <el-card v-for="agent in agents" :key="agent.id" shadow="never" class="agent-card">
        <template #header>
          <div class="agent-card-head">
            <div class="agent-card-meta">
              <el-tag size="small" type="warning" effect="plain">{{ agent.agent_type_label }}</el-tag>
              <strong class="agent-card-name">{{ agent.name }}</strong>
              <span class="agent-card-desc">{{ agent.description }}</span>
            </div>
            <el-switch v-model="agent.enabled" active-text="启用" inactive-text="停用" inline-prompt />
          </div>
        </template>
        <el-form label-position="top">
          <el-form-item label="提示词（Prompt）">
            <el-input v-model="agent.prompt" type="textarea" :autosize="{ minRows: 10, maxRows: 30 }" placeholder="留空则使用系统内置默认提示词" />
            <small class="agent-hint">占位符：[input] 自动替换为关键词，[output] 自动替换为固定的 JSON 输出格式说明（这两个请勿删除）。</small>
          </el-form-item>
          <el-button type="primary" @click="saveAgent(agent)">保存提示词</el-button>
          <el-button plain @click="resetAgentPrompt(agent)">恢复系统默认</el-button>
        </el-form>
      </el-card>
      <el-empty v-if="!loading && agents.length === 0" description="暂无 Agent 配置" />
    </div>
  </div>
</template>
