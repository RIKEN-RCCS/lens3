<template>
  <v-container class="d-flex align-center text-center fill-height"
               v-if="pool_data.pool_list.length">
    <div class="text-h5 text-center w-100">List Pools</div>
    <v-card variant="outlined" class="w-100 ma-4">
      <v-card-text>
        Pool list is a slider list of the pools. You can select a
        pool by clicking "edit" button (a pencil icon). Or, delete
        one by "delete" button (a trash can).
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
            <v-table density="compact" class="text-left">
              <tbody>
                <tr>
                  <td>uid</td>
                  <td>{{pool_data.pool_list[n]["owner_uid"]}}</td>
                </tr>
                <tr>
                  <td>gid</td>
                  <td>{{pool_data.pool_list[n]["owner_gid"]}}</td>
                </tr>
                <tr>
                  <td>minio-state</td>
                  <td>{{pool_data.pool_list[n]["minio_state"]}}
                    <v-btn
                      variant="plain"
                      v-if="pool_data.pool_list[n].minio_reason!='-'">
                      Reason
                      <v-dialog
                        v-model="pool_data.pool_list[n].dialog"
                        activator="parent"
                        width="auto">
                        <v-card>
                          <v-card-text>
                            {{pool_data.pool_list[n]["minio_reason"]}}
                          </v-card-text>
                          <v-card-actions>
                            <v-btn
                              v-on:click="pool_data.pool_list[n].dialog=false"
                              variant="text"
                              block>
                              Close
                            </v-btn>
                          </v-card-actions>
                        </v-card>
                      </v-dialog>
                    </v-btn>
                  </td>
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
                  <td>internal-id</td>
                  <td>{{pool_data.pool_list[n]["pool_name"]}}</td>
                </tr>
              </tbody>
            </v-table>
            <v-row class="pa-3 ma-1 align-center">
              <v-tooltip text="Edit this pool in a bottom pane">
                <template v-slot:activator="{props}">
                  <v-btn icon="mdi-pencil" variant="plain"
                         v-on:click="kick_edit_pool(n)"
                         v-bind="props" />
                </template>
              </v-tooltip>
              &nbsp;
              <v-tooltip text="Delete this pool (not undoable)">
                <template v-slot:activator="{props}">
                  <v-btn icon="mdi-delete-forever" variant="plain"
                         v-on:click="kick_delete_pool(n)"
                         v-bind="props" />
                </template>
              </v-tooltip>
            </v-row>
          </v-card>
        </v-slide-group-item>
      </v-slide-group>
    </v-col>
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
    //this.pool_data.api_list_pools();
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
