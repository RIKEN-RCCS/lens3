<template>
  <v-row>
    <PoolMake v-bind:pool_data="pool_data" />
  </v-row>
  <v-row>
    <PoolList v-bind:pool_data="pool_data" />
  </v-row>
  <v-row>
    <PoolEdit v-bind:pool_data="pool_data" />
  </v-row>
  <Alert v-bind:pool_data="pool_data" />
</template>

<script lang="ts" setup>
import PoolMake from '@/components/PoolMake.vue';
import PoolList from '@/components/PoolList.vue';
import PoolEdit from '@/components/PoolEdit.vue';
import Alert from '@/components/Alert.vue';
import {pool_data} from "@/lens3c";
</script>
