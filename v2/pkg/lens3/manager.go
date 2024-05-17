/* A sentinel for an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A manager watches the backend server state and records its outputs
// in logs.  The first few lines from a backend is used to check its
// start.  A backend usually does not output anything later except on
// errors.

// MEMO: A manager tries to kill a server by sudo's signal forwarding,
// when a shutdown fails.  Signal forwarding works because sudo runs
// with the same RUID.  It uses SIGTERM for using signal forwarding.
// A cancel function is replaced by one with SIGTERM.  The default in
// exec/Command.Cancel kills with SIGKILL, and does not work with
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
	"os"
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

type manager struct {
	table *keyval_table

	// MUX_EP and MUX_PID are about a process that a multiplexer and a
	// manager run in.
	mux_ep  string
	mux_pid int

	// BE factory is to make a backend.
	factory backend_factory

	// PROCESSES maps an os.Pid (int) to a backend record.
	process map[int]backend
	// MUTEX protects the processes map.
	mutex sync.Mutex

	// CH_SIG is a channel to receive SIGCHLD.
	ch_sig chan os.Signal

	// ENVIRON holds a copy of the minimal list of environs.
	environ []string

	//backend_conf
	manager_conf
}

// BACKEND_FACTORY is to make a backend instance.
type backend_factory interface {
	configure(conf *mux_conf)
	clean_at_exit()
	make_backend(string) backend
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
	// stderr by values on_out and on_err.  The passed strings are
	// accumulated ones all from the start.
	check_startup(int, []string) start_result

	// ESTABLISH does a server specific initialization at its start.
	establish()

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
	backend_record

	verbose bool

	// ENVIRON is the shared one in the_manager.
	environ *[]string

	// CH_QUIT is to inform stopping the server by closing.  Every
	// thread for this server shall quit.
	ch_quit chan vacuous

	cmd      *exec.Cmd
	ch_stdio chan stdio_message

	heartbeat_misses int

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

//var the_manager_conf = &the_manager.manager_conf

const (
	on_out int = iota + 1
	on_err
)

// STDIO_MESSAGE is a message passed through a channel.  Each is one
// line of a message.  ON_OUT or ON_ERR indicates a message is from
// stdout or stderr.
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

func configure_manager(w *manager, t *keyval_table, m *multiplexer, conf *mux_conf) {
	w.table = t
	w.manager_conf = conf.Manager

	w.watch_gap_minimal = 10
	w.stabilize_wait_ms = 1000
	w.manager_expiration = 1000

	w.ch_sig = set_signal_handling()
	w.environ = minimal_environ()

	w.mux_ep = m.mux_ep
	w.mux_pid = m.mux_pid

	w.factory = the_backend_minio_factory
	w.factory.configure(conf)
}

func manager_main() {
	defer the_manager.factory.clean_at_exit()
}

func start_manager(w *manager) {
	fmt.Println("start_manager() w=", w)

	//w.table = t
	//w.manager_conf = *conf

	//w.Sudo = "/usr/bin/sudo"
	//w.Heartbeat_miss_tolerance = 3
	//w.Heartbeat_interval = 60

	reap_child_process(w)
}

func start_backend_for_test(w *manager) backend {
	fmt.Println("start_backend_for_test()")
	//var pool = generate_pool_name()
	/*
		var g = w.factory.make_backend("d4f0c4645fce5734")
		var proc = g.get_super_part()

		var u, err4 = user.Current()
		assert_fatal(err4 == nil)
		proc.Owner_uid = "#" + u.Uid
		proc.Owner_gid = "#" + u.Gid
		proc.Buckets_directory = u.HomeDir + "/pool-x"
		proc.Probe_key = generate_access_key()
		proc.Online_status = true
		proc.Expiration_time = 0

		proc.Backend_ep = ""
		proc.Backend_pid = 0
		proc.Root_access = generate_access_key()
		proc.Root_secret = generate_secret_key()
		proc.Mux_ep = w.mux_ep
		proc.Mux_pid = w.mux_pid

		proc.verbose = true
		proc.environ = &w.environ
	*/

	var g = start_backend(w, "d4f0c4645fce5734")
	if g == nil {
		fmt.Println("START_BACKEND() FAILED")
		os.Exit(1)
	}
	var proc = g.get_super_part()
	proc.verbose = true

	go func() {

		if false {
			cancel_process_for_test(w, g)
			fmt.Println("MORE 5 SEC")
			time.Sleep(5 * time.Second)
		} else if false {
			shutdown_process_for_test(w, g)
			fmt.Println("MORE 5 SEC")
			time.Sleep(5 * time.Second)
		} else if true {
			fmt.Println("RUN MANAGER 15 MINUTES")
			time.Sleep(15 * 60 * time.Second)
			shutdown_process_for_test(w, g)
		}
	}()

	return g
}

func ping_server(w *manager, g backend) {
	var proc = g.get_super_part()
	proc.heartbeat_misses = 0
	for {
		time.Sleep(time.Duration(proc.Heartbeat_interval) * time.Second)
		var status = g.heartbeat()
		if status == 200 {
			proc.heartbeat_misses = 0
		} else {
			proc.heartbeat_misses += 1
		}
		if proc.heartbeat_misses > w.Heartbeat_miss_tolerance {
			logger.infof(("Mux(pool=%s)" +
				" Heartbeating server failed:" +
				" misses=%v"),
				proc.Pool, proc.heartbeat_misses)
			raise(termination("backend heartbeat failure"))
		}
	}
}

func stop_backend(w *manager, g backend) {
	fmt.Println("stop_backend()")
	var proc = g.get_super_part()

	var _ = g.shutdown()

	if proc.ch_quit != nil {
		close(proc.ch_quit)
		proc.ch_quit = nil
	}
}

// START_BACKEND_MUTEXED mutexes among all threads in all distributed
// processes of multiplexers, choosing one who takes the control of
// starting a backend.
func start_backend_mutexed(w *manager, pool string) backend {
	var now int64 = time.Now().Unix()
	var ep = &manager_mutex_record{
		Mux_ep:     w.mux_ep,
		Start_time: now,
	}
	var ok, _ = set_ex_manager(w.table, pool, ep)
	if !ok {
		var be1 = wait_for_backend_by_race(w, pool)
		if be1 == nil {
			logger.debugf("start_backend(pool=%s) waits by race", pool)
		}
		return nil
	} else {
		var be2 = start_backend(w, pool)
		return be2
	}
}

func start_backend(w *manager, pool string) backend {
	fmt.Println("start_backend()")
	delete_backend_process(w.table, pool)

	var desc = get_pool(w.table, pool)
	if desc == nil {
		logger.warnf("start_backend() pool is missing: pool=%s", pool)
		return nil
	}

	var g = w.factory.make_backend(pool)
	var proc *backend_process = g.get_super_part()
	// Set proc.pool_record part.
	proc.pool_record = *desc
	// Set proc.backend_record part.
	proc.Backend_ep = ""
	proc.Backend_pid = 0
	proc.Root_access = generate_access_key()
	proc.Root_secret = generate_secret_key()
	proc.Mux_ep = w.mux_ep
	proc.Mux_pid = w.mux_pid

	proc.verbose = true
	proc.environ = &w.environ

	var available_ports = list_ports_available(w)

	fmt.Printf("start_backend() proc=%v ports=%v\n", proc, available_ports)

	for _, port := range available_ports {
		var r1 = try_start_backend(w, g, port)
		switch r1.start_state {
		case start_ongoing:
			panic("internal")
		case start_started:
			// OK.
		case start_to_retry:
			continue
		case start_failed:
			logger.errorf("Mux(pool=%s) Starting a backend failed: %s",
				pool, r1.message)
			return nil
		}

		assert_fatal(proc.cmd.Process != nil)
		var pid = proc.cmd.Process.Pid
		func() {
			w.mutex.Lock()
			defer w.mutex.Unlock()
			w.process[pid] = g
		}()

		go barf_stdio_to_log(proc)

		// Sleep for a while for a server to be stable.
		time.Sleep(time.Duration(proc.stabilize_wait_ms) * time.Millisecond)

		g.establish()
		go ping_server(w, g)

		var desc = &proc.backend_record
		fmt.Println("set_backend_process(1) ep=", proc.Backend_ep)
		fmt.Println("proc.backend_record=")
		print_in_json(desc)
		set_backend_process(w.table, proc.Pool, desc)
		return g
	}

	// All ports are tried and failed.

	logger.warnf("Mux(pool=%s) Starting a backend SUSPENDED: %s",
		pool, " (all ports used)")
	var state = pool_state_SUSPENDED
	var reason = pool_reason_BACKEND_BUSY
	set_pool_state(w.table, pool, state, reason)
	return nil
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
		var be1 = get_backend_process(w.table, pool)
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

// LIST_PORTS_AVAILABLE lists ports available.  It drops the ports
// used by backends running on this same host locally.
func list_ports_available(w *manager) []int {
	var bes = list_backend_processes(w.table, "*")
	var used []int
	for _, be := range bes {
		if be.Mux_ep == w.mux_ep {
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

// TRY_START_BACKEND starts a process and waits for a message or a
// timeout.  A message from the server is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_backend(w *manager, g backend, port int) start_result {
	var proc = g.get_super_part()
	var thishost, _, err1 = net.SplitHostPort(w.mux_ep)
	if err1 != nil {
		panic(err1)
	}
	proc.Backend_ep = net.JoinHostPort(thishost, strconv.Itoa(port))
	fmt.Printf("try_start_backend(ep=%s)\n", proc.Backend_ep)

	var user = proc.Owner_uid
	var group = proc.Owner_gid
	var address = proc.Backend_ep
	var directory = proc.Buckets_directory
	var command = g.make_command_line(address, directory)
	var sudo_argv = []string{
		w.Sudo,
		"-n",
		"-u", user,
		"-g", group}
	var argv = append(sudo_argv, command.argv...)
	var envs = append(w.environ, command.envs...)

	logger.debugf("Mux(pool=%s) Run a server: argv=%v.", proc.Pool, argv)
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
	drain_stdio(proc)

	var err3 = cmd.Start()
	if err3 != nil {
		logger.errorf("cmd.Start() err=%v", err3)
		return start_result{
			start_state: start_failed,
			message:     err3.Error(),
		}
	}

	proc.Backend_pid = cmd.Process.Pid
	var r1 = wait_for_backend_come_up(g)
	fmt.Println("DONE state=", r1.start_state, r1.message)

	assert_fatal(r1.start_state != start_ongoing)

	return r1
}

// DRAIN_STDIO spawns threads for draining stdout+stderr to a channel
// until closed.  It returns immediately.  It drains one line at a
// time.  It closes the channel when both are closed.
func drain_stdio(proc *backend_process) {
	var cmd *exec.Cmd = proc.cmd
	var ch1 chan stdio_message = proc.ch_stdio
	// var o1, e1 io.ReadCloser

	var o1, err1 = cmd.StdoutPipe()
	if err1 != nil {
		log.Fatal(err1)
	}
	var e1, err2 = cmd.StderrPipe()
	if err2 != nil {
		log.Fatal(err2)
	}

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		var sc1 = bufio.NewScanner(o1)
		for sc1.Scan() {
			var s1 = sc1.Text()
			ch1 <- stdio_message{on_out, s1}
		}
		fmt.Println("close(out)")
	}()

	go func() {
		defer wg.Done()
		var sc2 = bufio.NewScanner(e1)
		for sc2.Scan() {
			var s2 = sc2.Text()
			ch1 <- stdio_message{on_err, s2}
		}
		fmt.Println("close(err)")
	}()

	go func() {
		wg.Wait()
		close(ch1)
	}()
}

func kill_server__(pid int) {
	var err1 = unix.Kill(pid, unix.SIGTERM)
	fmt.Println("unix.Kill()", err1)
}

// WAIT_FOR_BACKEND_COME_UP waits until either a server (1) outputs an
// expected message, (2) outputs an error message, (3) outputs too
// many messages, (4) reaches a timeout, (5) closes both
// stdout+stderr.  It returns STARTED/TO_RETRY/FAILED.  It reads the
// stdio channel as much as available.
func wait_for_backend_come_up(g backend) start_result {
	var proc *backend_process = g.get_super_part()
	// fmt.Printf("WAIT_FOR_BACKEND_COME_UP() svr=%T proc=%T\n", svr, proc)

	var msg_out []string
	var msg_err []string

	defer func() {
		// It defers calling a closure to refer to finally collected
		// msg_out and msg_err.
		drain_start_messages_to_log(proc.Pool, msg_out, msg_err)
	}()

	var timeout = time.After(60 * time.Second)
	for {
		select {
		case msg1, ok1 := <-proc.ch_stdio:
			if !ok1 {
				return start_result{
					start_state: start_failed,
					message:     "pipe closed",
				}
			}
			var messages_on_stdout bool = false
			switch msg1.int {
			case on_out:
				msg_out = append(msg_out, msg1.string)
				messages_on_stdout = true
			case on_err:
				msg_err = append(msg_err, msg1.string)
			}
			// Sleep for a short time for stdio messages.
			// (* time.Sleep(10 * time.Millisecond) *)
			for len(msg_out) < 500 && len(msg_err) < 500 {
				select {
				case msg2, ok2 := <-proc.ch_stdio:
					if !ok2 {
						break
					}
					switch msg2.int {
					case on_out:
						msg_out = append(msg_out, msg2.string)
						messages_on_stdout = true
					case on_err:
						msg_err = append(msg_err, msg2.string)
					}
					continue
				default:
					break
				}
				break
			}
			if messages_on_stdout {
				var st1 = g.check_startup(on_out, msg_out)
				switch st1.start_state {
				case start_ongoing:
					// Skip.
				case start_started:
					fmt.Println("*SERVER COME UP*")
					return st1
				case start_to_retry:
					return st1
				case start_failed:
					return st1
				}
			}
			if !(len(msg_out) < 500 && len(msg_err) < 500) {
				return start_result{
					start_state: start_failed,
					message:     "stdout/stderr flooding",
				}
			}
			continue
		case <-timeout:
			return start_result{
				start_state: start_failed,
				message:     "timeout",
			}
		}
	}
}

func drain_start_messages_to_log(pool string, outs []string, errs []string) {
	// fmt.Println("drain_start_messages_to_log()")
	var s string
	for _, s = range outs {
		logger.debugf("Mux(pool=%s): %s", pool, s)
	}
	for _, s = range errs {
		logger.debugf("Mux(pool=%s): %s", pool, s)
	}
}

func set_signal_handling() chan os.Signal {
	fmt.Println("set_signal_handling()")
	var ch = make(chan os.Signal, 1)
	//signal.Notify(ch, unix.SIGCHLD, unix.SIGHUP)
	return ch
}

func reap_child_process(w *manager) {
	for {
		//var options int = unix.WNOHANG
		var options int = 0
		var wstatus unix.WaitStatus
		var rusage unix.Rusage
		var wpid, err1 = unix.Wait4(-1, &wstatus, options, &rusage)
		if err1 != nil {
			var err, ok1 = err1.(unix.Errno)
			assert_fatal(ok1)
			if err == unix.ECHILD {
				time.Sleep(60 * time.Second)
			} else {
				logger.warnf("wait4 failed=%s", unix.ErrnoName(err))
			}
			continue
		}
		if wpid == 0 {
			logger.warn(fmt.Sprintf("wait4 failed=%s", unix.ErrnoName(unix.ECHILD)))
			continue
		}
		assert_fatal(wpid != -1)
		fmt.Println("wait pid=", wpid, "status=", wstatus,
			"rusage=", rusage)
	}
}

func reap_child_process_by_sigchld__(w *manager) {
	fmt.Println("reap_child_process() start")
	//proc map[int]backend_process
	//ch_sig chan sycall.Signal
	for sig := range w.ch_sig {
		switch sig {
		case unix.SIGCHLD:
			fmt.Println("Got SIGCHLD")
			var options int = unix.WNOHANG
			var wstatus unix.WaitStatus
			var rusage unix.Rusage
			var wpid, err1 = unix.Wait4(-1, &wstatus, options, &rusage)
			if err1 != nil {
				var err, ok1 = err1.(unix.Errno)
				assert_fatal(ok1)
				logger.warn(fmt.Sprintf("wait4 failed=%s", unix.ErrnoName(err)))
				continue
			}
			if wpid == 0 {
				logger.warn(fmt.Sprintf("wait4 failed=%s", unix.ErrnoName(unix.ECHILD)))
				continue
			}
			assert_fatal(wpid != -1)
			fmt.Println("wait pid=", wpid, "status=", wstatus,
				"rusage=", rusage)
		case unix.SIGHUP:
			fmt.Println("SIGHUP")
		default:
			var usig, ok2 = sig.(unix.Signal)
			assert_fatal(ok2)
			logger.warn(fmt.Sprintf("unhandled signal=%s", unix.SignalName(usig)))
		}
	}
	fmt.Println("reap_child_process() channel closed")
}

func barf_stdio_to_log(proc *backend_process) {
	var ch1 = proc.ch_stdio
	for {
		var x1, ok1 = <-ch1
		if !ok1 {
			fmt.Println("CLOSED")
			break
		}
		fmt.Println("LINE: ", x1.int, x1.string)
	}
}

// *** TEST CODE ***

func cancel_process_for_test(w *manager, g backend) {
	fmt.Println("CANCEL IN 10 SEC")
	time.Sleep(10 * time.Second)
	var proc = g.get_super_part()
	fmt.Println("cmd.Cancel()")
	var err5 = proc.cmd.Cancel()
	if err5 != nil {
		fmt.Println("cmd.Cancel()=", err5)
	}
}

func shutdown_process_for_test(w *manager, g backend) {
	fmt.Println("SHUTDOWN IN 10 SEC")
	time.Sleep(10 * time.Second)
	var proc = g.get_super_part()
	stop_backend(w, g)
	var err5 = proc.cmd.Cancel()
	if err5 != nil {
		fmt.Println("cmd.Cancel()=", err5)
	}
}
