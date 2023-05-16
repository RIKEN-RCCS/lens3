<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <div class="text-body-2 font-weight-light mb-n1">Edit pool</div>
      <v-sheet class="pa-3 ma-3">

        <div>
          <span class="label">BUCKETS</span>
        </div>
        <div>
          <span class="label">New bucket:</span>
          <span>Bucket name:</span>
          <input v-model="bucket_name" size="30" placeholder="bucket name" />
          <span>Bucket policy for public access:</span>
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
          <div v-for="b in list_of_buckets">
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
        <div v-for="k in access_keys_rw">
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
        <div v-for="k in access_keys_ro">
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
        <div v-for="k in access_keys_wo">
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
  data () {
    return {
      access_keys_rw:
[{access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
],
      access_keys_ro:
[{access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
],
      access_keys_wo:
[{access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
 {access_key: "99999", secret_key: "88888", expiration_time: "1970-10-10"},
],
      list_of_buckets: [],
      bucket_name: "bucket0?",
      bucket_policy: "policy-rw?",
      key_expiration_time: "1970-10-12",
    }
  },
}

function kick_make_bucket() {}
</script>
