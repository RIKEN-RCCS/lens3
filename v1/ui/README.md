# Lens3 UI with vuejs+vuetify

Lens3 UI is created with vuejs+vuetify.  See
[https://vuejs.org](https://vuejs.org/) and
[https://vuetifyjs.com](https://vuetifyjs.com/en/).

The UI code is stored "$TOP/v1/src/lenticularis/ui", which is
generated by Vuetify.  They are genetated by running a "vite" build
utility in this directory ("$TOP/v1/ui") as described below.

## Prerequisites: Newer nodejs and npm

vuejs+vuetifty requires much newer versions of "nodejs" and "npm" than
the ones in the standard dnf repository in RedHat/Rocky.  While Rocky
8.8 is distributing nodejs 10.x, the latest is nodejs 20.x at this
writing (September 2023).

See the sections "Installation Instructions" in
[https://github.com/nodesource/distributions](https://github.com/nodesource/distributions).
The below is a copy of the instructions (for Redhat), where it is
changed to use dnf in place of yum:

```
# dnf install https://rpm.nodesource.com/pub_20.x/nodistro/repo/nodesource-release-nodistro-1.noarch.rpm
# dnf install nodejs --setopt=nodesource-nodejs.module_hotfixes=1
```

## Building Vuetify Application

Running "make build" runs Vuetify's build procedure and a post-build
procedure.

```
$ cd $TOP/v1/ui
$ make build
```

## Vuetify Application Build Procedure

The "ui" directory contains a Vuetify application.  It is derived from
template files generated by running `npm create vuetify`.  A build
generates files in "$TOP/v1/src/lenticularis/ui".

```
$ cd $TOP/v1/ui
$ npm install
$ npm run dev or build or lint
```

A build procedure is as usual.

Kicking `npm run build` runs a "vite" build and generates files in
"$TOP/v1/src/lenticularis/ui".  The crucial configuration line in
"vite.config.ts" is the "base=./" setting.  It makes the paths in the
generated scripts relative ones.  Others are minor.  Adding
"minify=false" makes the generated files readable, and the
"rollupOptions" setting disables attaching hash strings to file names.

```
build: {
  outDir: "../src/lenticularis/ui",
  minify: false,
  emptyOutDir: true,
  rollupOptions: {
    output: {
      entryFileNames: `assets/[name].js`,
      chunkFileNames: `assets/[name].js`,
      assetFileNames: `assets/[name].[ext]`
    }
  },
},
base: "./",
```

## Post Build Procedure

After a build, run `sh fix-index-for-base-path.sh`, which adds a
script line in "$TOP/v1/src/lenticularis/ui/index.html".  It is to
tell the JavaScript code about the base-path -- it is needed to deal
with URL rewrites by a front-end proxy.  The actual line added is
`PLACE_BASE_PATH_HERE`.  This string will be replaced at runtime by
the following line (with an appropriate BASE-PATH value).

```
<script type="text/javascript">const base_path_="BASE-PATH";</script>
```

The BASE-PATH value is taken from the configuration setting.  This
replacement is performed in "api.py".  Modifying the base-path at
runtime is necessary to make the UI code deployable.

## Updating Vuetify

Updating Vuetify can be done by the following.  It works even if the
version is fixed to one explicitly specified.

```
$ npm install vuetify@latest --save
$ npm outdated
$ npm update --save
```

## ~~Note on the Date Picker~~

_The following description does not apply any more.  "v-date-picker"
is generally available since Vuetify 3.4.0._

A build for Lens3-v1.2.1 uses a specific version of Vuetify 3.3.15,
that should be 3.3.4 and later.  It is because it uses an
early-release, the "labs", version of "v-date-picker" component.  It
is explicitly fixed in "package.json".

```
  "dependencies": {... "vuetify": "3.3.15", ...}
```

When "v-date-picker" will be generally available as a production-ready
component in the future, it is necessary to remove the import
statement from the source code.  The code should look like below.

```
<script lang="ts" setup>
    import {VDatePicker} from 'vuetify/labs/VDatePicker'
</script>
```
