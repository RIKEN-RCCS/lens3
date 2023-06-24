<template>
  <v-container class="d-flex align-center text-center fill-height"
               v-if="pool_data.edit_pool_visible">
    <div class="text-h5 text-center w-100">Edit a Pool</div>
    <div class="text-h6 text-center w-100">{{pool_data.buckets_directory}}</div>
    <v-card variant="outlined" class="w-100 ma-4">
      <v-card-text>
        Edit pool lists buckets and access keys. You can
        add/delete them.  A bucket name should be unique in all
        pools including ones owned by others. An expiration of an
        access key is limited by the date in the future set by a
        site manager.
      </v-card-text>
    </v-card>

    <!-- BUCKETS -->

    <v-row align="center">
      <v-spacer />
      <v-card class="w-75 pa-4 ma-4">
        <v-card-title>New bucket</v-card-title>
        <v-text-field label="Bucket name"
                      v-model="pool_data.bucket_name" />
        <v-select label="Bucket policy for public access"
                  variant="underlined"
                  v-model="pool_data.bucket_policy" required
                  v-bind:items="['none', 'public', 'upload', 'download']" />
        <v-tooltip text="Create a bucket">
          <template v-slot:activator="{props}">
            <v-btn icon="mdi-folder-plus"
                   v-on:click="kick_make_bucket"
                   v-bind="props" />
          </template>
        </v-tooltip>
      </v-card>
      <v-spacer />
    </v-row>

    <v-table density="compact" class="w-100">
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

    <!-- KEYS -->

    <v-divider v-bind:thickness="5" class="border-opacity-0"></v-divider>
    <v-row align="center">
      <v-spacer />
      <v-card class="w-75 pa-4 ma-4">
        <v-card-title>New access key</v-card-title>
        <v-text-field
          type="date"
          v-bind:min="new Date()"
          label="Expiration (00:00:00 UTC)"
          v-model="pool_data.key_expiration_time">
        </v-text-field>
        <v-btn prepend-icon="mdi-key-plus"
               v-on:click="kick_make_secret('readwrite')">
          Create readwrite key
        </v-btn>
        &nbsp;
        <v-btn prepend-icon="mdi-key-plus"
               v-on:click="kick_make_secret('readonly')">
          Create readonly key
        </v-btn>
        &nbsp;
        <v-btn prepend-icon="mdi-key-plus"
               v-on:click="kick_make_secret('writeonly')">
          Create writeonly key
        </v-btn>
      </v-card>
      <v-spacer />
    </v-row>

    <div v-for="keyset in pool_data.access_key_set" class="w-100">
      <v-spacer />
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
      <v-spacer />
    </div>
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
