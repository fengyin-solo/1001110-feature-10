<template>
  <section class="page" data-module="container">
    <header class="page-head">
      <div>
        <h2>集装箱档案管理</h2>
        <p class="page-desc">
          维护在港集装箱档案：箱况清单照旧做登记、筛选与状态流转；
          箱况视图按箱型与箱况等级汇总箱量、四种箱况占比，并单独标出等级异常的箱号。
        </p>
      </div>
      <div class="page-actions">
        <div class="view-tabs" role="tablist">
          <button
            type="button"
            class="tab"
            :class="{ active: view === 'list' }"
            role="tab"
            @click="switchView('list')"
          >
            箱况清单
          </button>
          <button
            type="button"
            class="tab"
            :class="{ active: view === 'condition' }"
            role="tab"
            @click="switchView('condition')"
          >
            箱况视图
          </button>
        </div>
        <button v-if="view === 'list'" class="btn primary" type="button" @click="openCreate">登记集装箱</button>
        <button v-if="view === 'list'" class="btn" type="button" @click="exportRows">导出集装箱档案清单</button>
        <button class="btn" type="button" @click="refreshActive">刷新</button>
      </div>
    </header>

    <!-- 箱况清单（原有理货账目式列表，口径与箱况视图一致） -->
    <template v-if="view === 'list'">
      <div class="stat-row">
        <article v-for="item in stats" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="reload">
        <label v-for="field in filterFields" :key="field" class="filter-item">
          <span>{{ field }}</span>
          <input v-model="filters[field]" :placeholder="`按${field}检索`" />
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">暂无集装箱档案数据，可先登记集装箱</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条集装箱档案记录</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>

    <!-- 箱况视图 -->
    <template v-else>
      <div v-if="conditionError" class="error-panel">
        <p class="error-title">箱况视图数据取不到</p>
        <p class="error-detail">{{ conditionError }}</p>
        <p class="error-hint">箱况清单仍可正常查看，不影响老的理货账目。</p>
        <button class="btn primary" type="button" @click="loadCondition">重试</button>
      </div>

      <template v-else-if="condition">
        <p class="basis-note">
          统计口径：{{ condition.口径 }} · 统计日期 {{ condition.统计日期 }} ·
          在港箱数 <strong>{{ condition.在港箱数 }}</strong>，与箱况清单总数一致。
        </p>

        <h3 class="block-title">四种箱况占比</h3>
        <div class="stat-row share-row">
          <article v-for="item in condition.shares" :key="item.箱况" class="stat-card share-card">
            <div class="share-head">
              <span class="stat-label">{{ item.箱况 }}</span>
              <strong class="share-value">{{ item.数量 }}</strong>
            </div>
            <div class="share-bar">
              <span class="share-fill" :class="`fill-${item.箱况}`" :style="{ width: `${item.占比}%` }"></span>
            </div>
            <span class="share-percent">{{ item.占比 }}%</span>
          </article>
        </div>

        <h3 class="block-title">按箱型 × 箱况等级分布（在港箱量）</h3>
        <table class="data-table condition-table">
          <thead>
            <tr>
              <th>箱型</th>
              <th v-for="column in condition.matrix.columns" :key="column" :class="{ 'abnormal-col': column === '未填写' }">
                {{ column }}
              </th>
              <th>合计</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in condition.matrix.rows" :key="row.箱型">
              <td>{{ row.箱型 }}</td>
              <td
                v-for="(count, index) in row.cells"
                :key="condition.matrix.columns[index]"
                :class="{ 'abnormal-cell': condition.matrix.columns[index] === '未填写' && count > 0 }"
              >
                {{ count }}
              </td>
              <td class="total-cell">{{ row.合计 }}</td>
            </tr>
            <tr v-if="!condition.matrix.rows.length">
              <td :colspan="condition.matrix.columns.length + 2" class="empty-state">暂无在港集装箱数据</td>
            </tr>
          </tbody>
          <tfoot v-if="condition.matrix.rows.length">
            <tr>
              <td>合计</td>
              <td
                v-for="(count, index) in condition.matrix.totals"
                :key="index"
                :class="{ 'abnormal-cell': condition.matrix.columns[index] === '未填写' && count > 0 }"
              >
                {{ count }}
              </td>
              <td class="total-cell">{{ condition.在港箱数 }}</td>
            </tr>
          </tfoot>
        </table>

        <h3 class="block-title">
          箱况等级异常箱号
          <span class="abnormal-count">共 {{ condition.abnormal.length }} 箱</span>
        </h3>
        <table class="data-table condition-table">
          <thead>
            <tr>
              <th>箱号</th>
              <th>箱型</th>
              <th>箱况等级</th>
              <th>检验到期日</th>
              <th>箱况</th>
              <th>异常原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in condition.abnormal" :key="item.箱号" class="abnormal-row">
              <td>{{ item.箱号 }}</td>
              <td>{{ item.箱型 }}</td>
              <td>{{ item.箱况等级 }}</td>
              <td>{{ item.检验到期日 }}</td>
              <td>{{ item.箱况 }}</td>
              <td class="reason-cell">{{ item.异常原因 }}</td>
            </tr>
            <tr v-if="!condition.abnormal.length">
              <td colspan="6" class="empty-state">没有等级为空或与检验到期日对不上的箱子</td>
            </tr>
          </tbody>
        </table>

        <footer class="page-foot">
          <span>{{ condition.等级口径 }}</span>
        </footer>
      </template>

      <div v-else class="loading-state">正在读取箱况视图数据…</div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type MatrixRow = { 箱型: string; cells: number[]; 合计: number }
type ShareRow = { 箱况: string; 数量: number; 占比: number }
type AbnormalRow = {
  箱号: string
  箱型: string
  箱况等级: string
  检验到期日: string
  箱况: string
  异常原因: string
}
type ConditionSnapshot = {
  口径: string
  统计日期: string
  在港箱数: number
  等级口径: string
  matrix: { columns: string[]; rows: MatrixRow[]; totals: number[] }
  shares: ShareRow[]
  abnormal: AbnormalRow[]
}

const ENDPOINT = '/api/container'
const columns = ["箱号", "箱型", "箱况等级", "所属船公司", "尺寸规格", "自重", "检验到期日", "箱体状态"]
const actions = ["登记检验", "标记可周转", "报废箱体"]
const statuses = ["待检", "可周转", "待修", "已报废"]
const stats = [{"label": "在册箱量", "value": 0}, {"label": "待修箱量", "value": 0}, {"label": "检验到期箱量", "value": 0}]

const view = ref<'list' | 'condition'>('list')
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const condition = ref<ConditionSnapshot | null>(null)
const conditionError = ref('')

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '集装箱登记入口尚未接入审批流'
}

function switchView(next: 'list' | 'condition') {
  view.value = next
  void refreshActive()
}

function refreshActive() {
  if (view.value === 'condition') {
    void loadCondition()
  } else {
    void reload()
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('集装箱档案动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '集装箱档案操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('集装箱列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '集装箱档案列表读取失败'
  }
}

async function loadCondition() {
  conditionError.value = ''
  condition.value = null
  try {
    const response = await request(`${ENDPOINT}/condition`)
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(payload?.detail ?? `接口返回 ${response.status}，箱况视图未更新`)
    }
    condition.value = (await response.json()) as ConditionSnapshot
  } catch (error) {
    condition.value = null
    conditionError.value = error instanceof Error ? error.message : '箱况视图数据读取失败，请重试'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.view-tabs {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.tab {
  border: none;
  background: #fff;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
}
.tab + .tab {
  border-left: 1px solid var(--border);
}
.tab.active {
  background: var(--brand);
  color: #fff;
}
.basis-note {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--muted);
}
.block-title {
  font-size: 14px;
  margin: 16px 0 8px;
}
.abnormal-count {
  font-size: 12px;
  font-weight: 400;
  color: #b42318;
  margin-left: 6px;
}
.share-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.share-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.share-value {
  font-size: 18px;
}
.share-bar {
  height: 8px;
  border-radius: 4px;
  background: #edf1f6;
  overflow: hidden;
}
.share-fill {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: var(--brand);
}
.fill-待检 { background: #d97706; }
.fill-可周转 { background: #16a34a; }
.fill-待修 { background: #dc2626; }
.fill-已报废 { background: #6b7280; }
.share-percent {
  font-size: 12px;
  color: var(--muted);
}
.condition-table .total-cell,
.condition-table tfoot td {
  font-weight: 600;
  background: #f8fafc;
}
.abnormal-col {
  color: #b42318;
}
.abnormal-cell {
  color: #b42318;
  font-weight: 600;
}
.abnormal-row td {
  background: #fef3f2;
}
.reason-cell {
  color: #b42318;
}
.error-panel {
  background: #fff;
  border: 1px solid #fda29b;
  border-radius: 8px;
  padding: 16px;
  margin-top: 12px;
}
.error-title {
  margin: 0 0 6px;
  color: #b42318;
  font-weight: 600;
}
.error-detail {
  margin: 0 0 4px;
  font-size: 13px;
}
.error-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted);
}
.loading-state {
  padding: 32px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}
</style>
