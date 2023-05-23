<template>
  <v-app>
    <default-bar />
    <v-main>
      <setting-view />
    </v-main>
    <v-footer ></v-footer>
  </v-app>
</template>

<script lang="ts" setup>
  import DefaultBar from './layouts/default/AppBar.vue'
  //import DefaultView from './layouts/default/View.vue'
  import SettingView from './views/Setting.vue'
</script>
