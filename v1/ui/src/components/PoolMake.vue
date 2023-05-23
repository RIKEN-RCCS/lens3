<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">

      <div class="text-h5 text-center">New pool</div>
      <v-card variant="outlined" class="ma-4">
        <v-card-text>
          A pool is a directory where S3 buckets are created. It is
          associated to a MinIO instance. The first thing to do is
          to create a new pool.
        </v-card-text>
      </v-card>
      <v-text-field label="Buckets directory (absolute path)"
                    v-model="pool_data.buckets_directory"
                    class="ma-0" />
      <v-text-field label="User"
                    v-model="pool_data.user" disabled
                    class="ma-0" />
      <v-select label="Group"
                variant="underlined"
                v-model="pool_data.group" required
                v-bind:items="pool_data.group_choices"
                class="ma-0" />
      <v-btn v-on:click="kick_make_pool" rounded="xl"
             class="ma-1">Create</v-btn>

    </v-responsive>
  </v-container>
</template>

<script lang="ts">
export default {
  //props: ["pool_data"],
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
