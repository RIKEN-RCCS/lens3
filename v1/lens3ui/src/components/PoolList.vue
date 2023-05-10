<template>
  <v-container class="fill-height">
    <v-responsive class="d-flex align-center text-center fill-height">
      <div class="text-body-2 align-center text-center">Bucket pool list</div>
      <v-col class="pa-1 ma-1 bg-red">
        <v-slide-group v-model="model" center-active=true>
          <v-slide-group-item
            v-for="n in 15"
            :key="n"
            >
            <v-sheet class="pa-3 ma-3">
              <v-table height="30ex">
                <tbody>
                  <tr
                    v-for="item in desserts"
                    :key="item.name"
                    >
                    <td>{{item.name}}</td>
                    <td>{{item.calories}}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-sheet>
          </v-slide-group-item>
        </v-slide-group>
        <v-row class="pa-3">
          <v-spacer></v-spacer>
          <v-btn v-on:click="kick_edit_pool(p)" rounded="xl">Edit</v-btn>
          <v-btn v-on:click="kick_delete_pool(p)" rounded="xl">Delete</v-btn>
          <v-spacer></v-spacer>
        </v-row>
      </v-col>
    </v-responsive>
  </v-container>
</template>

<script lang="ts">
export default {
  data () {
    return {
      desserts: [
        {
          name: 'Frozen Yogurt',
          calories: 159,
        },
        {
          name: 'Ice cream sandwich',
          calories: 237,
        },
        {
          name: 'Eclair',
          calories: 262,
        },
        {
          name: 'Cupcake',
          calories: 305,
        },
        {
          name: 'Gingerbread',
          calories: 356,
        },
        {
          name: 'Jelly bean',
          calories: 375,
        },
        {
          name: 'Lollipop',
          calories: 392,
        },
        {
          name: 'Honeycomb',
          calories: 408,
        },
        {
          name: 'Donut',
          calories: 452,
        },
        {
          name: 'KitKat',
          calories: 518,
        },
      ],
    }
  },
}
</script>
