# Lens3 Sources

## Files

* Lens3-Mux
  * [mux.py](mux.py): Gunicorn entries
  * [multiplexer.py](multiplexer.py): Mux implementation
  * [manager.py](manager.py): a sentinel of MinIO process
  * [spawner.py](spawner.py)
  * [mc.py](mc.py)
  * [pooldata.py](pooldata.py)

* Lens3-Api
  * [api.py](api.py): Gunicorn/Fastapi entries
  * [control.py](control.py): Api implementation

* lens3-admin Command and Service Starter
  * [admintool.py](admintool.py)
  * [start_service.py](start_service.py)

* Utils
  * [table.py](table.py): Redis access routines
  * [yamlconf.py](yamlconf.py)
  * [utility.py](utility.py)

* Lens3-Api UI (generated files by vue.js + vuetify)
  * [ui](ui)

* Alternate Simple Lens3-Api UI
  * [ui2/index.html](ui2/index.html)
  * [ui2/lens3ui.js](ui2/lens3ui.js)

* [makefile](makefile) It includes rules for running pyright.
