import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import LibraryView from './views/LibraryView.vue'
import ReviewView from './views/ReviewView.vue'
import TaxonomyView from './views/TaxonomyView.vue'
import DiagnosticsView from './views/DiagnosticsView.vue'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/views.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/library' },
    { path: '/library', component: LibraryView },
    { path: '/review', component: ReviewView },
    { path: '/taxonomy', component: TaxonomyView },
    { path: '/diagnostics', component: DiagnosticsView },
  ],
})

createApp(App).use(router).mount('#app')
