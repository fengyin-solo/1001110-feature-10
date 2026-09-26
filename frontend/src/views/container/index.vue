<template>
  <section class="page" data-module="container">
    <header class="page-head">
      <div>
        <h2>集装箱档案管理</h2>
        <p class="page-desc">维护集装箱，围绕箱号、箱型、箱况等级、所属船公司做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记集装箱</button>
        <button class="btn" type="button" @click="exportRows">导出集装箱档案清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="condition-view">
      <header class="view-head">
        <div>
          <h3 class="view-title">箱况视图</h3>
          <p class="page-desc">按箱型与箱况等级汇总在港箱量，与下方箱况清单同源，刷新后两边数字一致。</p>
        </div>
        <button class="btn ghost" type="button" @click="refreshAll">刷新视图</button>
      </header>

      <div v-if="conditionError" class="view-error">
        <span class="error-text">{{ conditionError }}</span>
        <button class="btn" type="button" @click="loadConditionView">重试</button>
      </div>

      <template v-else>
        <div class="stat-row">
          <article v-for="item in statusShare" :key="item.status" class="stat-card">
            <span class="stat-label">{{ item.status }}</span>
            <strong class="stat-value">{{ item.count }} 箱 · {{ item.ratio }}%</strong>
          </article>
        </div>

        <table class="data-table">
          <thead>
            <tr>
              <th>箱型</th>
              <th v-for="grade in grades" :key="grade">箱况 {{ grade }}</th>
              <th>小计</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in matrixRows" :key="row.箱型">
              <td>{{ row.箱型 }}</td>
              <td v-for="grade in grades" :key="grade">{{ row.counts[grade] ?? 0 }}</td>
              <td>{{ row.subtotal }}</td>
            </tr>
            <tr v-if="matrixRows.length" class="total-row">
              <td>合计</td>
              <td v-for="grade in grades" :key="grade">{{ gradeTotals[grade] ?? 0 }}</td>
              <td>{{ conditionTotal }}</td>
            </tr>
            <tr v-if="!matrixRows.length">
              <td :colspan="grades.length + 2" class="empty-state">暂无在港集装箱数据</td>
            </tr>
          </tbody>
        </table>

        <div v-if="issues.length" class="issue-panel">
          <h4 class="issue-title">需核对的箱号（{{ issues.length }}）</h4>
          <ul class="issue-list">
            <li v-for="issue in issues" :key="issue.箱号">
              <span class="issue-no">{{ issue.箱号 }}</span>：{{ issue.原因 }}
            </li>
          </ul>
        </div>
      </template>
    </section>

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
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type ConditionView = {
  total: number
  grades: string[]
  rows: { 箱型: string; counts: Record<string, number>; subtotal: number }[]
  grade_totals: Record<string, number>
  status_share: { status: string; count: number; ratio: number }[]
  issues: { 箱号: string; 原因: string }[]
}

const ENDPOINT = '/api/container'
const columns = ["箱号", "箱型", "箱况等级", "所属船公司", "尺寸规格", "自重", "检验到期日", "箱体状态"]
const actions = ["登记检验", "标记可周转", "报废箱体"]
const statuses = ["待检", "可周转", "待修", "已报废"]
const stats = [{"label": "在册箱量", "value": 0}, {"label": "待修箱量", "value": 0}, {"label": "检验到期箱量", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const grades = ref<string[]>([])
const matrixRows = ref<ConditionView['rows']>([])
const gradeTotals = ref<Record<string, number>>({})
const statusShare = ref<ConditionView['status_share']>([])
const issues = ref<ConditionView['issues']>([])
const conditionTotal = ref(0)
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
    await refreshAll()
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

async function loadConditionView() {
  conditionError.value = ''
  try {
    const response = await request(`${ENDPOINT}/condition-view`)
    if (!response.ok) {
      throw new Error(`箱况视图读取失败（接口返回 ${response.status}）`)
    }
    const payload = (await response.json()) as ConditionView
    grades.value = payload.grades ?? []
    matrixRows.value = payload.rows ?? []
    gradeTotals.value = payload.grade_totals ?? {}
    statusShare.value = payload.status_share ?? []
    issues.value = payload.issues ?? []
    conditionTotal.value = payload.total ?? 0
  } catch (error) {
    conditionError.value = error instanceof Error ? error.message : '箱况视图数据暂时取不到，请稍后重试'
  }
}

async function refreshAll() {
  await Promise.all([reload(), loadConditionView()])
}

onMounted(refreshAll)
</script>
