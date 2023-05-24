<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <v-sheet class="pa-3 ma-3" v-if="pool_data.edit_pool_visible">
        <div class="text-h5">Edit pool</div>
        <v-card variant="outlined" class="pa-1 ma-4">
          <v-card-text>Directory: {{pool_data.buckets_directory}}</v-card-text>
        </v-card>

        <v-card class="pa-4 ma-4">
          <div class="text-h6">New bucket</div>
          <v-text-field label="Bucket name"
                        v-model="pool_data.bucket_name" />
          <v-select label="Bucket policy for public access"
                    variant="underlined"
                    v-model="pool_data.bucket_policy" required
                    v-bind:items="['none', 'public', 'upload', 'download']" />
          <v-btn v-on:click="kick_make_bucket" rounded="xl"
                 class="ma-1">
            Create
          </v-btn>
        </v-card>

        <!-- <div class="text-h6">Buckets</div> -->
        <v-table density="compact">
          <thead>
            <tr>
              <th class="text-left">Bucket</th>
              <th class="text-left">Policy</th>
              <th class="text-left">Delete</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in pool_data.buckets">
              <td>
                <input v-model="b.name" size="30" readonly />
              </td>
              <td>
                <input v-model="b.bkt_policy" size="30" readonly />
              </td>
              <td>
                <v-tooltip text="Delete a bucket">
                  <template v-slot:activator="{props}">
                    <v-btn icon="mdi-delete-forever" variant="plain"
                           v-on:click="kick_delete_bucket(b.name)"
                           v-bind="props" />
                  </template>
                </v-tooltip>
              </td>
            </tr>
          </tbody>
        </v-table>

        <v-spacer class="ma-4" />
        <v-card class="pa-4 ma-4">
          <div class="text-h6">New access key</div>
          <v-text-field
            type="date"
            v-bind:min="new Date().toISOString().substring(0, 10)"
            label="Expiration (00:00:00 UTC)"
            v-model="pool_data.key_expiration_time">
          </v-text-field>
          <v-btn v-on:click="kick_make_secret('readwrite')" rounded="xl">
            Create readwrite key
          </v-btn>
          &nbsp;
          <v-btn v-on:click="kick_make_secret('readonly')" rounded="xl">
            Create readonly key
          </v-btn>
          &nbsp;
          <v-btn v-on:click="kick_make_secret('writeonly')" rounded="xl">
            Create writeonly key
          </v-btn>
        </v-card>

        <div v-for="keyset in pool_data.access_key_set">
          <!-- <div class="text-h6">Access keys ({{keyset.policy}})</div> -->
          <v-table density="compact">
            <thead>
              <tr>
                <th class="text-left">Access key ({{keyset.policy}})</th>
                <th class="text-left">Secret key</th>
                <th class="text-left">Expiration</th>
                <th class="text-left">Delete</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in keyset.keys">
                <td>
                  <input v-model="k.access_key" size="22" readonly />
                  <v-tooltip text="Copy access key to clipboard">
                    <template v-slot:activator="{props}">
                      <v-btn icon="mdi-clipboard-text" variant="plain"
                             v-on:click="kick_copy_to_clipboard(k.access_key)"
                             v-bind="props" />
                    </template>
                  </v-tooltip>
                </td>
                <td>
                  <input v-model="k.secret_key" size="50" readonly />
                  <v-tooltip text="Copy secret key to clipboard">
                    <template v-slot:activator="{props}">
                      <v-btn icon="mdi-clipboard-text" variant="plain"
                             v-on:click="kick_copy_to_clipboard(k.secret_key)"
                             v-bind="props" />
                    </template>
                  </v-tooltip>
                </td>
                <td>
                  <input v-model="k.expiration_time" size=10 readonly />
                </td>
                <td>
                  <v-tooltip text="Delete this key (not undoable)">
                    <template v-slot:activator="{props}">
                      <v-btn icon="mdi-delete-forever" variant="plain"
                             v-on:click="kick_delete_secret(k.access_key)"
                           v-bind="props" />
                    </template>
                  </v-tooltip>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-sheet>
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
    kick_make_bucket() {
      console.log("make_bucket: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      const pool = this.pool_data.pool_name;
      const name = this.pool_data.bucket_name;
      const policy = this.pool_data.bucket_policy;
      this.pool_data.api_make_bucket(pool, name, policy);
    },

    kick_delete_bucket(name : string) {
      console.log("delete_bucket: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      const pool = this.pool_data.pool_name;
      this.pool_data.api_delete_bucket(pool, name);
    },

    kick_make_secret(rw : string) {
      console.log("make_secret: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      const pool = this.pool_data.pool_name;
      this.pool_data.api_make_secret(pool, rw);
    },

    kick_delete_secret(key : string) {
      console.log("delete_secret: this.pool_data=" + typeof (this.pool_data));
      console.log(this.pool_data);
      const pool = this.pool_data.pool_name;
      this.pool_data.api_delete_secret(pool, key);
    },

    kick_copy_to_clipboard(v : string) {
      navigator.clipboard.writeText(v);
    },
  },
}
</script>
