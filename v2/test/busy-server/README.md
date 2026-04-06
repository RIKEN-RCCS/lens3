# Busy Server Test

[test_busy_server.py](test_busy_server.py) tests the limitation of the
number of simultaneously running backend servers.  Accessing many
pools exceeding the limit will make some pools in the suspend state,
and operations on those pools are rejected for a short period (a few
minutes).  This tests such conditions.

NOTICE: THIS TEST WILL TAKE A LONG TIME.

## Limit of Simultaneously Running Backends

The limit of simultaneously running backends is configured by the
network port range.  A pool will be set to the suspended state, when
all the ports have been used.  The suspended state is kept for a
fraction of "backend_awake_duration" time, and after that period, a
pool will be back to the ready state.

The limit of simultaneously running backends should be set small by
considering the resident set size of each S3 server process, which is
typically over 1GB.

## Running the Test

It needs Python library "boto3".  It should be installed, maybe, by
running "make install-boto3".  See
[Python Setting](../README.md#python-setting) in "v2/test/README.md"
file.

The "client.json" file contains the test setting.  It is prepared by
copying an example file "client-example.json".  See
[Client Setting](../README.md#client-setting) in "v2/test/README.md"
file.

It is requred to create a number of directories in the directory
specified by "poolpool".  Names of directories are "pool"+nnn where
nnn is three digit number from 0 to n_pools-1.

```
bash make-directoris.sh pool-pool-directory number-of-directories
```

Set "poolpool", "pools_count", and "backend_awake_duration"
appropriately in the "client.json" file.

  - __poolpool__ is the directory where pools are created.
  - __pools_count__ is the number of pools to be created.
  - __backend_awake_duration__ is a wait time to access pools.

"pools_count" should be something that exceeds the limit of number of
backends by a few (3 to 5 being sufficient).  The limit is determined
by the port range in the Lens3 configuration ("port_min" and
"port_max" in "mux-conf.json").

"backend_awake_duration" should be the same value in the Lens3
configuration ("backend_awake_duration" in "mux-conf.json").  It is
the lifetime of a server instance after it becomes idle.

  - Running "test_busy_server.py prepare" prepares for the busy server
    test.  It creates many pools specified by "pools_count".

  - Running "test_busy_server.py destory" will delete pools created in
    prepare operation.

  - Running "test_busy_server.py run" will test servers by accesses
    the pools cyclically.

```
python3 test_busy_server.py prepare
python3 test_busy_server.py run
python3 test_busy_server.py destory
```

Running "test_busy_server.py" (both "run" and "prepare") will take a
long time.  It is because it will wait for backends expire their
lifetime, ("backend_awake_duration" or several minutes).
