<template>
  <v-app-bar flat>
    <v-app-bar-nav-icon>
          <v-icon icon="mdi-menu" />
    </v-app-bar-nav-icon>

    <v-app-bar-title>
      <v-icon icon="mdi-cog" />
      Lens3 Pool Setting
    </v-app-bar-title>
    <v-spacer></v-spacer>

    <v-divider inset vertical></v-divider>

    <v-toolbar-items>
      <v-switch v-model="dark" flat
                prepend-icon="mdi-white-balance-sunny"
                append-icon="mdi-moon-waning-crescent"
                @change="() => change_theme(dark)"></v-switch>
    </v-toolbar-items>

    <template v-slot:append>
      <v-btn icon="mdi-dots-vertical"></v-btn>
    </template>
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
      change_theme: (d : any) => {
        theme.global.name.value = d ? 'dark' : 'light';
      },
    }
  },
}
</script>
