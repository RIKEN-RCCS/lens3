<template>
  <v-responsive class="d-flex align-center text-center fill-height">
    <PoolMake v-bind:pool_data="pool_data" />
    <PoolList v-bind:pool_data="pool_data" />
    <PoolEdit v-bind:pool_data="pool_data" />
    <AlertPopup v-bind:pool_data="pool_data" />
  </v-responsive>
</template>

<script lang="ts" setup>
import PoolMake from '@/components/PoolMake.vue';
import PoolList from '@/components/PoolList.vue';
import PoolEdit from '@/components/PoolEdit.vue';
import AlertPopup from '@/components/Alert.vue';
import {pool_data} from "@/lens3c";
</script>
