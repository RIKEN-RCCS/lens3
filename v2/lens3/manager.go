// Copyright 2022-2026 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// A Sentinel for an S3 Backend Server

// Manager watches backend servers and records thier outputs in logs.
// The first few lines from a backend are used to check its start.  A
// backend usually does not output anything later except on errors.

// MEMO: Manager tries to kill a backend by sudo's signal relaying,
// when a shutdown fails.  Signal relaying works because sudo runs
// with the same RUID.  The signal of a cancel function is changed
// from SIGKILL to SIGTERM.  The default in exec.Command.Cancel kills
// with SIGKILL, but it does not work with signal relaying.  See
// "src/os/exec/exec.go".
//
// MEMO: It does not use "Pdeathsig" in unix.SysProcAttr.  Pdeathsig,
// or prctl(PR_SET_PDEATHSIG), is Linux.
//
// MEMO: os.Signal is an interface, while unix.Signal and
// syscall.Signal are concrete and they are identical.

package lens3

import (
	"bufio"
	"context"
	"log"
	"log/slog"
	"maps"
	"math/rand/v2"
	"net"
	"os/exec"
	"runtime/debug"
	"slices"
	"strconv"
	"sync"
	"time"

	"golang.org/x/sys/unix"
)

// MANAGER keeps track of backend processes.  A Manager is a single
// object, "the_manager".  MUX_EP is a copy of multiplexer.mux_ep,
// which is used for printing logging messages.  FACTORY is to make a
// backend.  PROCESS holds a list of backends.  It is emptied, when
// the manager is in shutdown.  ENVIRON holds a copy of the minimal
// list of environs.  LOGPREFIX≡"Mux(ep): " is a printing name of this
// Manager.  CH_QUIT_SERVICE is to receive quitting notification.
// MUTEX protects accesses to the process list.  A Manager starts
// threads to ping backend services.
type manager struct {
	multiplexer *multiplexer

	table *keyval_table

	mux_ep string

	backend_factory backend_factory

	process              map[string]backend_delegate
	shutdown_in_progress bool

	environ []string

	ch_quit_service <-chan vacuous

	mutex sync.Mutex

	conf *mux_conf
	logger *slog.Logger

	manager_conf
}

// BACKEND_FACTORY is to make a backend instance.
type backend_factory interface {
	get_factory_generic_part() *factory_generic
	configure_factory(*mux_conf, *manager_conf)
	make_delegate(string) backend_delegate
	clean_at_exit(logger *slog.Logger)
}

// BACKEND_DELEGATE represents a backend instance.  Its concrete body
// is defined for each backend type.  GET_DELEGATE_GENERIC_PART()
// returns a generic part or a superclass.  MAKE_COMMAND_LINE()
// returns a command and environment of a backend instance.
// CHECK_STARTUP() checks a start of a backend.  It is called each
// time a backend outputs a line of a message.  It looks for a
// specific message.  The first argument indicates stdout or stderr by
// values on_stdout and on_stderr.  The passed strings are accumulated
// all from the start.  ESTABLISH() does a server specific
// initialization at its start.  SHUTDOWN() stops a backend in its
// specific way.  HEARTBEAT() pings a backend and returns an http
// status.  It is an error but status=200.
type backend_delegate interface {
	get_delegate_generic_part() *delegate_generic
	make_command_line(port int, directory string) backend_command
	check_startup(stdio_stream_indicator, []string, *slog.Logger) *start_result
	establish(*slog.Logger) error
	shutdown(*slog.Logger) error
	heartbeat(*manager, *slog.Logger) int
}

// DELEGATE_GENERIC is a common part of backend instances.  It is
// embedded in an instance of backend_delegate and it can be obtained
// by get_delegate_generic_part().  ENVIRON is the shared one in
// the_manager.  The fields {CMD, CH_STDIO, CH_QUIT_BACKEND,
// CH_QUIT_BACKEND_SEND} are set when starting a backend.  MUTEX
// protects accesses to the ch_quit_backend.
type delegate_generic struct {
	pool_record
	be      *backend_record
	factory backend_factory

	environ []string

	cmd                  *exec.Cmd
	ch_stdio             <-chan stdio_message
	ch_quit_backend      <-chan vacuous
	ch_quit_backend_send chan<- vacuous

	heartbeat_misses int

	mutex sync.Mutex
}

// FACTORY_GENERIC is a common part of a backend-factory.  It holds
// the configuration information which is shared by backend instances.
// MANAGER_CONF shares the configuration of the manager.
type factory_generic struct {
	*manager_conf
	backend_common_conf
}

// BACKEND_COMMON_CONF is common parameters to all backends.
// USE_N_PORTS is the number of ports used per backend.  It is set by
// factory's configure().  It is use_n_ports=1 usually, but
// use_n_ports=2 for RCLONE as it uses a control port.
type backend_common_conf struct {
	use_n_ports int
}

type backend_command struct {
	argv []string
	envs []string
}

// THE_MANAGER is the single multiplexer instance.
var the_manager = &manager{}

// STDIO_STREAM_INDICATOR is an indicator of which of a stream of
// stdio, stdout or stderr.  It is stored in a STDIO_MESSAGE.
type stdio_stream_indicator int

const (
	on_stdout stdio_stream_indicator = iota + 1
	on_stderr
)

// STDIO_MESSAGE is a message passed through a "ch_stdio" channel.
// Each is one line of a message.  It is keyed by ON_STDOUT or
// ON_STDERR to indicate a message is from stdout or stderr.
type stdio_message struct {
	stdio_stream_indicator
	string
}

type start_result struct {
	start_state
	reason pool_reason
}

type start_state int

const (
	start_ongoing start_state = iota
	start_started
	start_to_retry
	start_transient_failure
	start_persistent_failure
)

func configure_manager(w *manager, m *multiplexer, t *keyval_table, q chan vacuous, c *mux_conf) {
	w.table = t
	w.multiplexer = m
	w.ch_quit_service = q
	w.conf = c
	w.manager_conf = c.Manager
	w.process = make(map[string]backend_delegate)

	w.mux_ep = m.mux_ep

	var awake = (w.Backend_awake_duration).time_duration()
	w.backend_busy_suspension = (awake / 3)
	w.backend_stabilize_time = (10 * time.Millisecond)
	w.backend_linger_time = (10 * time.Millisecond)
	//w.backend_timeout_suspension = (15 * 60 * time.Second)

	w.environ = minimal_environ()

	switch c.Multiplexer.Backend {
	case backend_name_minio:
		w.backend_factory = the_backend_minio_factory
	case backend_name_rclone:
		w.backend_factory = the_backend_rclone_factory
	case backend_name_s3baby:
		w.backend_factory = the_backend_s3baby_factory
	default:
		m.logger.Error("Configuration error, unknown backend",
			"backend", c.Multiplexer.Backend)
		panic(nil)
	}

	w.backend_factory.configure_factory(c, &w.manager_conf)
}

// INITIALIZE_DELEGATE_GENERIC initializes the common part of a
// backend.  The ep and pid of a backend are set later.
func initialize_delegate_generic(w *manager, dx *delegate_generic, pooldata *pool_record) {
	dx.pool_record = *pooldata
	dx.be = &backend_record{
		Pool:        pooldata.Pool,
		Backend_ep:  "",
		Backend_pid: 0,
		State:       pool_state_READY,
		Root_access: generate_access_key(),
		Root_secret: generate_secret_key(),
		Mux_ep:      w.multiplexer.mux_ep,
		Mux_pid:     w.multiplexer.mux_pid,
		Timestamp:   0,
	}
	dx.environ = w.environ
}

// STOP_RUNNING_BACKENDS stops all backends for quitting.  Note that
// copying the map (by maps.Clone()) is unnecessary, because Golang
// allows deleting.
func stop_running_backends(w *manager) {
	var processes map[string]backend_delegate
	func() {
		w.mutex.Lock()
		defer w.mutex.Unlock()
		processes = maps.Clone(w.process)
		w.shutdown_in_progress = true
	}()
	//var belist = list_backends_under_manager(w)
	for _, d := range processes {
		abort_backend(w, d)
	}
}

// START_BACKEND mutexes among all threads in all distributed
// processes of multiplexers, for choosing one who takes the control
// of starting a backend.  Returning nil is a fatal error.
func start_backend(w *manager, pool string) *backend_record {
	var begin = time.Now()
	var ep = &backend_mutex_record{
		Mux_ep:    w.mux_ep,
		Timestamp: time.Now().Unix(),
	}
	var ok1, _ = set_ex_backend_mutex(w.table, pool, ep)
	if !ok1 {
		w.logger.Info("Wait for backend by race", "pool", pool)
		var be1 = wait_for_backend_by_race(w, pool)
		if be1 == nil {
			// (An error is already logged).
			return nil
		}
		return be1
	} else {
		w.logger.Info("Start backend", "pool", pool)
		var expiry = (2 * (w.Backend_start_timeout_ms).time_duration())
		var ok2 = set_backend_mutex_expiry(w.table, pool, expiry)
		if !ok2 {
			// Ignore an error.
			w.logger.Error("DB.Expire(backend-mutex) failed",
				"pool", pool)
		}
		var be2 = start_backend_in_mutexed(w, pool)
		if be2 == nil {
			// (An error is already logged).
			return nil
		}

		var elapse = time.Now().Sub(begin)
		w.logger.Debug("Time to start backend",
			"pool", pool, "elapse", elapse)

		//var be2 = get_backend(w.table, pool)
		return be2
	}
}

// START_BACKEND_IN_MUTEXED starts a backend, trying all available
// ports.  It fails when all ports are tried and failed.  In that
// case, a dummy record (with State=pool_state_SUSPENDED) is inserted
// in the keyval-db, which will block a further backend from starting
// for a while.  Returning nil is a fatal error.
func start_backend_in_mutexed(w *manager, pool string) *backend_record {
	//fmt.Println("start_backend()")
	//delete_backend(w.table, pool)
	defer delete_backend_mutex(w.table, pool)

	var pooldata = get_pool(w.table, pool)
	if pooldata == nil {
		w.logger.Warn("start_backend() pool is missing",
			"pool", pool)
		return nil
	}

	var f = w.backend_factory.get_factory_generic_part()
	var d = w.backend_factory.make_delegate(pool)

	// Initialize the super part.  The following fields will be set in
	// starting a backend: {dx.cmd, dx.ch_stdio,
	// dx.ch_quit_backend}

	var dx *delegate_generic = d.get_delegate_generic_part()
	initialize_delegate_generic(w, dx, pooldata)

	var available_ports = list_available_ports(w, f.use_n_ports)

	if trace_proc&tracing != 0 {
		w.logger.Debug("start_backend()", "ports", available_ports)
	}

	for _, port := range available_ports {
		var r1 = try_start_backend(w, d, port)
		switch r1.start_state {
		case start_ongoing:
			// (NEVER).
			w.logger.Error("BAD-IMPL: Starting backend fatally failed",
				"pool", pool)
			panic(nil)
		case start_started:
			// Okay.
		case start_to_retry:
			continue
		case start_transient_failure:
			// (An error is already logged).
			var suspension = suspend_pool(w, d, r1.reason)
			return suspension
		case start_persistent_failure:
			// (An error is already logged).
			mark_pool_inoperable(w, pooldata, r1.reason)
			return nil
		}

		assert_fatal(dx.cmd.Process != nil)
		//var pid = dx.cmd.Process.Pid

		var ok1 bool
		func() {
			w.mutex.Lock()
			defer w.mutex.Unlock()
			if !w.shutdown_in_progress {
				w.process[pool] = d
				ok1 = true
			} else {
				ok1 = false
			}
		}()
		if !ok1 {
			w.logger.Warn("Starting backend aborted",
				"pool", pool, "reason", "manager is in shutdown")
			abort_backend(w, d)
			return nil
		}

		go disgorge_stdio_to_log(w, dx)

		// Sleep shortly for a backend to be stable.

		time.Sleep(w.backend_stabilize_time)

		d.establish(w.logger)

		var err1 = make_absent_buckets_in_backend(w, dx.be)
		if err1 != nil {
			// (An error is already logged).
			// LET A BACKEND CONTINUE TO WORK.
			// - abort_backend(w, d)
			// - mark_pool_inoperable(w, pooldata, reason)
			// - return nil
		}

		var now = time.Now().Unix()
		dx.be.Timestamp = now
		set_backend(w.table, pool, dx.be)

		// Backend has started.  Expiration of the backend record is
		// set in ping_backend().

		go ping_backend(w, d)

		var state1 = &approximate_state_record{
			Pool:      pool,
			State:     pool_state_READY,
			Reason:    pool_reason_NORMAL,
			Timestamp: now,
		}
		set_approximate_state(w.table, pool, state1)

		return dx.be
	}

	// All ports are tried and failed.

	w.logger.Warn("Backend SUSPENDED (no ports)", "pool", pool)

	var suspension = suspend_pool(w, d, start_failure_server_busy)
	return suspension
}

// TRY_START_BACKEND starts a process and waits for a message or a
// timeout.  A message from the backend is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_backend(w *manager, d backend_delegate, port int) *start_result {
	var dx *delegate_generic = d.get_delegate_generic_part()
	var pool = dx.Pool
	var thishost, _, err1 = net.SplitHostPort(w.mux_ep)
	if err1 != nil {
		w.logger.Error("Bad endpoint of Mux", "ep", w.mux_ep)
		panic(nil)
	}
	dx.be.Backend_ep = net.JoinHostPort(thishost, strconv.Itoa(port))
	if trace_proc&tracing != 0 {
		w.logger.Debug("try_start_backend()",
			"ep", dx.be.Backend_ep)
	}

	var user = dx.Owner_uid
	var group = dx.Owner_gid
	var directory = dx.Bucket_directory
	var command = d.make_command_line(port, directory)
	var sudo_argv = []string{
		w.Sudo,
		"-n",
		"-u", user,
		"-g", group}
	var argv = append(sudo_argv, command.argv...)
	var envs = append(w.environ, command.envs...)

	w.logger.Debug("Run backend", "pool", pool, "argv", argv)

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	if cmd == nil {
		w.logger.Error("exec.Command() returned nil")
		panic(nil)
	}
	assert_fatal(cmd.SysProcAttr == nil)

	cmd.Env = envs
	cmd.SysProcAttr = &unix.SysProcAttr{
		// Note (?) it fails with: Noctty=true
		Setsid:     false,
		Setctty:    false,
		Noctty:     false,
		Foreground: false,
	}
	cmd.Cancel = func() error {
		return cmd.Process.Signal(unix.SIGTERM)
	}
	cmd.Stdin = nil

	var ch_stdio = make(chan stdio_message)
	var ch_quit_backend = make(chan vacuous)
	dx.cmd = cmd
	dx.ch_stdio = ch_stdio
	dx.ch_quit_backend = ch_quit_backend
	dx.ch_quit_backend_send = ch_quit_backend

	start_disgorging_stdio(w, d, ch_stdio)

	var err3 = cmd.Start()
	if err3 != nil {
		w.logger.Error("exec.Command.Start() errs", "err", err3)
		return &start_result{
			start_state: start_persistent_failure,
			reason:      start_failure_exec_failed,
		}
	}

	dx.be.Backend_pid = cmd.Process.Pid
	var r1 = wait_for_backend_come_up(w, d)

	if trace_proc&tracing != 0 {
		w.logger.Debug("Starting backend finished (succeed/fail)",
			"pool", pool, "state", r1.start_state, "reason", r1.reason)
	}

	assert_fatal(r1.start_state != start_ongoing)

	return r1
}

// WAIT_FOR_BACKEND_COME_UP waits until a backend either (1) outputs
// an expected message, (2) outputs an error message, (3) outputs too
// many messages, (4) closes both stdout+stderr, (5) reaches a
// timeout.  It returns STARTED/RETRY/FAILURE.  It reads the stdio
// channels as much as available.
func wait_for_backend_come_up(w *manager, d backend_delegate) *start_result {
	var dx *delegate_generic = d.get_delegate_generic_part()
	var f = dx.factory.get_factory_generic_part()
	var pool = dx.Pool

	var msg_stdout []string
	var msg_stderr []string

	// It makes a closure in stead of directly defering a call, so
	// that to refer to finally collected msg_stdout and msg_stderr.

	defer func() {
		drain_start_messages_to_log(w, pool, msg_stdout, msg_stderr)
	}()

	var timeout = (f.Backend_start_timeout_ms).time_duration()
	var ch_timeout = time.After(timeout)
	for {
		select {
		case msg1, ok1 := <-dx.ch_stdio:
			if !ok1 {
				w.logger.Warn("Starting backend failed",
					"pool", pool, "reason", start_failure_pipe_closed)
				return &start_result{
					start_state: start_persistent_failure,
					reason:      start_failure_pipe_closed,
				}
			}
			var some_messages_on_stdout bool = false
			var some_messages_on_stderr bool = false
			switch msg1.stdio_stream_indicator {
			case on_stdout:
				msg_stdout = append(msg_stdout, msg1.string)
				some_messages_on_stdout = true
			case on_stderr:
				msg_stderr = append(msg_stderr, msg1.string)
				some_messages_on_stderr = true
			}
			// Sleep for a short time for stdio messages.
			// (* time.Sleep(10 * time.Millisecond) *)
			for len(msg_stdout) < 500 && len(msg_stderr) < 500 {
				select {
				case msg2, ok2 := <-dx.ch_stdio:
					if !ok2 {
						break
					}
					switch msg2.stdio_stream_indicator {
					case on_stdout:
						msg_stdout = append(msg_stdout, msg2.string)
						some_messages_on_stdout = true
					case on_stderr:
						msg_stderr = append(msg_stderr, msg2.string)
						some_messages_on_stderr = true
					}
					continue
				default:
					break
				}
				break
			}
			if some_messages_on_stdout {
				var st1 = d.check_startup(on_stdout, msg_stdout, w.logger)
				switch st1.start_state {
				case start_ongoing:
					// Skip.
				case start_transient_failure, start_persistent_failure:
					w.logger.Warn("Starting backend failed",
						"pool", pool, "reason", st1.reason)
					return st1
				default:
					return st1
				}
			}
			if some_messages_on_stderr {
				var st1 = d.check_startup(on_stderr, msg_stderr, w.logger)
				switch st1.start_state {
				case start_ongoing:
					// Skip.
				default:
					return st1
				}
			}
			if !(len(msg_stdout) < 500 && len(msg_stderr) < 500) {
				w.logger.Warn("Starting backend failed",
					"pool", pool, "reason", start_failure_stdio_flooding)
				return &start_result{
					start_state: start_persistent_failure,
					reason:      start_failure_stdio_flooding,
				}
			}
			continue
		case <-ch_timeout:
			w.logger.Warn("Starting backend failed",
				"pool", pool, "reason", start_failure_start_timeout)
			return &start_result{
				start_state: start_transient_failure,
				reason:      start_failure_start_timeout,
			}
		}
	}
}

// WAIT_FOR_BACKEND_BY_RACE waits until a start of a backend that is
// started by another thread.  It uses polling.  Its sleep time
// increases each time: 1ms, 3^1ms, 3^2ms, ... until maximum 1s.
func wait_for_backend_by_race(w *manager, pool string) *backend_record {
	var limit = time.Now().Add((w.Backend_start_timeout_ms).time_duration())
	var sleep int64 = 1
	for time.Now().Before(limit) {
		var be1 = get_backend(w.table, pool)
		if be1 != nil {
			return be1
		}
		time.Sleep(time.Duration(sleep) * time.Millisecond)
		sleep = min(sleep*3, 1000)
	}
	w.logger.Error("Wait for backend by race failed by timeout",
		"pool", pool)
	return nil
}

// SUSPEND_POOL puts a pool in the suspended state.  It will block the
// service for a certain period.
func suspend_pool(w *manager, d backend_delegate, reason pool_reason) *backend_record {
	var dx *delegate_generic = d.get_delegate_generic_part()
	var f = dx.factory.get_factory_generic_part()
	var pool = dx.Pool

	var duration time.Duration
	switch reason {
	case start_failure_server_busy:
		duration = f.backend_busy_suspension
	case start_failure_start_timeout:
		duration = (f.Backend_timeout_suspension).time_duration()
	default:
		duration = (f.Backend_timeout_suspension).time_duration()
	}

	var now int64 = time.Now().Unix()
	var suspension = &backend_record{
		Pool:        pool,
		Backend_ep:  "",
		Backend_pid: 0,
		State:       pool_state_SUSPENDED,
		Root_access: "",
		Root_secret: "",
		Mux_ep:      w.multiplexer.mux_ep,
		Mux_pid:     w.multiplexer.mux_pid,
		Timestamp:   now,
	}
	set_backend(w.table, pool, suspension)
	var ok3 = set_backend_expiry(w.table, pool, duration)
	if !ok3 {
		w.logger.Error("DB.Expire(dummy-backend) failed",
			"pool", pool)
	}

	var state2 = &approximate_state_record{
		Pool:      pool,
		State:     pool_state_SUSPENDED,
		Reason:    reason,
		Timestamp: now,
	}
	set_approximate_state(w.table, pool, state2)

	return suspension
}

// MARK_POOL_INOPERABLE makes a pool inoperable.
func mark_pool_inoperable(w *manager, pooldata *pool_record, reason pool_reason) {
	if pooldata.Inoperable {
		return
	}
	pooldata.Inoperable = true
	pooldata.Reason = reason
	pooldata.Timestamp = time.Now().Unix()
	set_pool(w.table, pooldata.Pool, pooldata)
}

// ABORT_BACKEND tells the pinger thread to shutdown the backend.
func abort_backend(w *manager, d backend_delegate) {
	var dx *delegate_generic = d.get_delegate_generic_part()
	func() {
		dx.mutex.Lock()
		defer dx.mutex.Unlock()
		if dx.ch_quit_backend_send != nil {
			close(dx.ch_quit_backend_send)
			dx.ch_quit_backend_send = nil
		}
	}()
}

// PING_BACKEND performs heartbeating in its thread.  It will shutdown
// the backend, either when heartbeating fails or it is instructed to
// stop the backend.
func ping_backend(w *manager, d backend_delegate) {
	defer func() {
		var x = recover()
		if x != nil {
			w.logger.Error("Pinger errs", "err", x,
				"stack", string(debug.Stack()))
		}
	}()

	var dx *delegate_generic = d.get_delegate_generic_part()
	var f = dx.factory.get_factory_generic_part()
	var pool = dx.Pool
	var duration = (w.Backend_awake_duration).time_duration()
	var interval = (f.Heartbeat_interval).time_duration()
	var expiry = (3 * (f.Heartbeat_interval).time_duration())
	var ok1 = set_backend_expiry(w.table, pool, expiry)
	if !ok1 {
		w.logger.Error("DB.Expire(backend) failed",
			"pool", pool, "action", "(ignored)")
	}

	dx.heartbeat_misses = 0
	for {
		var ok2 bool
		select {
		case _, ok2 = <-dx.ch_quit_backend:
			assert_fatal(!ok2)
			break
		default:
		}
		time.Sleep(interval)

		// Do heatbeat.

		var status = d.heartbeat(w, w.logger)
		if status == 200 {
			dx.heartbeat_misses = 0
		} else {
			dx.heartbeat_misses += 1
		}
		if dx.heartbeat_misses > 0 {
			w.logger.Error("Heartbeat failed",
				"pool", pool, "misses", dx.heartbeat_misses)
		} else if trace_proc&tracing != 0 {
			w.logger.Debug("Heartbeat", "pool", pool,
				"status", status, "misses", dx.heartbeat_misses)
		}
		if dx.heartbeat_misses > w.Heartbeat_miss_tolerance {
			break
		}

		// Check lifetime.  Missing pool timestamp means the awake
		// time elapsed (ts=0 is infinite past).

		var ts = get_pool_timestamp(w.table, pool)
		var lifetime = time.Unix(ts, 0).Add(duration)
		if !time.Now().Before(lifetime) {
			w.logger.Debug("Awake time elapsed", "pool", pool)
			break
		}

		// Update a record expiration.

		var ok3 = set_backend_expiry(w.table, pool, expiry)
		if !ok3 {
			w.logger.Error("DB.Expire(backend) failed",
				"pool", pool, "action", "quit backend")
			break
		}
	}
	stop_backend(w, d)
	wait4_child_process(w, d)
}

// STOP_BACKEND calls backend's shutdown().  Note that there is a race
// in checking a backend existence and stopping a backend.  That is,
// it would be possible some requests are sent to a backend while it
// is going to be shutdown.  It waits for a short time to avoid the
// race, assuming all requests are finished in the wait.
func stop_backend(w *manager, d backend_delegate) {
	var dx *delegate_generic = d.get_delegate_generic_part()
	var pool = dx.Pool
	w.logger.Info("Stop backend", "pool", pool)

	func() {
		w.mutex.Lock()
		defer w.mutex.Unlock()
		delete(w.process, pool)
	}()
	delete_backend_mutex(w.table, pool)
	delete_backend(w.table, pool)

	time.Sleep(w.backend_linger_time)

	var err1 = d.shutdown(w.logger)
	if err1 != nil {
		w.logger.Error("Backend shutdown() failed",
			"pool", pool, "err", err1)
	}
	if err1 == nil {
		return
	}
	var err2 = dx.cmd.Cancel()
	if err2 != nil {
		w.logger.Error("exec.Command.Cancel() on backend failed",
			"pool", pool, "err", err2)
	}
}

// START_DISGORGING_STDIO emits stdout+stderr outputs from a backend
// to the ch_stdio channel.  It spawns threads and returns
// immediately.  It drains one line at a time.  It will stop the
// backend when both the stdout+stderr are closed.
func start_disgorging_stdio(w *manager, d backend_delegate, ch_stdio chan<- stdio_message) {
	var dx *delegate_generic = d.get_delegate_generic_part()
	var cmd *exec.Cmd = dx.cmd

	var stdout1, err1 = cmd.StdoutPipe()
	if err1 != nil {
		log.Fatal(err1)
	}
	var stderr1, err2 = cmd.StderrPipe()
	if err2 != nil {
		log.Fatal(err2)
	}

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		var c1 = bufio.NewScanner(stdout1)
		for c1.Scan() {
			var s1 = c1.Text()
			ch_stdio <- stdio_message{on_stdout, s1}
		}
	}()

	go func() {
		defer wg.Done()
		var c2 = bufio.NewScanner(stderr1)
		for c2.Scan() {
			var s2 = c2.Text()
			ch_stdio <- stdio_message{on_stderr, s2}
		}
	}()

	go func() {
		wg.Wait()
		close(ch_stdio)
		abort_backend(w, d)
	}()
}

// DISGORGE_STDIO_TO_LOG dumps stdout+stderr messages to the logger.
// It receives messages written by threads started in
// start_disgorging_stdio().
func disgorge_stdio_to_log(w *manager, dx *delegate_generic) {
	var pool = dx.Pool
	for {
		var x1, ok1 = <-dx.ch_stdio
		if !ok1 {
			break
		}
		//fmt.Println("LINE: ", x1.int, x1.string)
		//var m = strings.TrimSpace(x1.string)
		var m = x1.string
		if x1.stdio_stream_indicator == on_stdout {
			w.logger.Info("backend-stdout", "pool", pool, "stdout", m)
		} else {
			w.logger.Info("backend-stderr", "pool", pool, "stderr", m)
		}
	}
	if trace_proc&tracing != 0 {
		w.logger.Debug("stdio dumper done", "pool", pool)
	}
}

// DRAIN_START_MESSAGES_TO_LOG outputs messages to a log, that are
// stored for checking a proper start of a backend.
func drain_start_messages_to_log(w *manager, pool string, stdouts []string, stderrs []string) {
	// fmt.Println("drain_start_messages_to_log()")
	var s string
	for _, s = range stdouts {
		w.logger.Info("backend-stdout", "pool", pool, "stdout", s)
	}
	for _, s = range stderrs {
		w.logger.Info("backend-stderr", "pool", pool, "stderr", s)
	}
}

// LIST_AVAILABLE_PORTS lists ports available.  It drops the ports
// used by backends running under this Multiplexer locally.  It uses
// each integer skipping by use_n_ports.  It randomizes the order of
// the list.
func list_available_ports(w *manager, use_n_ports int) []int {
	assert_fatal(use_n_ports == 1 || use_n_ports == 2)

	var belist = list_backends_under_manager(w)
	var used []int
	for _, be := range belist {
		assert_fatal(be.Mux_ep == w.mux_ep)
		var _, ps, err1 = net.SplitHostPort(be.Backend_ep)
		if err1 != nil {
			w.logger.Error("Bad endpoint",
				"ep", be.Backend_ep, "err", err1)
			panic(nil)
		}
		var port, err2 = strconv.Atoi(ps)
		if err2 != nil {
			w.logger.Error("Bad endpoint",
				"ep", be.Backend_ep, "err", err2)
			panic(nil)
		}
		used = append(used, port)
	}

	var ports []int
	for i := w.Port_min; i <= w.Port_max; i++ {
		if (i%use_n_ports) == 0 && (i+(use_n_ports-1)) <= w.Port_max {
			if slices.Index(used, i) == -1 {
				ports = append(ports, i)
			}
		}
	}
	rand.Shuffle(len(ports), func(i, j int) {
		ports[i], ports[j] = ports[j], ports[i]
	})
	return ports
}

func list_backends_under_manager(w *manager) []*backend_record {
	var belist = list_backends(w.table, "*")
	var list []*backend_record
	for _, be := range belist {
		if be.Mux_ep != w.mux_ep {
			continue
		}
		if be.State == pool_state_SUSPENDED {
			// Skip a dummy entry.
			continue
		}
		list = append(list, be)
	}
	return list
}

func wait4_child_process(w *manager, d backend_delegate) {
	var dx *delegate_generic = d.get_delegate_generic_part()
	var pid = dx.cmd.Process.Pid
	//var pid = dx.be.Backend_pid
	for {
		//var options int = unix.WNOHANG
		var options int = 0
		var wstatus unix.WaitStatus
		var rusage unix.Rusage
		var wpid, err1 = unix.Wait4(pid, &wstatus, options, &rusage)
		if err1 != nil {
			var err2, ok1 = err1.(unix.Errno)
			assert_fatal(ok1)
			w.logger.Warn("wait4() errs",
				"errno", unix.ErrnoName(err2))
			if err2 == unix.EINVAL || err2 == unix.ECHILD {
				break
			} else {
				continue
			}
		}
		if wpid == 0 {
			w.logger.Warn("wait4() failed",
				"errno", unix.ErrnoName(unix.ECHILD))
			continue
		}
		if trace_proc&tracing != 0 {
			w.logger.Debug("wait4() returns",
				"pid", wpid, "status", wstatus, "rusage", rusage)
		} else {
			w.logger.Debug("wait4() returns",
				"pid", wpid, "status", wstatus)
		}
		break
	}
}

// MAKE_ABSENT_BUCKETS_IN_BACKEND makes consistent about buckets in a
// Registrar's record and buckets in the backend.  It runs during
// starting a backend and when requested by Registrar.  It ignores
// errors from the backend but returns the first one.  Calling
// get_backend() won't work yet, because the record has not been set
// in the keyval-db.
func make_absent_buckets_in_backend(w *manager, be *backend_record) error {
	var pool = be.Pool

	var buckets_needed = gather_buckets(w.table, pool)
	var buckets_exsting, err1 = list_buckets_in_backend(w, be, w.logger)
	if err1 != nil {
		// (An error is already logged).
		return err1
	}

	w.logger.Debug("Check existing buckets in backend",
		"pool", pool, "buckets", buckets_exsting)

	var errx error = nil

	var now = time.Now()
	for _, b := range buckets_needed {
		if slices.Contains(buckets_exsting, b.Bucket) {
			continue
		}
		var expiration = time.Unix(b.Expiration_time, 0)
		if !now.Before(expiration) {
			continue
		}

		w.logger.Debug("Make a bucket in backend",
			"pool", pool, "bucket", b.Bucket)

		var err2 = make_bucket_in_backend(w, be, b, w.logger)
		if err2 != nil && errx == nil {
			// (An error is already logged).
			errx = err2
		}
	}
	return errx
}
