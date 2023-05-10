import {createRouter, createWebHistory} from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/default/Default.vue'),
    children: [
      {
        path: '',
        name: 'Welcome',
        component: () => import('@/views/Welcome.vue'),
        // route level code-splitting
        // this generates a separate chunk (about.[hash].js) for this route
        // which is lazy-loaded when the route is visited.
        //component: () => import(/* webpackChunkName: "home" */ '@/views/Home.vue'),
      },
    ],
  },
  {
    path: '/setting',
    component: () => import('@/layouts/default/Default.vue'),
    children: [
      {
        path: '',
        name: 'Setting',
        component: () => import('@/views/Setting.vue'),
      },
    ],
  },
  {
    path: '/about',
    component: () => import('@/layouts/default/Default.vue'),
    children: [
      {
        path: '',
        name: 'About',
        component: () => import('@/views/About.vue'),
      },
    ],
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
})

export default router
