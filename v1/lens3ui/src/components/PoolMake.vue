<template>
  <v-container class="fill-height">
    <v-col>

    <div class="text-body-2 align-center text-center">Make new bucket pool</div>
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
        <v-btn v-on:click="pool_data.kick_make_pool">Create</v-btn>
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
      default: () => ({})
    },
  },
  data() {
    console.log("PoolMake.vue: this.pool_data=" + typeof (this.pool_data))
    console.log(this.pool_data);
    return {
    }
  },
}
</script>
