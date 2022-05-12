# Design of Lenticularis-S3

This briefly describes a design of Lenticularis-S3.

[TOC]

## Overview

  + Terminology
    --Storage Zone:
      UNIX userid, bucket storage, access key, expiration date, etc.
      A concept that summarizes a set of information. A concept similar to Endpoint, but
      Because the facade hostname function makes the endpoint-url common,
      To avoid confusion, this system calls it the Storage Zone.
      (Abbreviated as zone if it is not ambiguous in context)

## System configuration

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


## Multiplexer

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
        --At this stage, the direct hostname is registered in the Storage Zone Table (main).
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

## Scheduler

  + Basic functions
    --Determine Zone ID
    --Determine the node to start MinIO in charge of Zone ID
    --Call manager and start MinIO in charge of Zone ID
    --Retransfer of the session transferred from the multiplexer (* See implementation differences)

  + Start condition
    --Called from the multiplexer. There are two reasons:
      --Access with direct hostname could not be resolved.
      --Access with Access Key ID could not be resolved.
    --Get Zone ID from Storage Zone Table (main)

  + Basic operation

    1. If access with direct hostname cannot be resolved
      --Look up the Storage Zone Table (directHostname) with Host as the key.
        Get Zone ID.
      --If you could not get the Zone ID:
        --The direct hostname is not registered. error 404 (via multiplexer)
      --A Zone ID was obtained. goto 3;
      --1, 2 are exclusive

    2. If access with the Access Key ID cannot be resolved
      --Look up the Storage Zone Table (accessKeyID) using the Access Key ID as the key.
        Get Zone ID.
      --If you could not get the Zone ID:
        --The Access Key ID is not registered. error 404 (via multiplexer)
      --A Zone ID was obtained. goto 3;
      --1, 2 are exclusive

    3. The Zone ID is not registered in the route table.
      --Here, I don't check if it is still registered in the MinIO Address Table.
      --Determine the node to start MinIO. (see "Scheduling" below)
        --When running on your own node: Start manager.
        --Pass the Zone ID, port range, and multiplexer address.
        --The Routing Table should have been updated after the startup is completed.
        --goto 4;

      --When running on another node: Transfer to that node.
        --Returns the address of the multiplexer of the node.
        --return Address of forwarding multiplexer;

    Four.
      --Recheck the Routing Table (directHostname). (In case of 1)
      --Recheck the Routing Table (accessKeyID). (In case of 2)
      --If MinIO Address is not registered in the Routing Table at this point,
        Unrecoverable error. 404 (via multiplexer)
        --It will be terminated immediately after the start operation.
      --return MinIO Address;

  + Scheduling
    --Calculate the node that launches MinIO

    --Look up the MinIO Address Table using the Zone ID as a key.
      --The Zone ID has already been obtained in step 1 or 2.
      --If registered, that node. Absolute priority. (hard coded)

    --Criteria for selecting other nodes
      --Automatically select the node with the fewest minio

  + Implementation
    --The controller is implemented with gunicorn + wsgi.

  + Differences between design concepts and implementations
    --For simplification of implementation, the controller and router are implemented in the same application.
      It is not an implementation that the controller forwards the HTTP session, but after starting MinIO
      Control shall be returned to the router.

  + Why the scheduler doesn't rewrite the Routing Table
      It is manager who terminates MinIO with a timeout.
      The scheduler is closed when MinIO is closed, in this case the manager
      I have to rewrite it. Therefore, even when MinIO is started, the manager will
      If you decide to rewrite the Routing Table, rewrite the Routing Table
      Is only the manager, and it is refreshing.

## Manager

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
      --Zone ID (mandatory)
        --Passing environment variables LENTICULARIS_ZONE_ID
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
        --Registered in Storage Zone Table (main) when starting MinIO
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
        Using the Zone ID as a key, the address of the multiplexer in charge,
        Record MinIO's address, MinIO's pid, and its own pid. Moreover,
        Update the Routing Table according to the above information.

  + Basic operation
    + Start
      --Look up the Storage Zone Table (main) using the Zone ID as a key and start MinIO.
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
      --Otherwise, `MINIO_ROOT_USER = zoneID`,
        Set `MINIO_ROOT_PASSWORD = rootSecret`.

    2. Lock the MinIO Address Table

      --try try
        --lock ("lk:" MinIO Address Table, Zone ID, timeout = TIMEOUT)
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

    3. Get parameters from Storage Zone Table (main)
      ――Atomicly, save everything.
      --Judgment of "not starting"
        --Check the status flag ⇒ If it is not "online", "Do not start"
        --Check the permission flag ⇒ If it is not "allowed", "Do not start"
        --Get expiration date (expDate) ⇒ If it expires, "Do not start"
        --Confirm Authorization ⇒ If you access by zone ID, "Do not start"
          JUSTIFICATION: I don't want all MinIO to be running after batch registration.
        --Check mode ⇒ If it is not "ready", "do not start"
        --"Start" == ("online" and "allowed" and "during validity period"
                           And "not zone ID" and "ready")

      --Judgment that "initialization is required"
        --Check the permission flag and mode flag in the Storage Zone Table (V)
        --Do not initialize if permission is "denied" (regardless of mode flag)
        --When mode is "initial" ⇒ "Initialization required"
        --What if "ready"? ⇒ Do not initialize.
        --What if "error: reason"? ⇒ If initialization is necessary, zoneadm will set initial
          It is reset.
        --What if "deprecated"? ⇒ This zone will be deleted. Do not initialize.
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

      --Check if the Zone ID entry is registered in the MinIO Address Table.
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
    --If the Storage Zone Table (V) mode is set at startup
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

      --For all users, refer to Storage Zone Table (main) and set policy
        --Create user list from Storage Zone Table (main), sort
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

      --For all buckets, set the policy by referring to the Storage Zone Table (main).
        --Create a bucket list from the Storage Zone Table (main), sort
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

      --Set "ready" to the mode of Storage Zone Table (V).
        --Ignore the lock in the Storage Zone Table (V).
        --The lock of Storage Zone Table (V) is used for exclusive control of the caller.
          The manager can ignore this lock.
        --If an error occurs on the way, set "error: reason".
      --There is a possibility that it will not come back from mc.
        --Use alarm () to time out.
        --Setting item name: `minio_user_install_timelimit`

  + When the Manager process && MinIO ends

    --I started it in my own process, but the Storage Zone Table (main) is "denied".
      Booting via multiplexer, initialization only, MinIO booting procedure 11.
      It is not registered in the MinIO Address Table and Routing Table.

    --Although it was started by its own process, apoptosis was activated.
      Delete the Routing Table and MinIO Address Table and exit.

    --Although it was started by its own process, apoptosis was activated.
      The entry for your process has been deleted from the MinIO Address Table.
      (It disappears as it is)

    --Storage Zone Table (main) is set to "denied" when booting via a multiplexer
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
        Use alarm () to time out. (`mc_stop_timelimit`)
    --Wait MinIO
      --If you come here from `SIGCHLD`, you should be back with -1 immediately. (Excluding STOP)

  + Apoptosis procedure
      (subroutine clear_tables)
    --Do not lock the MinIO Address Table.

    --If you have your own entry in the MinIO Address Table, do the following:
      --There is an entry for your process in the MinIO Address Table, and the supervisor
        The pids match.
      --Removed Zone ID dictionary from MinIO Address Table
      --Read Routing Table (atime)
      --Update Routing Table (remove atime)
        ――It is important not to erase atime by mistake. It is safe to erase it here. I don't care if it remains.
      --Update Routing Table (remove accessKeyID and directHostname)
        ――If you don't, you won't do anything. (Suffering from forced termination)

    --Execute "MinIO stop procedure". (stop_minio)
    --Copy routing Table atime to Storage Zone Table (V)
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
      Use alarm () to time out. (mc_info_timelimit)

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

  + Confirmation of Zone expiration date
    --Stop MinIO with expired Zone
      --Perform an apoptotic procedure.
        (In implementation, break the watch_minio loop)
    --Zone expiration date can be specified in Storage Zone Table (main)
      --You cannot specify the expiration date for each Access Key ID. For each zone.
    --Crash MinIO using an expired Zone
      --By polling operation
      --Executed along with MinIO's life-and-death monitoring (polling)
    --If the expiration date is changed by the user, this function cannot handle it.
      --MinIO termination operation is performed from ADM.

  + Update monitoring of Storage Zone Table (main)
    --Do not monitor the update of Storage Zone Table (main).
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


## decoy packet
  + decoy packet
    --Host: (direct hostname / facade hostname) and Authorization:
      Throws the correct (*) packet, the multiplexer, scheduler,
      The manager does exactly the same as for legitimate access,
      MinIO starts. Using this form of packet, the admin command
      Tell the manager the operation.
      -*: At least algorithm, Access Key ID part only
        --Multiplexers and controllers are other HTTP headers and payloads
          Because / cannot confirm the validity of. Signed Headers of Authorization,
          The existence of Signature is not confirmed. Similarly, the Credential date, Region,
          Do not check service either.
      --After starting MinIO, it becomes an illegal S3 access and returns an error, but it does not end.
      ――Packets of this type can be used for attacks that only activate MinIO,
        Due to the specifications, it is unavoidable.

    --Example: If you throw the following packet, the Access Key ID specified by Authorization
      The person in charge MinIO starts.

`` ```
Figure 1 decoy packet
`` ```

`` ```
Figure 2 Authorization
`` ```

`` ```
Figure 3 Credential
`` ```

## Server (S3 compatible server function)

  + MinIO
    --Use MinIO without modification


## Management function (specifications)

  + Access Key function
    --The access key duplication check is an exact match.
      --Only works when registering from API
        The estimated number of registrations is up to 10,000, and there is no problem in terms of performance.

  + Configuration file
    --Lalocation of multiplexer and controller
    --Address listened to by the multiplexer (connection port from the front end)
      --Reflected in the argument of starting gunicorn
    --Address that WebUI listens to (connection port from frontend)
      --Reflected in the argument of starting gunicorn
    --Authentication method used in Web UI
      --ssl-client-verify: / authorization: basic / authorization: bearer
    --Polling interval for life and death monitoring
    --Time to purge inactive MinIO
    --Redis port
    --Redis passphrase
    --Access log settings (default: LOCAL7, LOG_INFO)
    --Maximum number of entries per user
    --Allow / Deny List
      --Not a configuration file. Register with Redis.

      `` ```
      DENY, a00666
      DENY, rccs-aot
      ALLOW, *
      `` ```
    --List of groups to which all users belong
      --Not a configuration file. Register with Redis.
      --It is necessary to register all users separately from the allow / deny list.

  + Administrator command (CLI)
    --Storage Zone Table (main) Display / Edit, dump / restore
    --Operation monitoring / audit function
      --Display Routing Table
      --List of running MinIO
    --Resetting the Routing Table
      --The Routing Table can always be deleted. (atime is lost)
    --If the Routing Table is out of sync with MinIO's Life and Death Monitor (manager)
      Repair command
      --Reset the Routing Table.
        --Do not lock.
        --All reset or specify conditions
    --Reset MinIO Address Table
      --Delete from Routing Table and MinIO Address Table
        --All reset or specify conditions
        --Deleted from MinIO Address Table first, then deleted from Routing Table.
        --Do not lock.
        --In this situation, there is no option to stop MinIO. MinIO Address Table
          If you remove it from the polling interval at worst, it will undergo apoptosis after the polling interval time, so leave it alone.
    --Reset Storage Zone Table (*)
      --It is possible for the administrator to forcibly reset.
      --It is also possible for the administrator to delete only specific entries.
      --If you reset the Storage Zone Table (*), the data registered by the user will be lost.

    --Forced start of MinIO
    --MinIO forced stop (time consuming op.)

    --User / group list registration
      `` ```
      user1, gropu1, group2
      user2, gropu2, group3, group4
      ...
      `` ```

    --Allow / deny list registration


  + User functions (WebUI, CLI)
    --Limited to authenticated HTTP sessions
      --The Web UI itself does not have an authentication function. Authenticate externally and use the HTTP header
        `Authorization:` shall notify the authenticated user.
        --Different from S3 Authorization.
      --Confirm that one of the following three types is added to the HTTP header
        --`ssl_client_verify: success` &&` ssl_client_s_dn: ... `
        --`Authorization: basic ...`
        --`Authorization: bearer ...`
        --The method used for authentication can be specified in the configuration file.
          ・ Multiple specifications are possible
      --Authorization is the same as the local user name
        --Do not implement the map function.
    --Generation of Zone ID, Access Key ID, Secret Access Key
      --Zone ID, Access Key ID, Secret Access Key From generation to registration,
        Do not temporarily press the key.
    --Zone registration
    --View / edit / delete the list of entries belonging to your account
    --No administrator intervention required
    --Use syslog to save Apache combined equivalent logs.
      --The other party's port is also saved in the log.
    --Forcibly stop MinIO from WebUI:
      --Stop MinIO with mc
        mc admin service stop $ alias
      --You can connect to any multiplexer.

      --Do not serve disabled and unregistered users.
      --The bucket that could not be created is displayed in the UI as an error,
        The registration itself is completed, and the bucket can be used except for the bucket.

    --WebUI should be simple to speak json.
      --Assumed to be accessed only by authenticated users.
      --Do not implement user CLI.
        It can be easily realized by creating it as a wrapper that hits authentication + WebUI.

  + System requirements, installer
    --Can be operated on at least one node
    --Assuming a standard Linux distro
      --AlmaLinux 8.5
      --Ubuntu 20.04
    --Use pyenv to build Python environment
    --gunicorn starts from systemd

  + Test
    --MinIO standalone startup function for defect isolation


## Management function (implementation)

  + What you can do
    --Register / change / delete Zone
    --MinIO forced start / stop
    --Update allow / deny rules

  + Zone registration / change (ZoneDict is passed)

    1. If the zoneID exists at the time of registration, "change"
      --MinIO will stop, initialize, and restart without any changes.

      --Shaping the zone
        --encrypt
        --verification
      --If changed, calculate the difference,
        --If the bucket has changed, it needs to be initialized.
        --Error if access key has been changed
        --Error if buckets directory has changed

      --try: lock Storage Zone Table ("zk: {zone_id}")
        --If not "change", generate rootSecret and add it to storageZoneDict.

    2. Make MinIO unbootable.
      --Set to suspended
        --ptr does not change even in the suspended state.
      --Extract the Access Key ID and direct hostname from the reverse lookup

    3. If MinIO is running, stop it.
      ――If you can't stop it
        --Extract from MinIO Address Table, then from the route table.

    4. Zone registration
      --try: lock the entire Storage Zone Table ("zk:")
      --Key, bucket collision check
      --Register storageZoneDict in Storage Zone Table (main)
      --finally: unlock

    5. If initialization is needed
      --Additional zoneID is registered in the reverse lookup table
      --Set the Storage Zone Table (main) to `mode:" initial "`
      --Throw a decoy packet to zoneID
        (manager starts MinIO and initializes it.)
      --Delete the additionally registered zoneID from the reverse lookup table
        (Even if decoy fails, it will be executed.)

    6. Register the Access Key ID and direct hostname in the reverse lookup table
      --Execute even if initialization fails.

      --Set to resumed (not suspended)

    7. Returns mode.
      --If initialization is required, the success or failure of decoy is set to mode.
        If not, the last mode is set.

    8. finally: unlock (corresponds to 1)

  + Delete Zone

    1. try: lock the Storage Zone Table ("zk:")
      -(I don't pay attention to shorten the lock period.)
      --Set to suspended
    2. Clear the routing table (if there is an entry)
      --At this point, you will not be able to access.
    3. Stop MinIO (throwing a decoy is enough, you don't have to wait.)
    4. Remove mode, atime, ptr
    5. Delete zone
    6. finally: unlock

  + Forced start of MinIO
    --Throw a decoy packet to a suitable multiplexer.
      --In case of operation without facade hostname, you can go to direct hostname.

  + Forced stop of MinIO (time consuming op.)
    1. try: lock the Storage Zone Table ("zk:")
    2. If it is not registered in the MinIO Address Table, it is successful and finished.
        --If you know the node and pid, kill -TERM. Out of range of this operation.
        --Otherwise, MinIO cannot be stopped.

        --What if you can't lock?
    3. Set the permission flag of Storage Zone Table (main) to "denied".
    Four.
        --Pull out from the Routing Table.
          The same applies to the Routing Table (accessKeyID, directHostname).
          The Routing Table (atime) is left alone at this point.
        --To the multiplexer registered in MinIO Address Table
          Throw a decoy packet.
        --Confirm that it disappears from the MinIO Address Table.
        -Restore the permission flag in the Storage Zone Table (main) (if necessary).
    5. finally: unlock Storage Zone Table (*)

  + allow / deny rule updates
    - register
      --Check all Zones with new rules
      --Update Zone when conditions change (with MinIO pause)

## Web UI

  + WebUI
    --The key of the resource is zoneID.

## Public access function

  + Basic operation
    --DNS: Use Wildcard DNS record.
    --HTTPD: `

    Use `.
    --The multiplexer is sorted by referring to virtualhost (direct hostname).

  + Limits
    --Only one direct hostname can be set for each entry.

  + Sharing settings
    --After setting the Direct hostname, use the mc command etc. to set it separately by the user.
    --Reference: Public setting by mc:
      `` ```
      mc policy set public $ alias / $ bucket
      `` ```

## table

  + Table implementation uses Redis.
    --Redis is preferred over Memcached.
      --You can set a password.
      --Key list can be obtained.

    --Do not use redis_semaphore
    --Do not use pub / sub
    --Implement lock with transaction

  + DB reading is not exclusively controlled.
    --At any time, any process can be freely read from the DB.
    --The procedure to write to DB causes a problem no matter when it is read.
      Configure not to. (Only the items to be read in the previous section)

  + lock is 4 types
    -"pk:", "zk: {id}", "zk:", "lk: {id}"

    -"zk: {id}" also serves as suspend / resume for the zone

    --Table 1.1 lock list
      `` ```
      ========= ======================================== ===============
      lock description
      --------- ----------------------------------------- ---------------
      pk: allow / deny table rewrite
                      Conflict prevention when double-launching management commands
                 Target: entire allow / deny table

      rewriting zk: {id} Zone (suppressing MinIO startup)
                      Add, modify, delete
                      Modification / deletion involves clearing the route table + stopping MinIO
                      Only the specified Zone ID
                      While locked, the zone is suspended
                      The manager blocks while suspending.
                 Target: zone specified by id

      zk: Zone rewrite
                      Exclusive lock for store_zone.
                      Access Key ID, Secret Access Key, hostname collision
                      Checks are done under this lock. (While acquiring this lock,
                      Only I can rewrite the zone)
                 Target: Entire Zone

      lk: {id} MinIO started
                      Exclusive control of MinIO startup.
                      I stopped MinIO without locking and got this lock
                      The process also joins the stop target.
                 Target: zone specified by id
      ========= ======================================== ===============
      `` ```

  + Allow / Deny Table rewrite rights ("pk:" @ Allow / Deny Table)
    --Only processes with global lock in Allow / Deny Table
    --ADM only

  + Right to rewrite Storage Zone Table ("zk: {id}" @ Storage Zone Table)
    --Process (thread) with Zone ID lock in Storage Zone Table
      Only have the right to rewrite the entry for the Zone ID.
    --Exclusive lock for MinIO configuration operations
    --Used by ADM and API.
    -(V) Part is out of scope.
    --The manager ignores this lock and rewrites it.
      -(V) Part only.

  + Right to rewrite Storage Zone Table ("zk: {id}" @ Storage Zone Table)

  + Right to rewrite Storage Zone Table (accessKeyID, directHostname)
    --Interlock with Storage Zone Table (main).

  + MinIO Address Table rewrite right ("lk:" @minioAddressTable)
    --Process (thread) with Zone ID lock in MinIO Address Table
      Only have the right to rewrite the entry for the Zone ID.
       `try lock (MinIO Address Table, Zone ID, timeout = TIMEOUT)`
      --Deletes are not interlocked.
    --Routing Table (atime) is not subject to interlock.
    --Only the manager locks.
    --ADM may be forcibly deleted. When forced to delete, manager apoptotic.

  + Rewriting right (None) of Routing Table (accessKeyID, directHostname)
    --Interlock with MinIO Address Table.
    --Only the manager locks.
    --ADM may be forcibly deleted.

  + Routing Table (atime) rewrite right (None)
    --The multiplexer, manager rewrites.
    --Do not lock.
    --ADM may be forcibly deleted.

    --Table 1.2 List of rewrite rights
      `` ```
      ==== ============================================== == === ===
      no. F / E MUX SCH MGR SRV ADM API
      ---- --------------------------------- --- --- --- --- --- ----- ---
      0 Storage Zone Table
            Allow / Deny Table rwx r
            Users Table rwx r
            Storage Zone Table (main) rw rwx rwx
            Storage Zone Table (V) rwx rwx rwx
            Storage Zone Table (accessKeyID) r rwx rwx
            Storage Zone Table (directHostname) r rwx rwx
      2 Process Table
            Multiplexer Table rwx r rwx
            MinIO Address Table r rwx rx
      4 Routing Table
            Routing Table (accessKeyID) r rwx rx
            Routing Table (directHostname) r rwx rx
            Routing Table (atime) w rwx rx
      ==== ============================================== == === ===

        r: read, w: write, x: delete

        F / E: Load balancer
        MUX: multiplexer
        SCH: scheduler
        MGR: manager
        SRV: Server (MinIO)
        ADM: Administrator CLI
        API: WebUI Opposite API for Users
      `` ```



  + Allow / Deny Table

    --Table 2.1
      `` ```
      -------------- ------------------------------------ --------
      DB No. 0
      Type Strings
      Key "pr ::"
      Value json string that represents allow / deny rules
      -------------- ------------------------------------ --------
      `` ```

    --If this table changes, modify all entries in the Storage Zone Table (main)?


  + Users Table

    --Table 2.2
      `` ```
      -------------- ------------------------------------ --------
      DB No. 0
      Type Strings
      Key "uu: {unix_user}"
      Value {"id": "user1", "groups": ["group1", "group2", ...]}
      -------------- ------------------------------------ --------
      `` ```


  + Storage Zone Table (main):
    --Zone ID (primary key)
      --key & password
    --Access Key ID
      --Even in the case of operation that is accessed only by direct hostname
        Access Key ID and Secret Access Key are required
    --Secret Access Key
      --Encrypt and save on redis.
        --From the API, pour in the raw Secret Access Key.
      --Cryptographic strength does not matter (using rot13, changing only alphabet, numbers do not change)
        --`L0cXvr722WUiwaxM0OTU` ⇔` $ 13 $: Y0pKie722JHvjnkZ0BGH`

    --Uid when running the MinIO process (to the username authenticated by the front end)
      Match)
    --Gid when running the MinIO process
    --buckets directory (bucketsDir)
    --buckets (buckets)
      --`[{"key ": name," policy ": policy} ...]`
    --direct hostname (None when this function is OFF)
    --The expiration date of this entry (seconds since the epoch)
      --If it expires, MinIO will only be stopped and the entry will not be deleted.
    --Activation flag (calculated from administrator's permission list)

    --MinIO Root User and Password can be designed not to be saved in this table.
      (In this design, Zone ID is used for MinIO Root User)
      Administrators can access MinIO with MinIO Root privileges when troubleshooting
      Considering the merits, it is designed to be saved in this table.

    --Table 3.1 Storage Zone Table (main)
      `` ```
      --------------- ----------------------- ------------ ---
      DB No. 0
      Type Hash
      Key Zone ID ru:
      persistent True
      --------------- ----------------------- ------------ ---
      user User V-
      group Group VM
      rootSecret MinIO Root Password ---
      bucketsDir Buckets Directory VM
      buckets [Bucket] VM
      accessKeys [AccessKey ...] VM
      directHostnames [direct Hostname] VM
      expDate expiration date VM
      status online / offline VM
      permission allowed / denied ----
      --------------- ----------------------- ------------ ---
      var storage_zone_table
      funcs
                       ins_storage_zone
                       get_storage_zone
                       del_storage_zone
                       get_zoneID_list
                       set_permission
                       ins_allow_deny_rules
                       get_allow_deny_rules
                       ins_unixUserInfo
                       get_unixUserInfo
                       del_unixUserInfo
                       get_unixUsers_list
      --------------- ----------------------- ------------ ---
      V: Visible to users
      M: Modifiable by users
      AccessKey: {"accessKeyID": "AccessKey ID",
                  "secretAccessKey": "Secret Access Key",
                  "policyName": "readwrite / readonly / writeonly"}
      Bucket: {"key": ...
                  "policy": "none / none / upload / download / public"}
      `` ```


    --Table 3.2 Storage Zone Table (V)
      `` ```
      -------------- ----------------------------- ------- --------
      common w / Storage Zone Table (main)
      Type Strings
      Key ac: zoneID mo: zoneID
      persistent True
      -------------- ----------------------------- ------- --------
      atime valid while offline V --ac:
      mode initial / ready / error: reason /
                      / deprecated / suspended / V --mo:
      -------------- ----------------------------- ------- --------
      var storage_zone_table
      funcs set_atime, get_atime, del_atime
                      set_mode, get_mode, del_mode
      -------------- ----------------------------- ------- --------
      `` ```


    --Table 3.3 Storage Zone Table (accessKeyID)
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 0
      Type Strings
      Key Access Key ID ar:
      Value Zone ID
      persistent True
      -------------- ----------------------- ------------- -
      funcs: see Table 3.5
      -------------- ----------------------- ------------- -
      `` ```


    --Table 3.4 Storage Zone Table (directHostname)
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 0
      Type Strings
      Key Direct Hostname dr:
      Value Zone ID
      persistent True
      -------------- ----------------------- ------------- -
      funcs: see Table 3.5
      -------------- ----------------------- ------------- -
      `` ```


    --Table 3.5 Storage Zone Functions (PTR OP.)
      `` ```
      -------------- ----------------------- ------------- -
      funcs ins_ptr, del_ptr
                      get_zoneID_by_access_key_id
                      get_zoneID_by_directHostname
                      get_ptr_list
      -------------- ----------------------- ------------- -
      `` ```


  + Multiplexer Table: List of active multiplexers

    --Table 4.1 Multiplexer Table
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 2
      Type String
      Key Multiplexer host mx:
      Value Multiplexer conf
      persistent No
      -------------- ----------------------- ------------- -
      var process_table
      funcs set_mux
                      get_mux
                      del_mux
                      get_mux_list
      -------------- ---------------------- -------------- ――――
      `` ```

  --Hold a subset of mux-config.yaml in mux_conf.
    When the scheduler is upgraded in the future, the settings for each mux will be shared by mux_conf.

  --The mux address is obtained by combining the host and port of mux_conf with:.
    Process Table's minioAddr and routing Table keys are in this format
    Only the host and port of the mux_conf remain isolated.
    --This is because muxAddr in Process Table is only the host name.
      To calculate that value. (Separation is more difficult than binding)
      ――In the first place, even though the minioAddr of Process Table is Host: Port
         It is not applicable that muxAddr is Host.
         muxAddr is because multiplexer is one process per node
         Because of the policy that it is not necessary to distinguish by port.

  + MinIO Address Table
    --Zone ID → host: port: pid
    ――Can MinIO during shutdown be changed to orphan?
      ⇒ Also from the Routing Table, pull out from (R) to enable double startup.
      ⇒ The manager determines that MinIO is not running if it is not in (R).

    --Table 4.2 MinIO Address Table
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 2
      Type Hash
      Key Zone ID ma:
      persistent No
      -------------- ----------------------- ------------- -
      muxAddr Multiplexer Address
      minioAddr MinIO Address
      minioPid MinIO's PID
      supervisorPid Launcher's PID
      -------------- ----------------------- ------------- -
      var process_table
      funcs ins_minio_address
                      del_minio_address
                      get_minio_address
                      set_minio_address_expire
                      get_minio_address_list
      -------------- ----------------------- ------------- -
      `` ```


    --If the MinIO Address Table disappears at timeout,
      The routing table does not trigger the deletion of interlocking.


  + Routing Table: Correspondence table between Access Key ID and running MinIO
    --Access Key ID → Destination
    --Destination: MinIO standby address, host: port

    --Table 5.1 Routing Table (accessKeyID)
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 4
      Type Strings
      Key Access Key ID aa:
      Value MinIO Address
      persistent No
      -------------- ----------------------- ------------- -
      `` ```

    --Table 5.2 Routing Table (directHostname)
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 4
      Type Strings
      Key Direct Hostname da:
      Value MinIO Address
      persistent No
      -------------- ----------------------- ------------- -
      funcs: see Table 5.4
      -------------- ----------------------- ------------- -
      `` ```

    --Table 5.3 Routing Table (atime)
      `` ```
      -------------- ----------------------- ------------- -
      DB No. 4
      Type Strings
      Key MinIO Address at:
      Value seconds since the epoch
      persistent No
      -------------- ----------------------- ------------- -
      funcs: see Table 5.4
      -------------- ----------------------- ------------- -
      `` ```


    --Table 5.4 Routing Table Functions
      `` ```
      -------------- ----------------------- ------------- -
      var routingTable
      funcs ins_route
                      del_route
                      set_rout_expire
                      get_route_by_access_key
                      get_route_by_direct_hostname
                      set_atime_expire
                      set_atime_by_addr `_by_addr` is suffixed to avoid method name collisions.
                      get_atime_by_addr
                      del_atime_by_addr
                      get_route_list
      -------------- ----------------------- ------------- -
      `` ```

  + To simplify the implementation, atime with mux as a key is registered in the table,
    The system does not use that value.

  + User manipulation of the table
    --The API that is the back end of the user Web UI operates with lenticularis_admin privileges.
      Therefore, there are no restrictions on reading and writing tables.

  + Timing to initialize MinIO
    --If the Access Key ID or Secret Access Key is changed, stop it once.

## Security

  + Security
    --WebUI always trusts `Authorization:`.

  + Include CSRF Token in the payload, not the HTTP header.
    --Consider the existence of a reverse proxy that limits the header to stoic.

  + MinIO listens to ANY.


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

## API


  + Create limit
     --zoneID, Access Key ID, Secret Access Key cannot be changed.

  + Update restrictions
     --zoneID, Access Key ID, Secret Access Key cannot be changed.
     --BucketsDirectory cannot.

## mc

  --List of commands used
    `` ```
    mc admin info $ alias
    mc admin policy set $ alias $ policy user = $ accesskey
    mc admin service stop $ alias
    mc admin user add $ alias $ accesskey $ secretkey
    mc admin user disable $ alias $ accesskey
    mc admin user enable $ alias $ accesskey
    mc admin user list $ alias
    mc admin user remove $ alias $ accesskey
    mc ls $ alias
    mc mb $ alias / $ bucket
    mc policy set $ policy $ alias / $ bucket
    `` ```

  --Format: Specify `--json`

  --alias alias
    --Created with `random_str ()`

  --config (`--config-dir`)
    --Place in the following directory: `$ PrivateTmp / .mc / {zoneID}`

<!-- GOMI -->

### Updating pool information

        """
        permission           -- independent from "how"
        atime_from_arg       -- ditto.   <= include_atime
        initialize           -- ditto.
        decrypt              -- ditto.

        must_exist == how not in {None, "create_zone"}
        delete_zone = how == "delete_zone"
        create_bucket = how == "update_buckets"
        change_secret = how == "change_secret_key"

        how :   create_zone {
                    assert(zone_id is None)
                    permission=None (default)
                }
            |   None {
                    permission=None (default)
                }
            |   update_zone {
                    permission=None (default)
                }
            |   update_buckets {
                    permission=None (default)
                }
            |   change_secret_key {
                    permission=None (default)
                }
            |   delete_zone {
                    permission=None (default)
                }
            |   disable_zone {
                    permission="denied"
                }
            |   enable_zone {
                    permission="allowed"
                }
            ;

        """
        """
            Update or insert zone.

            traceid: debug use

            user_id: user ID of zone to be upserted.
                     if user_id is None, the value from zone["user"] is used.
                     otherwize zone["user"] should match user_id if it exists.

            zone_ID: zoneID to be updated.
                     if zoneID is None, new zone is created.
                     On the latter case, new zoneID is generated and
                     set to zone["zoneID"]
                     (if zoneID is not None and the zone does not exist, its error)

            zone: zone values to be created or updated.
                  see below.

            permission=None,       if supplied, set zone["permission"] to the given value,
                                   otherwize calculate permission using allow-deny-rules.
            atime_from_arg=None,   if supplied, set atime on database to the given value.

            Dictionary zone consists of following items:
              zoneID:           not on db
              rootSecret:
              user:
            * group:
            * bucketsDir:
            * buckets:
            * accessKeys:
            * directHostnames:
            * expDate:
            * status:
              permission:
              atime:            not on db

            (* denotes the item is mandatory)

            When creating buckets, supply only "buckets" item:
            * buckets:

            When changing access keys, supply only "accessKeys" item:
            * accessKeys:


            "buckets" is a list of buckets.
            buckets consists of following items:
            * key:
            * policy:


            "accessKeys" is a list of accessKeys.
            accessKey consists of following items:
            * accessKeyID:
            * secretAccessKey:
            * policyName:

           When changing Secret Access Keys, "secretAccesKey" and/or "policy" may be missing.
           NOT IMPLEMENTED: When changing policy, "secretAccesKey" may be missing.
           When creating new access key, "accessKeyID" and/or "secretAccesKey" may be missing.

        we must validate zone before inserting into dictionary.
        values may be missing in user supplied zone are,
            "rootSecret", "user", "permission", "accessKeyID", and "secretAccessKey".
        "user" is set in early step.
        "rootSecret" and "secretAccessKey" may generated and set at any time.
        "permission" may be set any time.


        "accessKeyID" must generated and set while entire database is locked.


        * when creating new zone, "zoneID" must generated while entire database is locked.
          this means we cannot include "zoneID" in the error report (on error).

        SPECIAL CASE 1:
            when deleing zone, following dict is used:
            {"permission": "denied"}

        SPECIAL CASE 2:
            when changing permission, following dict is used:
            {}
        """


<!-- NEW -->

## Design notes

### Bucket-pool

A bucket-pool has a state reflecting the state of a MinIO instance.
It does not include the process status of a MinIO instance.

* Bucket-pool state (`mode`)
  * None
  * "initial"
    * indicates an alias is not set in a MinIO.
  * "ready"
    * indicates it is ready for servicing, that is, an alias and its
      access keys are set.
  * "suspended"
  * "deprecated"
    * indicates a pool will be removed.
  * "error: " + error-description-string
* Bucket-pool state changes
  * `None -> "initial" -> "ready"`

`initialize_minio` moves the state from "initial" to "ready".

A bucket-pool has another state `status`, but it is always "online".

* Bucket-pool state (status)
  * "online"
  * "offline"

### Redis database operations

* inserting a pool
  * lock db -> insert pool -> unlock
* deleting a pool
  * lock pool -> lock db -> move to deleling-state
    -> stop minio -> delete pool -> unlock -> unlock

### Redis database keys (prefixes)

#### storage-table

* storage-table
  * ac:pool-id -> timestamp
  * ar:access-key -> pool-id
  * mo:pool-id -> pool-state
  * pr:: -> list of permissions of users (json)
  * ru:pool-id -> pool-description (htable)
  * uu:user -> user-info (json)
  * dr:host -> pool-id
  * lk: -> (for locking the whole table)
  * lk:pool-id -> (for locking a ru:pool-id)

#### process-table

* process-table
  * ma:pool-id -> process-description (htable)
  * mx:host -> route-description (htable)
  * lk:?? -> (lock?)

A route-description includes:
* an endpoint of a Mux (json)
* start-time
* last-interrupted-time?

A process-description includes:
* a host of a mux,
* an endpoint of a MinIO
* a pid of a manager
* a pid of a MinIO

#### routing-table

* routing-table
  * rt:pool-id -> endpoint
  * ts:pool-id -> access-timestamp
  * bk:bucket-name -> pool-id
  * at:endpoint -> atime (* to be unused *)
  * aa:access-key -> host-port (* to be unused *)
  * da:host -> host-port (* to be unused *)

A host-port is an address to a MinIO.

### Bucket policy

Public r/w policy is given to a bucket by Lens3-UI.  Lens3-UI invokes
the mc command, one of the following.

```
mc policy set upload alias/bucket
mc policy set download alias/bucket
mc policy set public alias/bucket
```
