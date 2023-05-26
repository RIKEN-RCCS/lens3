<template>
  <v-app-bar flat>
    <v-menu v-model="pool_data.menu_visible"
            v-bind:close-on-content-click="false"
            location="bottom">
      <template v-slot:activator="{props}">
        <v-app-bar-nav-icon v-bind="props">
          <v-icon icon="mdi-menu" />
        </v-app-bar-nav-icon>
      </template>
      <about-menu v-bind:pool_data="pool_data" />
    </v-menu>
    <v-app-bar-title>
      <v-icon icon="mdi-cog" />
      Lens3 Pool Manager
    </v-app-bar-title>

    <v-spacer></v-spacer>

    <v-toolbar-items>
      <v-switch v-model="dark" flat
                prepend-icon="mdi-white-balance-sunny"
                append-icon="mdi-moon-waning-crescent"
                @change="() => change_theme(dark)"></v-switch>
    </v-toolbar-items>
    <template v-slot:append>
      <v-btn icon="mdi-dots-vertical" disabled></v-btn>
    </template>
  </v-app-bar>
</template>

<script lang="ts">
import {useTheme} from "vuetify";
import AboutMenu from '@/components/About.vue';
export default {
  props: {
    pool_data: {
      type: Object,
      default: () => ({}),
    },
  },
  components: {
    AboutMenu: AboutMenu,
  },
  setup() {
    const theme = useTheme()
    return {
      theme,
      dark: false,
      change_theme: (d : any) => {
        theme.global.name.value = d ? "dark" : "light";
      },
    };
  },
};
</script>
