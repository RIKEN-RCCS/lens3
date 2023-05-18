<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <div class="text-body-2 align-center text-center">Bucket pool list</div>
      <v-col class="pa-1 ma-1 bg-red">
        <v-slide-group v-model="pool_data.pool_list" center-active>
          <v-slide-group-item
            v-for="(_, n) in pool_data.pool_list.length"
            v-bind:key="n" >
            <v-sheet class="pa-3 ma-3">
              <v-table height="30ex">
                <tbody>
                  <tr>
                    <td>index: </td>
                    <td>{{n}}</td>
                  </tr>

                  <tr>
                    <td>name: </td>
                    <td>{{pool_data.pool_list[n]["pool_name"]}}</td>
                  </tr>
                  <tr>
                    <td>Directory: </td>
                    <td>{{pool_data.pool_list[n]["buckets_directory"]}}</td>
                  </tr>
                  <tr>
                    <td>uid: </td>
                    <td>{{pool_data.pool_list[n]["owner_uid"]}}</td>
                  </tr>
                  <tr>
                    <td>gid: </td>
                    <td>{{pool_data.pool_list[n]["owner_gid"]}}</td>
                  </tr>
                  <tr>
                    <td>online_status: </td>
                    <td>{{pool_data.pool_list[n]["online_status"]}}</td>
                  </tr>
                  <tr>
                    <td>user_enabled_status: </td>
                    <td>{{pool_data.pool_list[n]["user_enabled_status"]}}</td>
                  </tr>
                  <tr>
                    <td>minio_state: </td>
                    <td>{{pool_data.pool_list[n]["minio_state"]}}</td>
                  </tr>
                  <tr>
                    <td>minio_reason: </td>
                    <td>{{pool_data.pool_list[n]["minio_reason"]}}</td>
                  </tr>
                  <tr>
                    <td>modification_time: </td>
                    <td>{{pool_data.pool_list[n]["modification_time"]}}</td>
                  </tr>
                </tbody>
              </v-table>
              <v-row class="pa-3">
                <v-spacer></v-spacer>
                <v-btn v-on:click="kick_edit_pool(n)" rounded="xl">Edit</v-btn>
                <v-btn v-on:click="kick_delete_pool(n)" rounded="xl">Delete</v-btn>
                <v-spacer></v-spacer>
              </v-row>
            </v-sheet>
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
      default: () => ({})
    },
  },
  data() {
    this.pool_data.api_list_pools();
    return {};
  },
  methods: {},
}
</script>
