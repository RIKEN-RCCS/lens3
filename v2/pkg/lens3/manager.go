/* A sentinel for an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A manager watches the backend server state and records its outputs
// in logs.  The first few lines from a backend is used to check its
// start.  A backend usually does not output anything later except on
// errors.

// MEMO: A manager tries to kill a server by sudo's signal relaying,
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
	// Golang prefers "x/sys/unix" over "syscall".  "SysProcAttr" are
	// the same in "x/sys/unix" and "syscall".

	// "log/slog" is in Go1.21.

	"bufio"
	"context"
	//"encoding/json"
	"fmt"
	"log"
	//"log/slog"
	"time"
	//"reflect"
	//"io"
	//"os"
	"os/exec"
	//"os/signal"
	"math/rand/v2"
	"net"
	//"os/user"
	"sync"
	//"bytes"
	//"syscall"
	"golang.org/x/sys/unix"
	//"runtime"
	//"reflect"
	"slices"
	"strconv"
	//"time"
	//"testing"
)

// MANAGER keeps track of backend processes.  Manager is a single
// object, "the_manager".  It is with threads to wait for child
// processes.
type manager struct {
	table *keyval_table

	multiplexer *multiplexer

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
	clean_at_exit()
	make_delegate(string) backend
}

// BACKEND is a backend specific part.  A backend shall not start its
// long-running threads.  Or, it lets them enter a wait-group.
type backend interface {
	// GET_SUPER_PART returns a generic part or a superclass.
	get_super_part() *backend_process

	// MAKE_COMMAND_LINE returns a command and environment of a
	// backend instance.
	make_command_line(string, string) backend_command

	// CHECK_STARTUP checks a start of a server.  It is called each
	// time a server outputs a line of a message.  It looks for a
	// specific message.  The first argument indicates stdout or
	// stderr by values on_stdout and on_stderr.  The passed strings
	// are accumulated ones all from the start.
	check_startup(int, []string) start_result

	// ESTABLISH does a server specific initialization at its start.
	establish() error

	// SHUTDOWN stops a server in its specific way.
	shutdown() error

	// HEARTBEAT pings a server and returns an http status.  It is an
	// error but status=200.
	heartbeat() int
}

// BACKEND_PROCESS is a generic part of a backend.  It is embedded in
// a backend instance and returned by get_super_part().  A
// configuration "manager_conf" is shared with the manager".
type backend_process struct {
	pool_record
	be *backend_record

	verbose bool

	// ENVIRON is the shared one in the_manager.
	environ *[]string

	// The following fields {cmd,ch_stdio,ch_quit_backend} are set
	// when starting a backend.
	cmd             *exec.Cmd
	ch_stdio        chan stdio_message
	ch_quit_backend chan vacuous

	heartbeat_misses int

	// MUTEX protects accesses to the ch_quit_backend.
	mutex sync.Mutex

	//*backend_conf
	*manager_conf
}

type backend_command struct {
	argv []string
	envs []string
}

// THE_MANAGER is the single multiplexer instance.
var the_manager = manager{
	//processes: make(map[int]backend),
}

// ON_STDOUT and ON_STDERR are indicators of stdout or stderr stored
// in a stdio_message.
const (
	on_stdout int = iota + 1
	on_stderr
)

// STDIO_MESSAGE is a message passed through a "ch_stdio" channel.
// Each is one line of a message.  The first field ON_STDOUT or
// ON_STDERR indicates a message is from stdout or stderr.
type stdio_message struct {
	int
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

	w.backend_stabilize_ms = 10
	w.backend_linger_ms = 10

	w.watch_gap_minimal = 10
	w.manager_expiration = 1000

	//w.ch_sig = set_signal_handling()
	w.environ = minimal_environ()

	w.mux_ep = m.mux_ep

	switch c.Multiplexer.Backend {
	case "minio":
		w.factory = the_backend_minio_factory
	case "rclone":
		w.factory = the_backend_rclone_factory
	default:
		logger.errf("Mux() Configuration error, unknown backend (%s)",
			c.Multiplexer.Backend)
		log.Panic("")
	}

	w.factory.configure(c)
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
			logger.debugf("start_backend(pool=%s) waits by race", pool)
		}
		return nil
	} else {
		var expiry int64 = int64(3 * w.Backend_start_timeout)
		var ok2 = set_backend_exclusion_expiry(w.table, pool, expiry)
		if !ok2 {
			// Ignore an error.
			logger.errf("Mux() Bad call set_backend_exclusion_expiry()")
		}
		var be2 = start_backend_in_mutexed(w, pool)
		return be2
	}
}

// START_BACKEND_IN_MUTEXED starts a backend, trying available ports.
func start_backend_in_mutexed(w *manager, pool string) backend {
	//fmt.Println("start_backend()")
	//delete_backend(w.table, pool)
	defer delete_backend_exclusion(w.table, pool)

	var pooldata = get_pool(w.table, pool)
	if pooldata == nil {
		logger.warnf("Mux() start_backend() pool is missing: pool=%s", pool)
		return nil
	}

	var d = w.factory.make_delegate(pool)

	// Initialize the super-part.

	var proc *backend_process = d.get_super_part()
	proc.pool_record = *pooldata
	proc.be = &backend_record{
		Pool:        pool,
		Backend_ep:  "",
		Backend_pid: 0,
		Root_access: generate_access_key(),
		Root_secret: generate_secret_key(),
		Mux_ep:      w.multiplexer.mux_ep,
		Mux_pid:     w.multiplexer.mux_pid,
		Timestamp:   0,
	}
	proc.verbose = true
	proc.environ = &w.environ
	proc.manager_conf = &w.manager_conf

	// The following fields are set in starting a backend.

	// proc.cmd
	// proc.ch_stdio
	// proc.ch_quit_backend

	var available_ports = list_available_ports(w)

	if proc.verbose {
		fmt.Printf("start_backend() ports=%v\n", available_ports)
	}

	for _, port := range available_ports {
		var r1 = try_start_backend(w, d, port)
		switch r1.start_state {
		case start_ongoing:
			panic("internal")
		case start_started:
			// OK.
		case start_to_retry:
			continue
		case start_failed:
			logger.errf("Mux(pool=%s) Starting a backend failed: %s",
				pool, r1.message)
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
			logger.warnf("Mux(pool=%s) Starting a backend failed: %s",
				pool, "manager is in shutdown")
			tell_stop_backend(w, d)
			return nil
		}

		go disgorge_stdio_to_log(proc)

		// Sleep for a while for a server to be stable.

		time.Sleep(time.Duration(w.backend_stabilize_ms) * time.Millisecond)

		d.establish()
		go ping_backend(w, d)

		var now int64 = time.Now().Unix()
		proc.be.Timestamp = now
		set_backend(w.table, proc.Pool, proc.be)
		return d
	}

	// All ports are tried and failed.

	logger.warnf("Mux() Starting a backend SUSPENDED (no ports): pool=(%s)",
		pool)
	var state = pool_state_SUSPENDED
	var reason = pool_reason_BACKEND_BUSY
	set_pool_state(w.table, pool, state, reason)
	return nil
}

// TRY_START_BACKEND starts a process and waits for a message or a
// timeout.  A message from the server is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_backend(w *manager, d backend, port int) start_result {
	var proc = d.get_super_part()
	var thishost, _, err1 = net.SplitHostPort(w.mux_ep)
	if err1 != nil {
		panic(err1)
	}
	proc.be.Backend_ep = net.JoinHostPort(thishost, strconv.Itoa(port))
	if proc.verbose {
		fmt.Printf("try_start_backend(ep=%s)\n", proc.be.Backend_ep)
	}

	var user = proc.Owner_uid
	var group = proc.Owner_gid
	var address = proc.be.Backend_ep
	var directory = proc.Buckets_directory
	var command = d.make_command_line(address, directory)
	var sudo_argv = []string{
		w.Sudo,
		"-n",
		"-u", user,
		"-g", group}
	var argv = append(sudo_argv, command.argv...)
	var envs = append(w.environ, command.envs...)

	logger.debugf("Mux(pool=%s) Run a backend: argv=%v", proc.Pool, argv)
	// logger.debugf("Mux(pool=%s) Run a server: argv=%v; envs=%v.",
	// proc.pool, argv, envs)

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	if cmd == nil {
		panic("cmd=nil")
	}
	assert_fatal(cmd.SysProcAttr == nil)

	cmd.Env = envs
	cmd.SysProcAttr = &unix.SysProcAttr{
		// Note (?) it fails with: Noctty=true
		Setsid:     true,
		Setctty:    false,
		Noctty:     false,
		Foreground: false,
	}
	cmd.Cancel = func() error {
		return cmd.Process.Signal(unix.SIGTERM)
	}
	cmd.Stdin = nil

	proc.cmd = cmd
	proc.ch_stdio = make(chan stdio_message)
	proc.ch_quit_backend = make(chan vacuous)

	start_disgorging_stdio(proc)

	var err3 = cmd.Start()
	if err3 != nil {
		logger.errf("cmd.Start() err=%v", err3)
		return start_result{
			start_state: start_failed,
			message:     err3.Error(),
		}
	}

	proc.be.Backend_pid = cmd.Process.Pid
	var r1 = wait_for_backend_come_up(d)

	fmt.Println("*** DONE state=", r1.start_state, r1.message)

	assert_fatal(r1.start_state != start_ongoing)

	return r1
}

// WAIT_FOR_BACKEND_COME_UP waits until either a server (1) outputs an
// expected message, (2) outputs an error message, (3) outputs too
// many messages, (4) reaches a timeout, (5) closes both
// stdout+stderr.  It returns STARTED/TO_RETRY/FAILED.  It reads the
// stdio channel as much as available.
func wait_for_backend_come_up(d backend) start_result {
	var proc *backend_process = d.get_super_part()
	// fmt.Printf("WAIT_FOR_BACKEND_COME_UP() svr=%T proc=%T\n", svr, proc)

	var msg_stdout []string
	var msg_stderr []string

	// It makes a closure in stead of directly defering a call, so
	// that to refer to finally collected msg_stdout and msg_stderr.

	defer func() {
		drain_start_messages_to_log(proc.Pool, msg_stdout, msg_stderr)
	}()

	var timeout = time.Duration(proc.Backend_start_timeout) * time.Second
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
			switch msg1.int {
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
					switch msg2.int {
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

// It sleeps in 1ms, 10ms, 100ms, and 1s, and keeps sleeping in 1s
// until a timeout.
func wait_for_backend_by_race(w *manager, pool string) *backend_record {
	logger.debugf("Mux(%s) Waiting for a backend by race.", w.mux_ep)
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
			sleep = sleep * 10
		}
	}
	logger.debugf("Mux(%s) Waiting for a backend by race failed.", w.mux_ep)
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
		if proc.ch_quit_backend != nil {
			close(proc.ch_quit_backend)
			proc.ch_quit_backend = nil
		}
	}()
}

// PING_BACKEND performs heartbeating.  It will shutdown the backend,
// either when heartbeating fails or it is instructed to stop the
// backend.  Note that it uses a copy of proc.ch_quit_backend
// here, because the field will be set null after closing.
func ping_backend(w *manager, d backend) {
	var proc = d.get_super_part()
	var duration = (time.Duration(w.Backend_awake_duration) * time.Second)
	var interval = (time.Duration(proc.Heartbeat_interval) * time.Second)
	var expiry = int64(3 * proc.Heartbeat_interval)
	var ch_quit_backend = proc.ch_quit_backend

	set_backend_expiry(w.table, proc.Pool, expiry)

	proc.heartbeat_misses = 0
	for {
		var ok1 bool
		select {
		case _, ok1 = <-ch_quit_backend:
			assert_fatal(!ok1)
			fmt.Println("*** CH_QUIT_BACKEND CLOSED")
			break
		default:
		}
		time.Sleep(interval)

		// Do heatbeat.

		var status = d.heartbeat()
		if status == 200 {
			proc.heartbeat_misses = 0
		} else {
			proc.heartbeat_misses += 1
		}
		if proc.verbose {
			logger.debugf("Mux() Heartbeat: pool=(%s) status=%d misses=%d",
				proc.Pool, status, proc.heartbeat_misses)
		}
		if proc.heartbeat_misses > w.Heartbeat_miss_tolerance {
			logger.infof("Mux() Heartbeat failed: pool=(%s) misses=%d",
				proc.Pool, proc.heartbeat_misses)
			break
		}

		// Check lifetime.

		var ts = get_access_timestamp(w.table, proc.Pool)
		var lifetime = time.Unix(ts, 0).Add(duration)
		if lifetime.Before(time.Now()) {
			logger.debugf("Mux() Awake time elapsed: pool=(%s)", proc.Pool)
			break
		}

		// Update a record expiration.

		var ok = set_backend_expiry(w.table, proc.Pool, expiry)
		if !ok {
			logger.warnf("Mux() Backend keyval-db entry gone: pool=(%s)",
				proc.Pool)
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
	fmt.Println("stop_backend()")
	var proc = d.get_super_part()

	delete_backend_exclusion(w.table, proc.Pool)
	delete_backend(w.table, proc.Pool)

	time.Sleep(time.Duration(w.backend_linger_ms) * time.Millisecond)

	var err1 = d.shutdown()
	if err1 != nil {
		logger.infof(("Mux() Backend shutdown() failed: pool=(%s) err=(%v)"),
			proc.Pool, err1)
	}
	if err1 == nil {
		return
	}
	var err2 = proc.cmd.Cancel()
	if err2 != nil {
		logger.infof(("Mux() Backend cmd.Cancel() failed: pool=(%s) err=(%v)"),
			proc.Pool, err2)
	}
}

// START_DISGORGING_STDIO spawns threads to emit backend output to the
// "ch_stdio" channel.  It returns immediately.  It drains one line at
// a time.  It closes the channel when both are closed.
func start_disgorging_stdio(proc *backend_process) {
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
			proc.ch_stdio <- stdio_message{on_stdout, s1}
		}
	}()

	go func() {
		defer wg.Done()
		var c2 = bufio.NewScanner(stderr1)
		for c2.Scan() {
			var s2 = c2.Text()
			proc.ch_stdio <- stdio_message{on_stderr, s2}
		}
	}()

	go func() {
		wg.Wait()
		close(proc.ch_stdio)
	}()
}

// DISGORGE_STDIO_TO_LOG outputs stdout+stderr messages to a log.  It
// receives messages written by threads started in
// start_disgorging_stdio().
func disgorge_stdio_to_log(proc *backend_process) {
	var pool = proc.Pool
	for {
		var x1, ok1 = <-proc.ch_stdio
		if !ok1 {
			fmt.Println("CLOSED")
			break
		}
		// fmt.Println("LINE: ", x1.int, x1.string)
		if x1.int == on_stdout {
			logger.infof("Mux(pool=%s) stdout: %s", pool, x1.string)
		} else {
			logger.infof("Mux(pool=%s) stderr: %s", pool, x1.string)
		}
	}
}

// DRAIN_START_MESSAGES_TO_LOG outputs messages to a log, that are
// stored for checking a proper start of a backend.
func drain_start_messages_to_log(pool string, outs []string, errs []string) {
	// fmt.Println("drain_start_messages_to_log()")
	var s string
	for _, s = range outs {
		logger.infof("Mux(pool=%s) stdout: %s", pool, s)
	}
	for _, s = range errs {
		logger.infof("Mux(pool=%s) stderr: %s", pool, s)
	}
}

// LIST_AVAILABLE_PORTS lists ports available.  It drops the ports
// used by backends running on this host locally.  It randomizes the
// order of the entries.
func list_available_ports(w *manager) []int {
	var bes = list_backends_under_manager(w)
	var used []int
	for _, be := range bes {
		assert_fatal(be.Mux_ep == w.mux_ep)
		var _, ps, err1 = net.SplitHostPort(be.Backend_ep)
		if err1 != nil {
			panic(err1)
		}
		var port, err2 = strconv.Atoi(ps)
		if err2 != nil {
			panic(err2)
		}
		used = append(used, port)
	}
	var ports []int
	for i := w.Port_min; i <= w.Port_max+1; i++ {
		if slices.Index(used, i) == -1 {
			ports = append(ports, i)
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
				logger.warnf("wait4() failed: errno=%s",
					unix.ErrnoName(err2))
			}
			continue
		}
		if wpid == 0 {
			logger.warnf("Mux() wait4() failed: errno=%s",
				unix.ErrnoName(unix.ECHILD))
			continue
		}
		logger.debugf("Mux() wait4() returns pid=%d status=%d rusage=(%#v)",
			wpid, wstatus, rusage)
		break
	}
}
