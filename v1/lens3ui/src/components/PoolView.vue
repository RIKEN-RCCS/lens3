<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <div class="text-body-2 font-weight-light mb-n1">Edit pool</div>
      <v-sheet class="pa-3 ma-3" v-if="pool_data.edit_pool_visible">

        <div>
          <span class="label">BUCKETS</span>
        </div>
        <div>
          <span class="label">New bucket: </span>
          <span>Bucket name: </span>
          <input v-model="bucket_name" size="30" placeholder="bucket name" />
          <span>Bucket policy for public access: </span>
          <select v-model="bucket_policy" v-bind:required="true">
            <option selected>none</option>
            <option>public</option>
            <option>upload</option>
            <option>download</option>
          </select>
          <button v-on:click="kick_make_bucket">Add bucket</button>
        </div>

        <div>
          <span class="label">Existing buckets and policies</span>
          <div v-for="b in pool_data.buckets">
            <input v-model="b.name" size="30" disabled />
            <input v-model="b.bkt_policy" size="10" disabled />
            <button v-on:click="kick_delete_bucket(b.name)">Delete bucket</button>
          </div>
        </div>

        <div>
          <span class="label">ACCESS KEYS</span>
        </div>
        <div>
          <span class="label">Expiration:</span>
          <input type="date" v-model="key_expiration_time" />
          <span class="label">UTC</span>
        </div>
        <div>
          <span class="label">Access keys (rw)</span>
          <button v-on:click="kick_make_secret('readwrite')">Create key</button>
        </div>
        <div v-for="k in pool_data.access_keys_rw">
          <input v-model="k.access_key" size="22" disabled />
          <button v-on:click="kick_copy_to_clipboard(k.access_key)">Copy</button>
          <input v-model="k.secret_key" size="50" disabled />
          <button v-on:click="kick_copy_to_clipboard(k.secret_key)">Copy</button>
          <span>Expires:</span>
          <input type="datetime" v-model="k.expiration_time" disabled />
          <button v-on:click="kick_delete_secret(k.access_key)">Delete key</button>
        </div>

        <div>
          <span class="label">Access keys (ro)</span>
          <button v-on:click="kick_make_secret('readonly')">Create key</button>
        </div>
        <div v-for="k in pool_data.access_keys_ro">
          <input v-model="k.access_key" size="22" disabled />
          <button v-on:click="kick_copy_to_clipboard(k.access_key)">Copy</button>
          <input v-model="k.secret_key" size="50" disabled />
          <button v-on:click="kick_copy_to_clipboard(k.secret_key)">Copy</button>
          <span>Expires:</span>
          <input type="datetime" v-model="k.expiration_time" disabled />
          <button v-on:click="kick_delete_secret(k.access_key)">Delete key</button>
        </div>

        <div>
          <span class="label">Access keys (wo)</span>
          <button v-on:click="kick_make_secret('writeonly')">Create key</button>
        </div>
        <div v-for="k in pool_data.access_keys_wo">
          <input v-model="k.access_key" size="22" disabled />
          <button v-on:click="kick_copy_to_clipboard(k.access_key)">Copy</button>
          <input v-model="k.secret_key" size="50" disabled />
          <button v-on:click="kick_copy_to_clipboard(k.secret_key)">Copy</button>
          <span>Expires:</span>
          <input type="datetime" v-model="k.expiration_time" disabled />
          <button v-on:click="kick_delete_secret(k.access_key)">Delete key</button>
        </div>
      </v-sheet>

      <v-row class="d-flex align-center justify-center">
        <router-link to="/">Go to Home</router-link>&nbsp;
        <router-link to="/setting">Go to Setting</router-link>&nbsp;
        <router-link to="/about">Go to About</router-link>
      </v-row>
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
      navigator.clipboard.writeText(s);
    },
  },
}
</script>
