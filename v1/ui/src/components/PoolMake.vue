<template>
  <v-container class="fill-height">
    <v-col>

      <div class="text-h4 font-weight-bold text-center">New pool</div>
      <div>
        <span class="label">Buckets directory (absolute path): </span>
        <input v-model="pool_data.buckets_directory" size="30" />
      </div>
      <div>
        <span class="label">User: </span>
        <input v-model="pool_data.user" size="30" disabled />
      </div>
      <div>
        <span class="label">Group: </span>
        <select v-model="pool_data.group" required>
          <option v-for="(g, i) in pool_data.group_choices" v-bind:selected="i == 0">
            {{g}}
          </option>
        </select>
        <div>
          <v-btn v-on:click="kick_make_pool" rounded="xl">Create</v-btn>
        </div>
      </div>

    </v-col>
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
