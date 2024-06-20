/* A sentinel of an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A manager watches the backend server state and records its outputs
// in logs.  The first few lines from the backend is used to check its
// start.  Backends usually do not output anything later except on
// errors.

// MEMO: A manager tries to kill a backend by sudo's signal relaying,
// when a shutdown fails.  Signal relaying works because sudo runs
// with the same RUID.  Note that killpg won't work.  A cancel
// function is replaced by one with SIGTERM.  The default in
// exec/Command.Cancel kills with SIGKILL, but it does not work with
// sudo.  See "src/os/exec/exec.go".
//
// MEMO: It does not use "Pdeathsig" in "unix.SysProcAttr".
// Pdeathsig, or prctl(PR_SET_PDEATHSIG), is Linux.
//
// MEMO: os.Signal is an interface, while unix.Signal, syscall.Signal
// are identical and concrete.

import (
	"bufio"
	"context"
	"golang.org/x/sys/unix"
	"log"
	"math/rand/v2"
	"net"
	"os/exec"
	"slices"
	"strconv"
	"sync"
	"time"
	//"bytes"
	//"encoding/json"
	//"fmt"
	//"io"
	//"log/slog"
	//"os"
	//"os/signal"
	//"os/user"
	//"reflect"
	//"reflect"
	//"runtime"
	//"strings"
	//"syscall"
	//"testing"
	//"time"
)

// MANAGER keeps track of backend processes.  Manager is a single
// object, "the_manager".  It is with threads to wait for child
// processes.
type manager struct {
	// MuxEP="Mux(ep)" is a printing name of this Manager.
	MuxEP string

	multiplexer *multiplexer

	table *keyval_table

	// MUX_EP is a copy of multiplexer.mux_ep, used for printing
	// logging messages.
	mux_ep string

	// BE factory is to make a backend.
	factory backend_factory

	// PROCESS holds a list of backends.  It is emptied, when the
	// manager is in shutdown.
	process              map[string]backend
	shutdown_in_progress bool

	// ENVIRON holds a copy of the minimal list of environs.
	environ []string

	// CH_QUIT is to receive quitting notification.
	ch_quit_service <-chan vacuous

	// MUTEX protects accesses to the processes list.
	mutex sync.Mutex

	conf *mux_conf
	manager_conf
}

// BACKEND_FACTORY is to make a backend instance.
type backend_factory interface {
	configure(conf *mux_conf)
	make_delegate(string) backend
	clean_at_exit()
}

// BACKEND is a backend specific part.  A backend shall not start its
// long-running threads.  Or, it lets them enter a wait-group.
type backend interface {
	// GET_SUPER_PART returns a generic part or a superclass.
	get_super_part() *backend_delegate

	// MAKE_COMMAND_LINE returns a command and environment of a
	// backend instance.
	make_command_line(port int, directory string) backend_command

	// CHECK_STARTUP checks a start of a backend.  It is called each
	// time a backend outputs a line of a message.  It looks for a
	// specific message.  The first argument indicates stdout or
	// stderr by values on_stdout and on_stderr.  The passed strings
	// are accumulated ones all from the start.
	check_startup(stdio_stream, []string) start_result

	// ESTABLISH does a server specific initialization at its start.
	establish() error

	// SHUTDOWN stops a backend in its specific way.
	shutdown() error

	// HEARTBEAT pings a backend and returns an http status.  It is an
	// error but status=200.
	heartbeat(w *manager) int
}

// BACKEND_DELEGATE is a generic part of a backend.  It is embedded in
// a backend instance and obtained by get_super_part().  A
// configuration "manager_conf" is shared with the manager.
type backend_delegate struct {
	pool_record
	be *backend_record

	verbose bool

	// ENVIRON is the shared one in the_manager.
	environ *[]string

	// The following fields {cmd,ch_stdio,ch_quit_backend} are set
	// when starting a backend.
	cmd                  *exec.Cmd
	ch_stdio             <-chan stdio_message
	ch_quit_backend      <-chan vacuous
	ch_quit_backend_send chan<- vacuous

	heartbeat_misses int

	// MUTEX protects accesses to the ch_quit_backend.
	mutex sync.Mutex

	*manager_conf
	*backend_conf
}

// BACKEND_CONF is static parameters that are thought to be a part of
// manager_conf.  It is set by factory's make_delegate().
type backend_conf struct {
	// USE_N_PORTS is the number of ports used per backend.  It is
	// MinIO:1 and rclone:2.
	use_n_ports int
}

type backend_command struct {
	argv []string
	envs []string
}

// THE_MANAGER is the single multiplexer instance.
var the_manager = &manager{}

// STDIO_STREAM is an indicator of which of a stream of stdio, stdout
// or stderr.  It is stored in a STDIO_MESSAGE.
type stdio_stream int

const (
	on_stdout stdio_stream = iota + 1
	on_stderr
)

// STDIO_MESSAGE is a message passed through a "ch_stdio" channel.
// Each is one line of a message.  It is keyed by ON_STDOUT or
// ON_STDERR to indicate a message is from stdout or stderr.
type stdio_message struct {
	stdio_stream
	string
}

type start_result struct {
	start_state
	message string
}

type start_state int

const (
	start_ongoing start_state = iota
	start_started
	start_to_retry
	start_failed
)

func configure_manager(w *manager, m *multiplexer, t *keyval_table, q chan vacuous, c *mux_conf) {
	w.table = t
	w.multiplexer = m
	w.ch_quit_service = q
	w.conf = c
	w.manager_conf = c.Manager
	w.process = make(map[string]backend)

	w.MuxEP = m.MuxEP
	w.mux_ep = m.mux_ep

	w.backend_stabilize_ms = 10
	w.backend_linger_ms = 10

	w.watch_gap_minimal = 10
	w.manager_expiration = 1000

	//w.ch_sig = set_signal_handling()
	w.environ = minimal_environ()

	switch c.Multiplexer.Backend {
	case "minio":
		w.factory = the_backend_minio_factory
	case "rclone":
		w.factory = the_backend_rclone_factory
	default:
		slogger.Error(w.MuxEP+" Configuration error, unknown backend",
			"backend", c.Multiplexer.Backend)
		panic(nil)
	}

	w.factory.configure(c)
}

// INITIALIZE_BACKEND_DELEGATE initializes the super part of a
// backend.  The ep and pid of a backend are set later.
func initialize_backend_delegate(w *manager, proc *backend_delegate, pooldata *pool_record) {
	proc.pool_record = *pooldata
	proc.be = &backend_record{
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
	proc.verbose = true
	proc.environ = &w.environ
	proc.manager_conf = &w.manager_conf
}

func stop_running_backends(w *manager) {
	var processes map[string]backend
	func() {
		w.mutex.Lock()
		defer w.mutex.Unlock()
		processes = w.process
		w.process = nil
		w.shutdown_in_progress = true
	}()
	//var bes = list_backends_under_manager(w)
	for _, d := range processes {
		tell_stop_backend(w, d)
	}
}

// START_BACKEND mutexes among all threads in all distributed
// processes of multiplexers, for choosing one who takes the control
// of starting a backend.
func start_backend(w *manager, pool string) backend {
	var now int64 = time.Now().Unix()
	var ep = &backend_exclusion_record{
		Mux_ep:    w.mux_ep,
		Timestamp: now,
	}
	var ok1, _ = set_ex_backend_exclusion(w.table, pool, ep)
	if !ok1 {
		var be1 = wait_for_backend_by_race(w, pool)
		if be1 == nil {
			slogger.Debug(w.MuxEP+" start_backend waits by race", "pool", pool)
		}
		return nil
	} else {
		var expiry int64 = int64(3 * w.Backend_start_timeout)
		var ok2 = set_backend_exclusion_expiry(w.table, pool, expiry)
		if !ok2 {
			// Ignore an error.
			slogger.Error(w.MuxEP + " Bad call set_backend_exclusion_expiry()")
		}
		var be2 = start_backend_in_mutexed(w, pool)
		return be2
	}
}

// START_BACKEND_IN_MUTEXED starts a backend, trying available ports.
// It fails when all ports are tried and failed.  In that case, a
// dummy backend record is stored in the keyval-db, to block a backend
// from further starting for a while.
func start_backend_in_mutexed(w *manager, pool string) backend {
	//fmt.Println("start_backend()")
	//delete_backend(w.table, pool)
	defer delete_backend_exclusion(w.table, pool)

	var pooldata = get_pool(w.table, pool)
	if pooldata == nil {
		slogger.Warn(w.MuxEP+" start_backend() pool is missing", "pool", pool)
		return nil
	}

	var d = w.factory.make_delegate(pool)

	// Initialize the super part.

	var proc *backend_delegate = d.get_super_part()
	initialize_backend_delegate(w, proc, pooldata)
	var be *backend_record = proc.be

	// The following fields are set in starting a backend: {proc.cmd,
	// proc.ch_stdio, proc.ch_quit_backend}

	var available_ports = list_available_ports(w, proc.use_n_ports)

	if proc.verbose {
		slogger.Debug(w.MuxEP+" start_backend()", "ports", available_ports)
	}

	for _, port := range available_ports {
		var r1 = try_start_backend(w, d, port)
		switch r1.start_state {
		case start_ongoing:
			slogger.Error(w.MuxEP+" Starting a backend failed (timeout)",
				"pool", pool)
			return nil
		case start_started:
			// OK.
		case start_to_retry:
			continue
		case start_failed:
			slogger.Error(w.MuxEP+" Starting a backend failed",
				"pool", pool, "msg", r1.message)
			return nil
		}

		assert_fatal(proc.cmd.Process != nil)
		//var pid = proc.cmd.Process.Pid

		var ok bool
		func() {
			w.mutex.Lock()
			defer w.mutex.Unlock()
			if !w.shutdown_in_progress {
				w.process[pool] = d
				ok = true
			} else {
				ok = false
			}
		}()
		if !ok {
			slogger.Warn(w.MuxEP+" Starting a backend failed",
				"pool", pool, "msg", "manager is in shutdown")
			tell_stop_backend(w, d)
			return nil
		}

		go disgorge_stdio_to_log(w, proc)

		// Sleep for a while for a backend to be stable.

		time.Sleep(time.Duration(w.backend_stabilize_ms) * time.Millisecond)

		d.establish()

		make_absent_buckets_in_backend(w, be)

		go ping_backend(w, d)

		var now int64 = time.Now().Unix()
		be.Timestamp = now
		set_backend(w.table, pool, be)
		return d
	}

	// All ports are tried and failed.

	slogger.Warn(w.MuxEP+" A backend SUSPENDED (no ports)", "pool", pool)

	var now int64 = time.Now().Unix()
	var dummy = &backend_record{
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
	var expiry = int64(proc.Backend_awake_duration / 3)
	set_backend(w.table, pool, dummy)
	set_backend_expiry(w.table, proc.Pool, expiry)

	var state = pool_state_SUSPENDED
	var reason = pool_reason_SERVER_BUSY
	set_pool_state(w.table, pool, state, reason)
	return nil
}

// TRY_START_BACKEND starts a process and waits for a message or a
// timeout.  A message from the backend is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_backend(w *manager, d backend, port int) start_result {
	var proc = d.get_super_part()
	var thishost, _, err1 = net.SplitHostPort(w.mux_ep)
	if err1 != nil {
		slogger.Error(w.MuxEP+" Bad endpoint of Mux", "ep", w.mux_ep)
		panic(nil)
	}
	proc.be.Backend_ep = net.JoinHostPort(thishost, strconv.Itoa(port))
	if proc.verbose {
		slogger.Debug(w.MuxEP+" try_start_backend()", "ep", proc.be.Backend_ep)
	}

	var user = proc.Owner_uid
	var group = proc.Owner_gid
	var directory = proc.Buckets_directory
	var command = d.make_command_line(port, directory)
	var sudo_argv = []string{
		w.Sudo,
		"-n",
		"-u", user,
		"-g", group}
	var argv = append(sudo_argv, command.argv...)
	var envs = append(w.environ, command.envs...)

	slogger.Debug(w.MuxEP+" Run a backend", "pool", proc.Pool, "argv", argv)

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	if cmd == nil {
		slogger.Error(w.MuxEP + " exec.Command() returned nil")
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
	proc.cmd = cmd
	proc.ch_stdio = ch_stdio
	proc.ch_quit_backend = ch_quit_backend
	proc.ch_quit_backend_send = ch_quit_backend

	start_disgorging_stdio(w, d, ch_stdio)

	var err3 = cmd.Start()
	if err3 != nil {
		slogger.Error("exec.Command.Start() failed", "err", err3)
		return start_result{
			start_state: start_failed,
			message:     err3.Error(),
		}
	}

	proc.be.Backend_pid = cmd.Process.Pid
	var r1 = wait_for_backend_come_up(w, d)

	if proc.verbose {
		slogger.Debug(w.MuxEP+" A backend started",
			"pool", proc.Pool, "state", r1.start_state, "msg", r1.message)
	}

	assert_fatal(r1.start_state != start_ongoing)

	return r1
}

// WAIT_FOR_BACKEND_COME_UP waits until either a backend server (1)
// outputs an expected message, (2) outputs an error message, (3)
// outputs too many messages, (4) reaches a timeout, (5) closes both
// stdout+stderr.  It returns STARTED/FAILED/TO_RETRY.  It reads the
// stdio channels as much as available.
func wait_for_backend_come_up(w *manager, d backend) start_result {
	var proc *backend_delegate = d.get_super_part()
	// fmt.Printf("WAIT_FOR_BACKEND_COME_UP() svr=%T proc=%T\n", svr, proc)

	var msg_stdout []string
	var msg_stderr []string

	// It makes a closure in stead of directly defering a call, so
	// that to refer to finally collected msg_stdout and msg_stderr.

	defer func() {
		drain_start_messages_to_log(w, proc.Pool, msg_stdout, msg_stderr)
	}()

	var timeout = (time.Duration(proc.Backend_start_timeout) * time.Second)
	var ch_timeout = time.After(timeout)
	for {
		select {
		case msg1, ok1 := <-proc.ch_stdio:
			if !ok1 {
				return start_result{
					start_state: start_failed,
					message:     "pipe closed",
				}
			}
			var some_messages_on_stdout bool = false
			var some_messages_on_stderr bool = false
			switch msg1.stdio_stream {
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
				case msg2, ok2 := <-proc.ch_stdio:
					if !ok2 {
						break
					}
					switch msg2.stdio_stream {
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
				var st1 = d.check_startup(on_stdout, msg_stdout)
				switch st1.start_state {
				case start_ongoing:
					// Skip.
				default:
					return st1
				}
			}
			if some_messages_on_stderr {
				var st1 = d.check_startup(on_stderr, msg_stderr)
				switch st1.start_state {
				case start_ongoing:
					// Skip.
				default:
					return st1
				}
			}
			if !(len(msg_stdout) < 500 && len(msg_stderr) < 500) {
				return start_result{
					start_state: start_failed,
					message:     "stdout/stderr flooding",
				}
			}
			continue
		case <-ch_timeout:
			return start_result{
				start_state: start_failed,
				message:     "timeout",
			}
		}
	}
}

// It sleeps in 1ms, 3^1ms, 3^2ms, ... and 1s, and keeps sleeping in 1s
// until a timeout.
func wait_for_backend_by_race(w *manager, pool string) *backend_record {
	slogger.Debug(w.MuxEP+" Waiting for a backend by race", "pool", pool)
	var sleep int64 = 1
	var limit = time.Now().Add(
		(time.Duration(w.Backend_start_timeout) * time.Second) +
			(time.Duration(w.Backend_setup_timeout) * time.Second))
	for time.Now().Compare(limit) < 0 {
		var be1 = get_backend(w.table, pool)
		if be1 != nil {
			return be1
		}
		time.Sleep(time.Duration(sleep) * time.Millisecond)
		if sleep < 1000 {
			sleep = sleep * 3
		} else {
			sleep = 1000
		}
	}
	slogger.Debug(w.MuxEP+" Waiting for a backend by race failed", "pool", pool)
	return nil
}

// COMMAND_TO_STOP_BACKEND tells the pinger thread to shutdown the backend.
func command_to_stop_backend(w *manager, pool string) {
	var d backend
	func() {
		w.mutex.Lock()
		defer w.mutex.Unlock()
		d = w.process[pool]
	}()
	if d == nil {
		return
	}
	tell_stop_backend(w, d)
}

// TELL_STOP_BACKEND tells the pinger thread to shutdown the backend.
func tell_stop_backend(w *manager, d backend) {
	var proc = d.get_super_part()
	func() {
		proc.mutex.Lock()
		defer proc.mutex.Unlock()
		if proc.ch_quit_backend_send != nil {
			close(proc.ch_quit_backend_send)
			proc.ch_quit_backend_send = nil
		}
	}()
}

// PING_BACKEND performs heartbeating.  It will shutdown the backend,
// either when heartbeating fails or it is instructed to stop the
// backend.
func ping_backend(w *manager, d backend) {
	var proc = d.get_super_part()
	var duration = (time.Duration(w.Backend_awake_duration) * time.Second)
	var interval = (time.Duration(proc.Heartbeat_interval) * time.Second)
	var expiry = int64(3 * proc.Heartbeat_interval)
	//var ch_quit_backend = proc.ch_quit_backend

	set_backend_expiry(w.table, proc.Pool, expiry)

	proc.heartbeat_misses = 0
	for {
		var ok1 bool
		select {
		case _, ok1 = <-proc.ch_quit_backend:
			assert_fatal(!ok1)
			//fmt.Println("*** CH_QUIT_BACKEND CLOSED")
			break
		default:
		}
		time.Sleep(interval)

		// Do heatbeat.

		var status = d.heartbeat(w)
		if status == 200 {
			proc.heartbeat_misses = 0
		} else {
			proc.heartbeat_misses += 1
		}
		if proc.verbose {
			slogger.Debug(w.MuxEP+" Heartbeat", "pool", proc.Pool,
				"status", status, "misses", proc.heartbeat_misses)
		}
		if proc.heartbeat_misses > w.Heartbeat_miss_tolerance {
			slogger.Info(w.MuxEP+" Heartbeat failed",
				"pool", proc.Pool, "misses", proc.heartbeat_misses)
			break
		}

		// Check lifetime.

		var ts = get_access_timestamp(w.table, proc.Pool)
		var lifetime = time.Unix(ts, 0).Add(duration)
		if lifetime.Before(time.Now()) {
			slogger.Debug(w.MuxEP+" Awake time elapsed", "pool", proc.Pool)
			break
		}

		// Update a record expiration.

		var ok = set_backend_expiry(w.table, proc.Pool, expiry)
		if !ok {
			slogger.Warn(w.MuxEP+" Backend entry has gone",
				"pool", proc.Pool)
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
func stop_backend(w *manager, d backend) {
	var proc = d.get_super_part()
	slogger.Info(w.MuxEP+" Stop a backend", "pool", proc.Pool)

	delete_backend_exclusion(w.table, proc.Pool)
	delete_backend(w.table, proc.Pool)

	time.Sleep(time.Duration(w.backend_linger_ms) * time.Millisecond)

	var err1 = d.shutdown()
	if err1 != nil {
		slogger.Info(w.MuxEP+" Backend shutdown() failed",
			"pool", proc.Pool, "err", err1)
	}
	if err1 == nil {
		return
	}
	var err2 = proc.cmd.Cancel()
	if err2 != nil {
		slogger.Info(w.MuxEP+" Backend exec.Command.Cancel() failed",
			"pool", proc.Pool, "err", err2)
	}
}

// START_DISGORGING_STDIO spawns threads to emit backend stdout/stderr
// outputs to the "ch_stdio" channel.  It returns immediately.  It
// drains one line at a time.  It closes the channel when both are
// closed.
func start_disgorging_stdio(w *manager, d backend, ch_stdio chan<- stdio_message) {
	var proc = d.get_super_part()
	var cmd *exec.Cmd = proc.cmd

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
		tell_stop_backend(w, d)
	}()
}

// DISGORGE_STDIO_TO_LOG dumps stdout+stderr messages to a log.  It
// receives messages written by threads started in
// start_disgorging_stdio().
func disgorge_stdio_to_log(w *manager, proc *backend_delegate) {
	var pool = proc.Pool
	for {
		var x1, ok1 = <-proc.ch_stdio
		if !ok1 {
			break
		}
		// fmt.Println("LINE: ", x1.int, x1.string)
		//var m = strings.TrimSpace(x1.string)
		var m = x1.string
		if x1.stdio_stream == on_stdout {
			slogger.Info(w.MuxEP+" stdout message", "pool", pool, "msg", m)
		} else {
			slogger.Info(w.MuxEP+" stderr message", "pool", pool, "msg", m)
		}
	}
	if proc.verbose {
		slogger.Debug(w.MuxEP+" stdio dumper done", "pool", pool)
	}
}

// DRAIN_START_MESSAGES_TO_LOG outputs messages to a log, that are
// stored for checking a proper start of a backend.
func drain_start_messages_to_log(w *manager, pool string, stdouts []string, stderrs []string) {
	// fmt.Println("drain_start_messages_to_log()")
	var s string
	for _, s = range stdouts {
		slogger.Info(w.MuxEP+" stdout message", "pool", pool, "msg", s)
	}
	for _, s = range stderrs {
		slogger.Info(w.MuxEP+" stderr message", "pool", pool, "msg", s)
	}
}

// LIST_AVAILABLE_PORTS lists ports available.  It drops the ports
// used by backends running on this host locally.  It uses each
// integer skipping by use_n_ports.  It randomizes the order of the
// list.
func list_available_ports(w *manager, use_n_ports int) []int {
	assert_fatal(use_n_ports == 1 || use_n_ports == 2)

	var bes = list_backends_under_manager(w)
	var used []int
	for _, be := range bes {
		assert_fatal(be.Mux_ep == w.mux_ep)
		var _, ps, err1 = net.SplitHostPort(be.Backend_ep)
		if err1 != nil {
			slogger.Error(w.MuxEP+" Bad endpoint",
				"ep", be.Backend_ep, "err", err1)
			panic(nil)
		}
		var port, err2 = strconv.Atoi(ps)
		if err2 != nil {
			slogger.Error(w.MuxEP+" Bad endpoint",
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
	var allbes = list_backends(w.table, "*")
	var list []*backend_record
	for _, be := range allbes {
		if be.Mux_ep == w.mux_ep {
			list = append(list, be)
		}
	}
	return list
}

func wait4_child_process(w *manager, d backend) {
	var proc = d.get_super_part()
	var pid = proc.cmd.Process.Pid
	//var pid = proc.be.Backend_pid
	for {
		//var options int = unix.WNOHANG
		var options int = 0
		var wstatus unix.WaitStatus
		var rusage unix.Rusage
		var wpid, err1 = unix.Wait4(pid, &wstatus, options, &rusage)
		if err1 != nil {
			var err2, ok1 = err1.(unix.Errno)
			assert_fatal(ok1)
			if err2 == unix.ECHILD {
				time.Sleep(60 * time.Second)
			} else {
				slogger.Warn(w.MuxEP+"wait4() failed",
					"errno", unix.ErrnoName(err2))
			}
			continue
		}
		if wpid == 0 {
			slogger.Warn(w.MuxEP+" wait4() failed",
				"errno", unix.ErrnoName(unix.ECHILD))
			continue
		}
		if proc.verbose {
			slogger.Debug(w.MuxEP+" wait4() returns",
				"pid", wpid, "status", wstatus, "rusage", rusage)
		} else {
			slogger.Debug(w.MuxEP+" wait4() returns",
				"pid", wpid, "status", wstatus)
		}
		break
	}
}

// MAKE_ABSENT_BUCKETS_IN_BACKEND makes consistent about buckets with
// a record in Registrar.  Note that it runs during starting a
// backend.  Thus, it won't work to call get_backend(table,pool),
// because the record is not set in the keyval-db yet.
func make_absent_buckets_in_backend(w *manager, be *backend_record) {
	// var be = get_backend(w.table, pool)
	// if be == nil {
	// 	logger.errf(w.MuxEP + " Backend not running in setup: pool=(%s)",
	// 		pool)
	// 	return
	// }

	var pool = be.Pool
	var buckets_needed = gather_buckets(w.table, pool)

	var buckets_exsting, err = list_buckets_in_backend(w, be)
	if err != nil {
		slogger.Error(w.MuxEP+" Backend access failed",
			"pool", be.Pool, "err", err)
		command_to_stop_backend(w, pool)
	}

	slogger.Debug(w.MuxEP+" Check existing buckets in backend",
		"pool", be.Pool, "buckets", buckets_exsting)

	var now int64 = time.Now().Unix()
	for _, b := range buckets_needed {
		if slices.Contains(buckets_exsting, b.Bucket) {
			continue
		}
		if b.Expiration_time < now {
			continue
		}

		slogger.Debug(w.MuxEP+" Make a bucket in backend",
			"pool", b.Pool, "bucket", b.Bucket)

		make_bucket_in_backend(w, be, b)
	}
}
