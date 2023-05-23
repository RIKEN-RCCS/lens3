<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <div class="text-h5">Pool list</div>
      <v-card variant="outlined" class="pa-1 ma-4">
        <v-card-text>
          A pool list is a slider list of the pools. Select a pool by
          clicking the "edit" button.
        </v-card-text>
      </v-card>
      <v-col class="pa-1 ma-1">
        <v-slide-group v-model="pool_data.pool_list" center-active>
          <v-slide-group-item
            v-for="(_, n) in pool_data.pool_list.length"
            v-bind:key="n">
            <v-card outlined class="ma-4">
              <v-card-item>
                <v-card-title>{{pool_data.pool_list[n]["buckets_directory"]}}</v-card-title>
              </v-card-item>
              <v-table density="compact" height="30ex">
                <tbody>
                  <tr>
                    <td>Directory</td>
                    <td>{{pool_data.pool_list[n]["buckets_directory"]}}</td>
                  </tr>
                  <tr>
                    <td>uid</td>
                    <td>{{pool_data.pool_list[n]["owner_uid"]}}</td>
                  </tr>
                  <tr>
                    <td>gid</td>
                    <td>{{pool_data.pool_list[n]["owner_gid"]}}</td>
                  </tr>
                  <tr>
                    <td>online?</td>
                    <td>{{pool_data.pool_list[n]["online_status"]}}</td>
                  </tr>
                  <tr>
                    <td>enabled?</td>
                    <td>{{pool_data.pool_list[n]["user_enabled_status"]}}</td>
                  </tr>
                  <tr>
                    <td>minio_state</td>
                    <td>{{pool_data.pool_list[n]["minio_state"]}}</td>
                  </tr>
                  <tr>
                    <td>minio_reason</td>
                    <td>{{pool_data.pool_list[n]["minio_reason"]}}</td>
                  </tr>
                  <tr>
                    <td>id</td>
                    <td>{{pool_data.pool_list[n]["pool_name"]}}</td>
                  </tr>
                </tbody>
              </v-table>
              <v-row class="pa-3 ma-1 align-center">
                <v-btn v-on:click="kick_edit_pool(n)" rounded="xl">Edit</v-btn>
                &nbsp;
                <v-btn v-on:click="kick_delete_pool(n)" rounded="xl">Delete</v-btn>
              </v-row>
            </v-card>
          </v-slide-group-item>
        </v-slide-group>
      </v-col>
    </v-responsive>
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
    this.pool_data.api_list_pools();
    return {};
  },
  methods: {
    kick_edit_pool(i : number) {
      console.log("edit_pool: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      this.pool_data.edit_pool(i);
    },
    kick_delete_pool(i : number) {
      console.log("delete_pool: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      const d = this.pool_data.pool_list[i]
      console.log("delete_pool: i=" + i + " id=" + d["pool_name"]);
      this.pool_data.api_delete_pool(d["pool_name"]);
    },
  },
}
</script>
