<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { galleryApi } from './api'

const route = useRoute()
const tokenOpen = ref(false)
const token = ref('')
const tokenDialog = ref<HTMLDialogElement | null>(null)
const navigation = [
  { to: '/library', label: '资产整理', hint: '浏览、筛选与批量管理' },
  { to: '/review', label: '待审核', hint: '连续打标与人工确认' },
  { to: '/taxonomy', label: '标签体系', hint: '整理图片标签与旧标签' },
  { to: '/diagnostics', label: '检索诊断', hint: '验证聊天语境候选' },
]

function saveToken() {
  galleryApi.token = token.value.trim()
  closeToken()
}

function closeToken() {
  tokenDialog.value?.close()
  tokenOpen.value = false
}

watch(tokenOpen, async (open) => {
  await nextTick()
  if (open && tokenDialog.value && !tokenDialog.value.open) tokenDialog.value.showModal()
  if (!open) tokenDialog.value?.close()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-glow" aria-hidden="true"></div>
      <div class="brand"><div class="brand-mark"><span>P</span></div><div><strong>Plana Gallery</strong><span>本地语境图库</span></div></div>
      <nav aria-label="图库主导航">
        <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-item" :class="{ active: route.path === item.to }">
          <strong>{{ item.label }}</strong><span>{{ item.hint }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer"><div class="local-badge"><i aria-hidden="true"></i>Local-only runtime</div><button type="button" class="button ghost full" @click="tokenOpen = true">访问设置</button><small>图片与元数据仅保存在本机</small></div>
    </aside>
    <main class="workspace"><RouterView /></main>
    <dialog ref="tokenDialog" class="modal-dialog" aria-labelledby="token-title" @cancel.prevent="closeToken" @close="tokenOpen = false">
      <form class="modal-card" @submit.prevent="saveToken">
        <header class="dialog-header"><div><span>访问设置</span><h2 id="token-title">管理 API Token</h2></div><button type="button" class="icon-button" aria-label="关闭设置" @click="closeToken">×</button></header>
        <label>Token<input v-model="token" type="password" autocomplete="off" placeholder="仅在当前页面内存保存" /></label>
        <p class="hint">Token 不会写入浏览器存储，刷新页面后自动清除。</p>
        <footer class="dialog-actions"><button type="button" class="button ghost" @click="closeToken">取消</button><button type="submit" class="button primary">应用</button></footer>
      </form>
    </dialog>
  </div>
</template>
