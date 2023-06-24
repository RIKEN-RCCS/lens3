<template>
  <v-dialog
    v-model="pool_data.dialog_text"
    v-if="pool_data.dialog_visible"
    width="auto" >
    <v-card v-bind:text="pool_data.dialog_text">
      <v-card-actions>
        <v-btn block @click="pool_data.dialog_visible=false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
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
    return {};
  },
}
</script>
