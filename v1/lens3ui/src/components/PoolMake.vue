<template>
  <v-container class="fill-height">
    <v-col>

    <div class="text-body-2 align-center text-center">Make new bucket pool</div>
    <div>
      <span class="label">Buckets directory (absolute path):</span>
      <input v-model="buckets_directory" size="30" />
    </div>
    <div>
      <span class="label">User:</span>
      <input v-model="user" size="30" disabled />
    </div>
    <div>
      <span class="label">Group:</span>
      <select v-model="group" required="true">
        <option v-for="(g, i) in group_choices" v-bind:selected="i == 0">
          {{g}}
        </option>
      </select>
      <div>
        <v-btn v-on:click="kick_make_pool">Create</v-btn>
      </div>
    </div>

    </v-col>
  </v-container>
</template>

<script lang="ts" setup>
  //
</script>
