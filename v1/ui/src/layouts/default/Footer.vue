<template>
  <v-footer class="bg-grey-lighten-1">
    <v-spacer />
    <div class="text-center"> 
      {{pool_data.footer_banner}}
    </div>
    <v-spacer />
  </v-footer>
</template>

<script lang="ts">
export default {
  props: {
    pool_data: {
      type: Object,
      default: () => ({}),
    },
  },
  //setup () {
  //  return {};
  //},
};
</script>
