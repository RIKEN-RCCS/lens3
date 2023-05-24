# Lens3 UI with vuejs+vuetifty

Lens3 UI is created with vuejs+vuetifty.  See
[https://vuejs.org](https://vuejs.org/) and
[https://vuetifyjs.com](https://vuetifyjs.com/en/).

The UI code is stored "v1/src/lenticularis/ui", which is generated by
Vuetify.  They are genetated by running a "vite" build utility in this
directory ("v1/ui") as described below.

## Basic Vuetify build steps

```
% npm create vuetify
% cd ui
% npm install --legacy-peer-deps

% npm run dev
or
% npm run build
or
% npm run lint
```

## Build procedure

A build procedure is as usual.  The files here are derived from the
templates generated by a Vuetify build utility.

(1) Run `npm install --legacy-peer-deps`, which installs dependent
packages (zzmatu is not for sure).  The option "--legacy-peer-deps" is
needed at the time of writing (2023-05-23).

(2) Run `npm run build`, which runs a "vite" build and generates
script files in "v1/src/lenticularis/ui".  The crucial configuration
line (in "vite.config.ts") is the "base".  It makes the paths in the
script as relative ones.

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

Note that adding "minify" makes readable the generated files, and
"rollupOptions" is not to attach hashes to the file names.

(3) Then, run `sh fix-index-for-base-path.sh`, which adds a script
line in v1/src/lenticularis/ui/index.html. It is to tell browsers
about the base-path (it is needed to deal with URL rewrites by a
front-end proxy).  The actual line added is `PLACE_BASE_PATH_HERE`.
This string will be replaced at runtime by the following line (with an
appropriate BASE-PATH value).

```
<script type="text/javascript">const base_path_="BASE-PATH";</script>
```

The BASE-PATH value is taken from the configuration setting.  This
replacement is performed in "api.py".  Modifying the base-path at
runtime is needed to make the UI code deployable.