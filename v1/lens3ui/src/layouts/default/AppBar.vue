<template>
  <v-app-bar flat>
    <v-app-bar-title>
      <v-icon icon="mdi-cog" />
      Lens3 Pool Setting
    </v-app-bar-title>
    <v-spacer></v-spacer>
    <v-col md="2">
      <v-switch v-model="dark" label="Dark mode" @change="() => change_theme(dark)"></v-switch>
    </v-col>
    <v-app-bar-nav-icon>
          <v-icon icon="mdi-menu" />
    </v-app-bar-nav-icon>
  </v-app-bar>
</template>

<script lang="ts">
import {useTheme} from 'vuetify'
export default {
  setup () {
    const theme = useTheme()
    return {
      theme,
      dark: false,
      change_theme: (d) => {
        theme.global.name.value = d ? 'dark' : 'light';
      },
    }
  },
}
</script>
