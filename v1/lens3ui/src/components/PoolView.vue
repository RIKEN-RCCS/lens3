<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <div class="text-body-2 font-weight-light mb-n1">Welcome to</div>
      <h1 class="text-h2 font-weight-bold">Pool View</h1>
      <div class="py-14" />
      <v-row class="d-flex align-center justify-center">

        <p>
          <router-link to="/">Go to Home</router-link>
        </p>
        <p>
          <router-link to="/setting">Go to Setting</router-link>
        </p>
        <p>
          <router-link to="/about">Go to About</router-link>
        </p>

      </v-row>
    </v-responsive>
  </v-container>
</template>

<script lang="ts" setup>
  //
</script>
