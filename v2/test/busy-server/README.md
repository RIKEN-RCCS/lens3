# Busy Server Test

## Description

[test_busy_server.py](test_busy_server.py) tests the limit of the
number of running backend servers.  Simultaneously accessing many
pools exceeding the limit would make some of the pools in the suspend
state, and operations on those pools are rejected for a while.  This
tests such conditions.


The limit of simultaneously running servers is configured by the port
range.  A pool will be set to the suspended state, when all the ports
have been used.  The suspended state is kept for a while (a fraction
of "backend_awake_duration"), and then, a pool will be back to the
ready state.  The limit should is set small.  The resident set size of
one server process is typically over 1GB.

Running "test_busy_server.py prepare" prepares for the busy server
test.  It creates many pools exceeding the limit of backends.

Running "test_busy_server.py run" will test servers to run
alternating.

Running "test_busy_server.py" (both prepare and run) will take a long
time, a multiple of "backend_awake_duration" or several minutes,
because it will wait for some backends expire their lifetime.

## "client.json"

The "client.json" file should contain access information to Lens3.  It
can be prepared by copying an example "client-example.json".  See
[Client Setting](../README.md#client-setting) in "v2/test/README.md"
file.

Set "pools_count" and "backend_awake_duration" appropriately in the
"client.json" file.

- __pools_count__: is the number of pools to be created.
- __backend_awake_duration__: is a wait time to access pools.

"pools_count" should be something that exceeds the limit of number of
backends by a few (3 to 5 being sufficient).  The limit is determined
by the port range in the Lens3 configuration ("port_min" and
"port_max" in "mux-conf.json").

"backend_awake_duration" should be the same value in the Lens3
configuration ("backend_awake_duration" in "mux-conf.json").  It is
the lifetime of a server instance after it becomes idle.
