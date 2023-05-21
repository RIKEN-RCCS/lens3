<template>
  <v-row>
    <PoolMake v-bind:pool_data="pool_data" />
  </v-row>
  <v-row>
    <PoolList v-bind:pool_data="pool_data" />
  </v-row>
  <v-row>
    <PoolView v-bind:pool_data="pool_data" />
  </v-row>
</template>

<script lang="ts" setup>
import PoolMake from '@/components/PoolMake.vue';
import PoolList from '@/components/PoolList.vue';
import PoolView from '@/components/PoolView.vue';
import {pool_data} from "@/lens3c";
</script>
