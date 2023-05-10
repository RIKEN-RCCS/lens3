<template>
  <v-col>
    <PoolMake />
  </v-col>
  <v-col>
    <PoolList />
  </v-col>
  <v-col>
    <PoolView />
  </v-col>
</template>

<script lang="ts" setup>
  import PoolMake from '@/components/PoolMake.vue'
  import PoolList from '@/components/PoolList.vue'
  import PoolView from '@/components/PoolView.vue'
</script>
