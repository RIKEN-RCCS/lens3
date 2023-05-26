<template>
  <v-app>
    <default-bar v-bind:pool_data="pool_data" />
    <v-main>
      <setting-view />
    </v-main>
    <default-footer v-bind:pool_data="pool_data" />
  </v-app>
</template>

<script lang="ts" setup>
  import DefaultBar from './layouts/default/AppBar.vue'
  import SettingView from './views/Setting.vue'
  import DefaultFooter from './layouts/default/Footer.vue'
  import {pool_data} from "@/lens3c";
</script>
