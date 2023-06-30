<template>
  <v-card variant="outlined" class="text-body-1 pa-4" min-width="33%">
    <v-card-title>About Lens3</v-card-title>
    <v-card-text density="comfortable">
      <p>
        Lens3 is an S3 service using 3rd-party server program MinIO.
        Lens3 runs multiple MinIO instances at a single access point,
        and forwards S3 requests with regard to the registered
        buckets.
      </p><p>
        For the usage, see the Lens3 user-guide.md in:
        <a href="https://github.com/riken-rccs/lens3/">github.com</a>
      </p><p>
        Lens3's S3 end-point is: {{pool_data.s3_url}}
        <v-btn variant="text" v-on:click="kick_copy_url_to_clipboard">
          (copy link)</v-btn>
      </p><p>
        A simpler UI is available at "ui2/index.html".
      </p><p>
        Lens3 version: {{pool_data.lens3_version}}
</p>
    </v-card-text>
    <v-card-actions>
      <v-btn
        v-on:click="pool_data.menu_visible=false"
        block
        variant="text">
        Close
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
  methods: {
    kick_copy_url_to_clipboard() {
      navigator.clipboard.writeText(this.pool_data.s3_url);
    },
  },
}
</script>
