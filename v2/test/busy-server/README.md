# Busy Server Test

## Description

This tests the limit of the number of running backend servers.
Simultaneously accessing many pools exceeding the limit would make
some of the pools in the suspend state, and operations on those pools
are rejected.  This tests such conditions.

The limit of the number of backends is configured by the port range.
A pool will be set to the suspended state, when all the ports have
been used.  The suspended state is kept for a while (a fraction of
"backend_awake_duration"), and then, a pool will be back to the ready
state.

The limit is set small, because the resident set size of a server
process is typically over 1GB.

[prepare_busy_server.py](prepare_busy_server.py) prepares for the busy
server test.  It creates many pools exceeding the limit of backends.
The preparation work itself is used as the busy server test.

Running "prepare_busy_server.py" will take a long time (multiple of
"backend_awake_duration", or tens of minutes), because it will wait
for some backends expire their lifetime.

## "client.json"

Set "pools_count" and "backend_awake_duration" appropriately in the
"client.json" file.  "pools_count" should be something that exceeds
the limit of backends (exceeding by 3 to 5 will be enough).  The limit
is specified by the value of the port range in the Lens3 configuration
("mux-conf.json").  "backend_awake_duration" should be the same value
in the Lens3 configuration ("mux-conf.json").  The
"backend_awake_duration" is the lifetime of a server instance after it
becomes idle.

* __pools_count__: is used in "busy_server_prepare.py".  It is the
  number of pools to be created.
* __backend_awake_duration__: is a wait time; use the value in the
  configuration.
