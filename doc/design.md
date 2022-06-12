# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

* Components
  * Multiplexer
  * Controller

   * MinIO instances (S3 compatible server function)
      --Launched from manager
      --The S3 compatible server function uses MinIO (`https://min.io/`).
      --MinIO adds and uses MinIO User.
        --MINIO_ROOT can only be accessed by the system and the administrator.

  + Management function
    --Has a management function using management commands
    --Access Redis directly and work with tables
    --Throw decoy to manager to operate minio

  + Public access function
    --Function to access the bucket set to public
    --Realized by sorting by direct hostname
      --Since sorting by Access Key cannot be used

  + Table
    --Use Redis

  + Supports load balancer
    --Because all multiplexers and controllers work together
      Share the Routing Table

  + Log function
    --Send to syslog (via journald)

  + Fault tolerance
    ――Somewhat.
    --MinIO is not multiplexed.
    --Redis is not multiplexed. (This is a single point of failure)

  + Availability
    --Good (best effort)

  + Maintenance
    --Automatic maintenance of minio, mc, dependent software (security patch,
      (Update etc.) No function is provided. According to the maintenance procedure of each software
      Shall be.

  + Time to live of each component
    --The process that keeps running from the start to the end of the service
      --Front end (reverse proxy)
      --gunicorn (for multiplexer, for WebUI API)
      --Redis
    --A process that is started as needed and keeps running until killed
      --manager
      --MinIO
    --Process threads that run only when needed
      --Multiplexer (per HTTP session, gunicorn thread)
      -scheduler (for each session not registered in the Routing Table.)
        In the implementation, the same thread as the multiplexer)
      --WebUI service (gunicorn thread)
      --Administrator CLI

### Multiplexer

      --Distribution by Access Key ID
      --Sort by host name (⇒Public access function)
      --All multiplexers must be reachable to all MinIO nodes.
        --The transfer destination MinIO is started on the same node as the multiplexer.
          Not exclusively.

### Subcomponents of a Controller

A Controller starts a MinIO instance and manages its life-time.

* Subcomponents of a Controller
  * Scheduler
        --Plan the node to start MinIO.
          When starting MinIO on its own node, the manager is in charge of the actual start.
          Scheduler is the python code in the same process as the multiplexer.
  * Manager
        --Responsible for starting MinIO. The manager is started by Popen from the scheduler,
          It will be a separate process (python program). This process is MinIO
          It starts and the process monitors MinIO's life and death.
        --Register your own information in the manger list.
        --Auto start: Called on demand when accessed.
          Scheduler makes the decision to start. The Manager determines the suppression of multiple startups.
        --Automatic stop: Stops if there is no access for a certain period of time
           Stops when the specified deadline expires
           Stops when "offline" is set by user or administrator operation
           Stops when an administrator puts a user in the Deny list ("disabled")
           Stop when your entry disappears from the Manager list


### Multiplexer

  + Basic functions
    --Forward S3 connections to MinIO according to the Routing Table (accessKeyID / direct Hostname)
    --Record the S3 connection time in the Routing Table (atime)

  + Start
    --Obtain the standby address of the multiplexer on the local node from the configuration file
    --`lenitcularis.mux` in` /etc/lenticularis/mux-config.yaml`
      Is registered in the Multiplexer Table.
      The key is `mx:` + "lenticularis". "Mux". "Host" + ":" +
        "Lenticularis". "mux". "port" + pid

  + End
      Deleted own entry from Multiplexer Table.

  + Basic operation preparation

    1. Check if `REMOTE_ADDR` is included in` trusted_hosts`, `multiplexer`.
      --`trusted_hosts`,` multiplexer` are converted to IP Address with `getaddrinfo`
        Then compare
        --Compare IPv6 projected addresses after converting to IPv4
      --No negative cache.
        --The possibility of over-rejection cannot be ruled out: Causes a Type II error.

    2. Get the HTTP Host header. Compare with facade hostname. (case insensitive)
      --Goto 4; if there is no Host header (not direct hostname)
      --goto 3; if not direct hostname (if direct hostname)
      --goto 4; for direct hostname (not direct hostname)

    3. Access with direct hostname
      --If Host is not facade hostname, Host is the key and Routing Table
        Look up (directHostname) and extract MinIO Address. Get MinIO Address
        If you go to 6;
      --otherly goto 5;
        --MinIO corresponding to direct hostname in Routing Table (directHostname)
         Address is not registered.
        --At this stage, the direct hostname is registered in the Storage Pool Table (main).
          Do not check if it is done. After that, verify with the controller.
        --Even if `AWS4-HMAC-SHA256` used in Authorization is specified in the previous section
          If you reach this section, 3 will not be activated. This operation has priority.
          When accessing the wrong direct hostname with Authorization
          To make an error.
      --Joined direct_hostname_domain to Routing Table (directHostname)
        The FQDN direct hostname is registered.
      --Intended to be able to handle multiple direct_hostname_domains in the future.

    4. Access by Access Key ID
      --If there is no Host or if it is a facade hostname:
      --From the HTTP header `Authorization:`, `AWS4-HMAC-SHA256 Credential =`
        (Hereafter, S3 Authorization) followed by Access Key ID (until immediately before "` / `"
        Part) is extracted and used as the Access Key ID.
        --A different concept from the Authorization used by the Web UI for authentication
      --Error 404 if `Authorization:` is missing or does not match the above format
        `https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-auth-using-authorization-header.html`
      --If the Access Key ID is obtained, use the Access Key ID as the key and use the Routing Table.
        Look up (accessKeyID) and extract MinIO Address. MinIO Address was obtained
        If go to 6;
        If you do not get an Access Key ID, proceed as None.
      --otherly goto 5;
        --The Routing Table (accessKeyID) has the MinIO Address corresponding to the Access Key ID.
          not registered.

    5. If MinIO Address is not registered
      --Call the controller. There are two patterns of triggers:
        --Access with direct hostname could not be resolved.
          In this case, do not pass the Access Key ID (if any).
          You don't even have to hand it over.
        --Access with Access Key ID could not be resolved.
      --The controller returns MinIO Address.
        --An error is returned if MinIO fails to start. error 404
      --goto 6;

    6. Transfer
      --Updated Routing Table (atime). The key is MinIO Address.
      --Forward to MinIO Address.

    --About simultaneous incoming calls
      --Same Access Key ID to other multiplexers when not registered in the route table
        Sessions may arrive at about the same time, but as a multiplexer
        It is don't care.
      --This case is handled exclusively by the controller.
      --If you have already registered in the route table, there is no problem with simultaneous incoming calls.

    --Handling of HTTP headers
      --The front end should not change the `Host:` contained in the HTTP header.
        -(Reference) Set so that `Host` is not changed by reverse proxy:
        `` ```
        proxy_set_header Host $ http_host; --NGINX
        ProxyPreserveHost on --Apache2
        `` ```

    --Differences between design concept and implementation
      --The design concept is that the controller also transfers HTTP sessions,
        In the implementation, the controller returns control to the router after starting MinIO,
        It is assumed that the router forwards the HTTP session.

  + Malfunction of transfer destination
    --Access Key ID is registered in the Routing Table, but it does not respond correctly
      What to do if
      --When the connection to MinIO times out ⇒
        --Returns error 503 connection timeout to the client.
        --The controller purges the MinIO.
      --Connect but do not respond to HTTP (for example, there is an application other than MinIO)

  + Standby port
    --This application is implemented as wsgi app, and the standby port is connected from the front end.
      I assume that you will.
    --This application does not support UNIX domains.
      --In NGINX, it is possible to communicate with wsgi waiting in the UNIX domain, but in this implementation
        This function is not supported.

  + Multiple launches of multiplexer
    --Multiplexers can be started multiple times.
    --The front end attaches the HTTP session to any multiplexer
      You may transfer it. (Especially when operating as a load balancer)

  + Multiplexer list
    --The front end (reverse proxy) does not see this table. Front end
      The rules are described separately by the system administrator.
    --The multiplexer list is created automatically.
      -multiplexer deletes entry with atexit.
      --Even if it ends (crashes) shortly after executing atexit, it disappears after a certain period of time.
    --Renew your registration at regular intervals.
      --Constant time: watchdog_timer + jitter
      --When the entire table is forcibly deleted, it will be re-registered after a certain period of time.
      --Scheduling changes until the entire table is regenerated.
      --The redis timed feature deletes entries if they can't be updated.

  + mc communication
    --The multiplexer also transparently passes mc communication.
    --Because mc includes S3 Authorization in the HTTP header
      The process is the same as normal S3 access.

  + Security
    --IP address restriction (access permission) setting function:
      --List the nodes that are allowed access to `trusted_hosts`.
        --Host name or address
      --multiplexers registered with redis are considered `trusted_hosts`.
        --There is no need to write it in the configuration file.
    --Multiplexer--Because the connection between controllers is implemented as the same process
      No special measures will be taken. (No need to connect)
    --Use syslog to save Apache's combined equivalent logs.
      --The port of the other party cannot be recorded.
        The front end should be set to log the other party's port as well.
    --DoS measures
      --Front-end load balancer, things that NGINX / Apache2 cannot prevent:
        --Connect with a random Access Key ID
        --Connect with a random direct hostname
        --Connect but send nothing until timed out

  + Activity monitoring
    --Update the Routing Table (atime) every time there is a session connection.

  + Implementation
    --The multiplexer is implemented with gunicorn + wsgi.
    --Implemented as the same process (app) as the controller.

### Manager

  + Overview
    --Manager mainly starts / monitors / stops MinIO
      Responsible for updating the Routing Table and MinIO Address Table

  + Basic functions
    --The manager itself has the same UID as the UID running wsgi (hereafter,
      It works with lenticularis_admin authority).
    --manager: `setuid (2)` to the specified user privileges and start MinIO.
      --In the implementation, create a small program that wraps `sudo`,
        Or use a small program with `chmod u + s`
      --When using `sudo`, allow only MinIO to be executed in` sudoers.d`.
        --When using `sudo`, the` lenticuralis_admin` privilege should be `setuid (2)`
          It doesn't have to be feasible.
    --Environment variables to save (if unset, do not add)
      `` ```
      HOME HOME
      LANG
      LC_CTYPE
      LOGNAME
      PATH
      SHELL
      USER
      USERNAME
      `` ```

    --Environment variables to add (overwrite if existing)
      `` ```
      MINIO_ROOT_PASSWORD
      MINIO_ROOT_USER
      MINIO_HTTP_TRACE
      MINIO_BROWSER
      `` ```

    --Command: `python3 -m lenticularis.mux.manager args ...`
    --Implementation language: python
    -Parameters passed from scheduler
      --Pool ID (mandatory)
        --Passing environment variables LENTICULARIS_POOL_ID
      --multiplexer node name (1st positional parameter)
      --The range of ports assigned to MinIO (mandatory)
        --Passed by command line (2nd and 3rd positional parameters)
        --lower (inclusive) upper (inclusive)
      --The address of the multiplexer in charge (mandatory)
        --Passed by command line (4th positional parameter)
        --Example: 127.0.0.1:8000
      --Configuration file: `--configfile /path/to/mux.conf` (mandatory)
      --Trace ID (for debugging): `--traceid id` (optional)
      --No use of masquerade: `--useTrueAccount` (optional)
        --Registered in Storage Pool Table (main) when starting MinIO
          Use the access key
        --Usually, masquerade.
    --exit status:
      --If MinIO starts successfully: 0
      --If MinIO fails to start: Non-0
    --Output (stdout):
      --If startup fails: Empty
      --If the startup is successful: MinIO's address. host: port.
    --Side effects:
      --If MinIO is successfully started, the MinIO Address Table will be displayed.
        Using the Pool ID as a key, the address of the multiplexer in charge,
        Record MinIO's address, MinIO's pid, and its own pid. Moreover,
        Update the Routing Table according to the above information.

  + Basic operation
    + Start
      --Look up the Storage Pool Table (main) using the Pool ID as a key and start MinIO.
        do.
      --Update MinIO Address Table (Insert)
      --Update the Routing Table
      --Initialize MinIO if there is a request for initialization.
        --Notify the success or failure of initialization via redis
    + End
      --Exit with MinIO termination (`SIGCHLD`) or forced termination (`SIGTERM`)
      --Stop MinIO with mc
        mc admin service stop $ alias
      --Wait MinIO
      --Update the Routing Table
      --Update (delete) MinIO Address Table
    + Surveillance
      --Forcibly stop MinIO that has not been accessed for a certain period of time

  + MinIO startup procedure

    --The Routing Table and MinIO Address Table show that when apoptosis occurs
      It may disappear even if it is locked.

    1. Preparation
      --TIMEOUT = 120
      --When doing masquerade, `MINIO_ROOT_USER`,` MINIO_ROOT_PASSWORD`
        To generate. randomStr ()
      --Otherwise, `MINIO_ROOT_USER = poolID`,
        Set `MINIO_ROOT_PASSWORD = rootSecret`.

    2. Lock the MinIO Address Table

      --try try
        --lock ("lk:" MinIO Address Table, Pool ID, timeout = TIMEOUT)
        --Start (or start / initialize / stop) MinIO within TIMEOUT seconds. goto 3;
        --If the startup cannot be completed within TIMEOUT seconds, the lock will be released.
          Even in that case, record it in the log and proceed first.
      --except
        --I couldn't lock it.
        --Someone should be trying to start MinIO.
        --Someone may be trying to start && close MinIO,
          It is running the controller "MinIO boot procedure"
          No apoptotic procedure is in progress. What if apoptosis
          Since it does not lock, there is no lock conflict.
        --goto 14;

    3. Get parameters from Storage Pool Table (main)
      ――Atomicly, save everything.
      --Judgment of "not starting"
        --Check the status flag ⇒ If it is not "online", "Do not start"
        --Check the permission flag ⇒ If it is not "allowed", "Do not start"
        --Get expiration date (expDate) ⇒ If it expires, "Do not start"
        --Confirm Authorization ⇒ If you access by pool ID, "Do not start"
          JUSTIFICATION: I don't want all MinIO to be running after batch registration.
        --Check mode ⇒ If it is not "ready", "do not start"
        --"Start" == ("online" and "allowed" and "during validity period"
                           And "not pool ID" and "ready")

      --Judgment that "initialization is required"
        --Check the permission flag and mode flag in the Storage Pool Table (V)
        --Do not initialize if permission is "denied" (regardless of mode flag)
        --When mode is "initial" ⇒ "Initialization required"
        --What if "ready"? ⇒ Do not initialize.
        --What if "error: reason"? ⇒ If initialization is necessary, pooladm will set initial
          It is reset.
        --What if "deprecated"? ⇒ This pool will be deleted. Do not initialize.
        --What if "suspended"? ⇒ Do not initialize.
        -What if (unset)? ⇒ Do not initialize.

        --"allowed" and "initial"

      --If "Does not start" && "Initialization is required", start temporarily.
        --In particular, the case of "suspended" is included.

    Four.
      --The multiplexer is in the Routing Table (Access Key ID
        Or after determining that the direct hostname is not registered)
        By the time just before the try lock, someone may have started and completed MinIO.
        There is. From now on, MinIO Address Table and Routing Table
        Only the own process can rewrite (the entry related to Access Key ID).
        Check again (MinIO Address Table only).

      --Check if the Pool ID entry is registered in the MinIO Address Table.
        --No problem if it is not registered in the MinIO Address Table.
        --MinIO is stopped.
        --If "does not start" and NOT "initialization is required", goto 13;
        --otherwise (NOT "doesn't start" or "needs to be initialized")

        --If registered in the MinIO Address Table, MinIO has already started.
          (subroutine handle_running_minio)
        ――If "initialization is necessary", it is an impossible situation. (This flag is
          If you are standing, MinIO should not be running. )
          Notify system administrator. goto 13;

        --If it doesn't start, you have to stop MinIO.
        --You will reach here when you perform a forced termination operation.
        --If the scheduling is correct, it should be registered on your own node.
          -If it is not the own node, a fatal error occurs.
          -The mux address registered in the MinIO Address Table is
          -Check if it matches the mux address of the local node.
          -Notify the system administrator. goto 13;
          ・ Otherwise goto 12; (kill_supervisor)

        --otherwise (NOT "doesn't start" and NOT "needs to be initialized")
          ie Start, do not initialize, registered in MinIO Address Table.
          -Someone started MinIO just before the try lock.
             The Routing Table should also be updated. (I don't check this.)

        --The one who reached here is not registered in the Routing Table, but MinIO
            Because it was running. Do not update the Routing Table either.
        ――I don't monitor this MinIO.
        --goto 13;

    5. Start MinIO using `sudo`
      --Set alias for mc
        --Delete mc alias at the exit of this block. (mc alias remove)
      --`sudo -u USER -g GROUP / usr / local / bin / minio --anonymous PARAMS`
        (subroutine `try_start_minio`)
        --Read MinIO's standard output and succeed if `API:` is included.
          (subroutine `wait_for_minio_to_come_up`)
      --An error will occur if the port is in use. Change the port and try again.
        --If you have tried all the ports, give up booting. End goto 13;
      --fallthru;

    6. Perform initialization if "initialization required"
      --Refer to "Initialize MinIO" for the procedure.
      --If initialization fails, goto 11;
      --fallthru;

    7. 7.
      --From lock, if TIMEOUT or more has passed, an alarm is recorded in the log.
      ――Since I was able to start it, I don't have a lock, but I will proceed first.
        --Be careful not to step on exception when unlocking.
      --fallthru;

    8. 8.
      --If it doesn't start, goto 11;
      --fallthru;

    9. Update Routing Table and MinIO Address Table
        (subroutine update_tables)
      --Set the current time in the Routing Table (atime) (this is the first)
      --Update Routing Table (register accessKeyID and directHostname) (this is the second)
      --Set a dictionary in MinIO Active Table (this is the last)
        --muxAddr, minioAddr, minioPid, supervisorPid

    Ten.
      --Display host: port on standard output
      --Close standard output
      - end. goto 13;
        (In this case, move to the MinIO watch loop (subr. Watch_minio))
        (In implementation, unlock without returning. (Be careful not to unlock twice))

    11. Stop MinIO
      --Although it is not registered in the MinIO Address Table, your own process is running MinIO.
      --Execute "MinIO stop procedure". (stop_minio)
      --goto 13;
      ――I arrived here via 5. To get to 5, go through 3 and 4.
        Your process is always running MinIO.
        5. comes only from 3 and 4 goto 5 ;, so MinIO Address Table,
        Not registered with Routing Table. Check it.

    12. Stop MinIO
      (subroutine kill_supervisor)
      --Do not unlock. (Apoptosis ignores lock.)
      --The own process has not started MinIO, but the process that started MinIO on its own node
        Exists. `kill (supervisorPid, SIGTERM);`.
      --You've only reached here directly from 3.
        I am here because the forced termination operation was performed.
        It is registered in the MinIO Address Table.
        The Routing Table is not registered.
      --Wait until the MinIO Address Table is empty.
        --Check every s.
        --The MinIO Address Table may never be empty.
          Wait up to kill_supervisor_wait.
      --The route table should also be empty. (Need confirmation?)
      --fallthru; (goto 13)

    13. unlock (); return;

    14. waitUnlock (); return;

  + MinIO initialization
    --If the Storage Pool Table (V) mode is set at startup
      Initialize MinIO when you start MinIO.
      --mode: "initial" / "ready" / "error: reason"
        --For "initial", proceed to the next section.
        --Other than the above, do nothing. end.
          ・ "Ready", "error: reason", etc.
      --There are cases where it is started by decoy and cases where it is started by normal access,
        Same procedure.

    --The initialization procedure is as follows:
      --MinIO has already been started by "Starting MinIO, step 4".
      --The mc setting is completed in "Starting MinIO, step 4".

      --For all users, refer to Storage Pool Table (main) and set policy
        --Create user list from Storage Pool Table (main), sort
        --Get existing user list, sort
          `mc admin user list`
        --zip (user list, existing user list)

        --Users that are not in the existing user list but are in the user list (New Entry)
          -Create (default enable), set policy
             `mc admin user add`,
             `mc admin policy set`
        --Users that are not in the user list but are in the existing user list (Deleted Entry)
          -Disable (do not change the policy. Do not delete.)
            `mc admin user disable`
        --Users that exist on both sides (Updated Entry)
          ・ Set policy
             `mc admin policy set`
          ・ If disable, enable (this is later)
             `mc admin user enable`

        --policy :: = writeonly / readonly / readwrite

      --For all buckets, set the policy by referring to the Storage Pool Table (main).
        --Create a bucket list from the Storage Pool Table (main), sort
        --Create an existing bucket list, sort
          `mc ls`
        --zip (bucket list, existing bucket list)

        --A bucket that is not in the existing bucket list but is in the bucket list (New Entry)
          ・ Create and set policy
            `mc mb`,
            `mc policy set`
        --A bucket that is not in the bucket list but exists in the existing bucket list
          ・ Set none
            `mc policy set none`
        --Buckets that exist on both sides
          -Set the policy of the bucket in the bucket list
            `mc policy set`

        --`policy :: = none / download / upload / public`

      --Set "ready" to the mode of Storage Pool Table (V).
        --Ignore the lock in the Storage Pool Table (V).
        --The lock of Storage Pool Table (V) is used for exclusive control of the caller.
          The manager can ignore this lock.
        --If an error occurs on the way, set "error: reason".
      --There is a possibility that it will not come back from mc.
        --Use alarm () to time out.
        --Setting item name: `minio_setup_timeout`

  + When the Manager process && MinIO ends

    --I started it in my own process, but the Storage Pool Table (main) is "denied".
      Booting via multiplexer, initialization only, MinIO booting procedure 11.
      It is not registered in the MinIO Address Table and Routing Table.

    --Although it was started by its own process, apoptosis was activated.
      Delete the Routing Table and MinIO Address Table and exit.

    --Although it was started by its own process, apoptosis was activated.
      The entry for your process has been deleted from the MinIO Address Table.
      (It disappears as it is)

    --Storage Pool Table (main) is set to "denied" when booting via a multiplexer
      Has become
      --Other processes on your node should be running MinIO. (MinIO startup procedure 11.)
      --If it is not on the local node, a fatal error occurs.
      --Registered in the MinIO Address Table.
      --The Routing Table is not registered.

  + MinIO stop procedure
    (subroutine stop_minio)
    --Stop MinIO with mc
      --mc admin service stop $ alias
      --If you come here from `SIGCHLD`, MinIO no longer exists, STOPPED.
        If it is STOPPED, it may not come back from mc.
        Use alarm () to time out. (`minio_stop_timeout`)
    --Wait MinIO
      --If you come here from `SIGCHLD`, you should be back with -1 immediately. (Excluding STOP)

  + Apoptosis procedure
      (subroutine clear_tables)
    --Do not lock the MinIO Address Table.

    --If you have your own entry in the MinIO Address Table, do the following:
      --There is an entry for your process in the MinIO Address Table, and the supervisor
        The pids match.
      --Removed Pool ID dictionary from MinIO Address Table
      --Read Routing Table (atime)
      --Update Routing Table (remove atime)
        ――It is important not to erase atime by mistake. It is safe to erase it here. I don't care if it remains.
      --Update Routing Table (remove accessKeyID and directHostname)
        ――If you don't, you won't do anything. (Suffering from forced termination)

    --Execute "MinIO stop procedure". (stop_minio)
    --Copy routing Table atime to Storage Pool Table (V)
      ――If you don't, you won't do anything. (Suffering from forced termination)

    ――If you decide to turn off atime here, your own process will be started when it is started with a gap.
      Erase atime that is not managed. The key for atime is minioAddr,
      It starts with the same address, so I make a mistake.
      Should I also lock the operation to kill MinIO?

    --The process ends.


  + `SIGTERM`,` SIGALARM`, `SIGCHLD`
    —— Upon receiving a signal, perform an apoptosis procedure.
      (In implementation, break the watch_minio loop)
    --`SIGCHLD` is when the MinIO process has terminated (including the case of STOPPED)
    --Ignore other signals

  + MinIO's life and death monitoring (polling)
    --Check the survival of MinIO with mc at regular intervals.
      --Include fluctuations in a certain period of time
    --Get MinIO info using mc. If it cannot be obtained, MinIO will not reply.
    --If there is no response from MinIO, perform the apoptosis procedure.
      (In implementation, break the watch_minio loop)
    --There is a possibility that it will not come back from mc.
      Use alarm () to time out. (heartbeat_timeout)

  + MinIO activity monitoring (polling)
    --The manager kills MinIO that has not been accessed for a certain period of time.
      --Last HTTP session of the relevant MinIO recorded in the Routing Table (atime)
        Kill MinIO when the elapsed time from the start time to the current time exceeds the specified value.
    --If there is no response from MinIO, perform the apoptosis procedure.
      (In implementation, break the watch_minio loop)
    --Executed along with MinIO's life-and-death monitoring (polling)

  + Monitor MinIO Address Table (polling)
    --Is there no entry for my process in the MinIO Address Table?
        (For registered entries)
        If the supervisor's pids do not match, apoptosis occurs.
        (In implementation, break the watch_minio loop)
    --Do not lock.
    --Executed along with MinIO's life-and-death monitoring (polling)

  + Confirmation of Pool expiration date
    --Stop MinIO with expired Pool
      --Perform an apoptotic procedure.
        (In implementation, break the watch_minio loop)
    --Pool expiration date can be specified in Storage Pool Table (main)
      --You cannot specify the expiration date for each Access Key ID. For each pool.
    --Crash MinIO using an expired Pool
      --By polling operation
      --Executed along with MinIO's life-and-death monitoring (polling)
    --If the expiration date is changed by the user, this function cannot handle it.
      --MinIO termination operation is performed from ADM.

  + Update monitoring of Storage Pool Table (main)
    --Do not monitor the update of Storage Pool Table (main).
    --For the following events, MinIO termination operation is performed from ADM.
      --The permission flag may be changed to "denied".
      --The expiration date is subject to change.
      --May be changed to "offline".

  + Start MinIO (implementation)
    -Get parameters from Redis other than those passed from scheduler
      --Parameters obtained from Redis
        --MinIO Root Password
        --UNIX username
        --gid
        --Secret Access Key
        --buckets directory
      --Port number is automatic
    --Set to umask 077
    --Use `sudo -u user` to switch permissions for operations during MinIO execution
    --In `sudo`, gid can be specified.
    --Do not use MinIO's command line option `--json`.
      --Because the contents of the standard output of MinIO are not used.

  + Process configuration
    --The manager `setsid (2)` and becomes the session leader.
    --The manager process becomes the direct parent of MinIO.
    --Discard the standard output of MinIO.
    --MinIO's standard error output inherits manager's standard error output
    --The manager detects the end of MinIO with `SIGCHLD`.
    --If the manager is killed, the manager will use mc to stop MinIO.

  + scheduler reads at least one line of manager output.
    --The manager does not stall with the above conditions.
      --The manager outputs only one line to stdout.

  + Manager operating environment
    --The manager shall be operated on a dedicated node.
      --General users shall not log in to the node.
      --A port number is secured in advance (maliciously) by another person or another application.
        I don't expect that.
      --Allow the port to be (accidentally) used by other apps.
    --The manager shall be called from the scheduler.
    --Not expected to be used directly by the user.


## remarks

  + Operational notes
    --In this method, unless you delete the local account (UNIX user), the S3 compatible server
      The feature remains valid.
    --In the case of Tomitake, if you want to suspend the user account, use a local account.
      The operation is done to leave it.
    --Under the above assumptions, if you suspend your user account at Tomitake,
      Use the administrator command of this system to create the account.
      It is necessary to delete the user from the DB of this system.

## Sudo

  + Commands to be executed by each user with `sudo`:` / usr / local / bin / minio`

## Security

  + Security
    --WebUI always trusts `Authorization:`.

  + Include CSRF Token in the payload, not the HTTP header.
    --Consider the existence of a reverse proxy that limits the header to stoic.

  + MinIO listens to ANY.

<!-- NEW -->

## Design Notes

### Redis Database Keys (prefixes)

Lens3 uses a couple of databases (by a database number), but the
division is arbitrary because the distinct prefixes are used.  Most of
the entries are records in json, and the others are simple strings.

Note: In the tables below, entries with "(\*)" are set atomically (by
"setnx"), and entries with "(\*\*)" are with expiry.

#### storage-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| po:pool-id    | pool-description | |
| uu:user       | user-info     | |
| ps:pool-id    | pool-state    | |
| bd:directory  | pool-id       | A bucket-directory (string) (\*) |

A pool-description is a record: {}.

A user-info is a record: {"groups", "permitted", "modification_time"}
where "groups" is a string list and "permitted" is a boolean.

#### process-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| ma:pool-id    | MinIO-manager | (\*, \*\*)|
| mn:pool-id    | MinIO-process | |
| mx:mux-endpoint | Mux-description | |

An __ma:pool-id__ entry is a MinIO-manager under which a MinIO process
runs.  It is a record: {"mux_host", "mux_port", "manager_pid",
"modification_time"}.  It is used as a mutex and protects accesses to
mn:pool-id and ep:pool-id.

An __mn:pool-id__ entry is a MinIO-process description: {"minio_ep",
"minio_pid", "admin", "password", "mux_host", "mux_port",
"manager_pid", "modification_time"}.

An __mx:mux-endpoint__ entry is a Mux description that is a record:
{"host", "port", "start_time", "modification_time"}.  A key is an
endpoint (host+port) of a Mux.  A start-time is a time the record is
first created, and a modification-time is updated each time the record
is refreshed.  The content has no particular use.

#### routing-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| ep:pool-id    | MinIO-endpoint | |
| bk:bucket-name | bucket-description | A mapping by a bucket-name (\*) |
| ts:pool-id    | timestamp     | Timestamp on the last access (string) |

An __ep:pool-id__ entry is a MinIO-endpoint (a host:port string).

A __bk:bucket-name__ entry is a bucket-description that is a
record: {"pool", "bkt_policy", "modification_time"}.  A bkt-policy
indicates public R/W status of a bucket: {"none", "upload",
"download", "public"}, which are borrowed from MinIO.

#### pickone-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| id:random     | key-description | An entry to keep uniqueness (*) |

An id:random entry stores a generated key for pool-id or access-key.
A key-description is a record: {"use", "owner", "secret_key",
"key_policy", "modification_time"}.  A use/owner pair is either
"pool"/user-id or "access_key"/pool-id.  A secret-key and a key-policy
fields are missing for an entry for use=pool.  A key-policy is one of
{"readwrite", "readonly", "writeonly"}, which are borrowed from MinIO.

### Bucket policy

Public r/w policy is given to a bucket by Lens3.  Lens3 invokes the mc
command, one of the following.

```
mc policy set public alias/bucket
mc policy set upload alias/bucket
mc policy set download alias/bucket
mc policy set none alias/bucket
```

Accesses to deleted buckets in Lens3 are refused at Mux, but they
remain accessbile in MinIO, which have access policy "none" and are
accessible using access-keys.

### Redis Database Operations

A single Redis instance is used, and not distributed.

Usually, it is required an uniqueness guarantee, such as for an
access-keys and ID's for pools, and atomic set is suffice.  A failure
is concidered only for MinIO endpoints, and timeouts are set for
"ma:pool-id" entries.  See the section Redis Database Keys.

Redis client routines catches socket related exceptions (including
ConnectionError and TimeoutError).  Others are not checked at all by
Lens3.

Operations by an administrator is NOT mutexed.  They include
modifications on the user-list.

### Pool State Transition

A bucket-pool has a state in: __None__, __INITIAL__, __READY__,
__DISABLED__, and __INOPERABLE__.  Mux (A Manager) governs transition
of states.  A Manager checks conditions of a transition at some
interval (heartbeat_interval).

* __None__ → __INITIAL__: It is a quick transition.
* __INITIAL__ → _READY__: It is at a start of MinIO.
* ? → __INOPERABLE__: It is by a failure of starting MinIO.  This
  state is a deadend.
* ? → __DISABLED__: It is by some disabling condition, including an
  expiry of a pool, disabling a user account, or making a pool
  offline.
*__DISABLED__ → __INITIAL__: It is at a cease of a disabling condition.

### Wui/Mux systemd Services

All states of services are stored in Redis.  systemd services can be
stoped/started.

### Wui Processes

Wui is not designed as load-balanced.  Wui may consist of some
processes (started by Gunicorn), but they need to run on a single node
in order to share the configuration directory of the "mc" command.

### Mux Processes

There exists multiple Mux processes for a single Mux service, as it is
started by Gunicorn.  Some book-keeping periodical operations (running
in background threads) are performed more frequently than expected.

### MinIO Clients

Note that alias commands are local (not connect to a MinIO).

### Manager Processes

A Manager becomes a session leader (by calling setsid), and a MinIO
process will be terminated when a Manager exits.

## Service Tests

#### Forced Heartbeat Failure

"kill -STOP" the MinIO process.  It causes heartbeat failure.  Note
that, it leaves "minio" and "sudo" processes in STOP state.

#### Forced Termination of Mux and MinIO

#### Deletion of Redis Expiring Entries

Forced removal of a __ma:pool-id__ entry should (1) start a new
Mux+MinIO pair, and (2) stop an old Mux+MinIO pair.

## Glossary

* __Probe-key__: An access-key used by Wui to tell Mux about wake up
  of MinIO.  This is key has no corresponding secret.  It is
  distiguished by an empty secret.

## RANDOM MEMO

__Load balancing__: The "scheduler.py" file is not used in v1.2, which
is for distributing the processes.  Lens3 now assumes accesses to Mux
is in itself balanced by a front-end reverse-proxy.

__Removing buckets__: Lens3 does not remove buckets at all.  It just
makes them inaccessible.  It is because MinIO's "mc rb" command
removes the contents of a bucket that is not useful usually.

__Python Popen behavior__: A closure of a pipe created by Popen is not
detectable until the process exits.  Lens3 uses a one line message on
stdout to detect a start of a subprocess, but it does not wait for an
EOF.  In addition, p.communicate() on an exited process waits.  A
check of a process status is needed.

__Python alarm behavior__: Raising an exception at an alarm signal
does not wake-up the python waiting for a subprocess to finish.
Instead, a timeout of p.comminicate() will be in effect.

__MC command concurrency__: Lens3 assumes running multiple MC commands
with a distinct "alias" concurrently do not interfere.
