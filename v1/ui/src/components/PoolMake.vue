<template>
  <v-container class="align-center text-center fill-height">
    <div class="text-h5 text-center w-100">Manage Pools</div>
    <v-card variant="outlined" class="ma-4 w-100">
      <v-card-text>
        A pool is a directory where S3 buckets are created. It is
        associated to a MinIO instance. The first thing to do is
        to create a new pool.
      </v-card-text>
    </v-card>

    <v-row align="center">
    <v-spacer />
    <v-card class="w-75 pa-4 ma-4">
      <v-card-title>New pool</v-card-title>
      <v-text-field label="Buckets directory (absolute path)"
                    v-model="pool_data.buckets_directory" />
      <v-text-field label="User" cols="auto"
                    v-model="pool_data.user" readonly />
      <v-select label="Group" cols="auto"
                variant="underlined"
                v-model="pool_data.group" required
                v-bind:items="pool_data.group_choices" />
      <v-tooltip text="Create a pool">
        <template v-slot:activator="{props}">
          <v-btn icon="mdi-plus-circle"
                 v-on:click="kick_make_pool"
                 v-bind="props" />
        </template>
      </v-tooltip>
    </v-card>
    <v-spacer />
    </v-row>
  </v-container>
</template>

<script lang="ts">
export default {
  props: {
    pool_data: {
      type: Object,
      default: () => ({}),
    },
  },
  data() {
    this.pool_data.api_get_user_info();
    console.log("PoolMake.vue: this.pool_data=" + typeof (this.pool_data));
    console.log(this.pool_data);
    return {
    };
  },
  methods: {
    kick_make_pool() {
      console.log("make_pool: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      this.pool_data.api_make_pool();
    },
  },
}
</script>
