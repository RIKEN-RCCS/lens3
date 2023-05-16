<template>
  <v-row>
    <PoolMake v-bind:pool_data="pool_data" />
  </v-row>
</template>

<script lang="ts" setup>
//import PoolDummy from '@/components/PoolDummy.vue';
import PoolMake from '@/components/PoolMake.vue';
//import PoolList from '@/components/PoolList.vue';
//import PoolView from '@/components/PoolView.vue';
import {pool_data} from "@/lens3c";
</script>
