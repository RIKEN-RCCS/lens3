<template>
  <v-card variant="outlined" class="text-body-1 pa-4" min-width="300">
    <v-card-title>About Lens3</v-card-title>
    <v-card-text class="text-body-1">
      <ul>
        <li>
      Lens3 is a multiplexer to MinIO to service multiple MinIO
      instances at a single access point.
        </li>
        <li>
      For the usage, see the Lens3 User Guide in:
      <a href="https://github.com/riken-rccs/lens3/">github.com</a>
        </li>
        <li>
      S3 is serviced at: {{pool_data.s3_url}}
      <v-btn icon="mdi-clipboard-text" variant="plain"
             v-on:click="kick_copy_url_to_clipboard" />.
        </li>
        <li>
      Lens3 version: {{pool_data.lens3_version}}
        </li>
      </ul>
    </v-card-text>
    <v-card-actions>
      <v-btn
        variant="text"
        v-on:click="pool_data.menu_visible=false" >
        Dismiss
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script lang="ts">
export default {
  props: {
    pool_data: {
      type: Object,
      default: () => ({}),
    },
  },
  //data() {
  //  return {
  //  };
  //},
  methods: {
    kick_copy_url_to_clipboard() {
      navigator.clipboard.writeText(this.pool_data.s3_url);
    },
  },
}
</script>
