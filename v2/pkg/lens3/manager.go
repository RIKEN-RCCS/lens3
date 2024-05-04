/* A sentinel for an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// A manager watches the backend server state and records its outputs
// in logs.  The first few lines from a server is used to check its
// start.  A server usually does not output anything later except on
// errors.
//
// MEMO: A manager tries to kill a server by sudo's signal forwarding,
// when a shutdown fails.  Signal forwarding works because sudo runs
// with the same RUID.  PDEATHSIG in exec/Command nor
// prctl(PR_SET_PDEATHSIG) does not work because of sudo.  The default
// in exec/Command.Cancel kills with SIGKILL, and it does not work
// with sudo.  See "src/os/exec/exec.go".  A cancel function is
// replaced by one with SIGTERM, (though it won't be used).

// os.Signal is an interface, unix.Signal, syscall.Signal are
// identical and concrete.

package lens3

// Golang prefers "x/sys/unix" over "syscall".  "SysProcAttr" are the
// same in "x/sys/unix" and "syscall".

// "log/slog" is in Go1.21.

import (
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
	"os/user"
	"sync"
	//"bytes"
	//"syscall"
	"golang.org/x/sys/unix"
	//"runtime"
	//"reflect"
	//"strconv"
	//"time"
	//"testing"
)

type vacuous_ = struct{}

// BACKEND_MANAGER is a single object with threads of a child process
// reaper.
type backend_manager struct {

	// BE is a source to make a backend.
	be backend_factory

	// PROC maps a PID to a process record.  PID is int in "os".
	proc map[int]backend

	// CH_SIG is a channel to receive SIGCHLD.
	ch_sig chan os.Signal

	environ []string

	// -- ctl_param map[string]any

	bin_sudo string

	server_setup_at_start        bool
	server_awake_duration        int
	heartbeat_interval           int
	heartbeat_tolerance          int
	heartbeat_timeout            int
	server_start_timeout         int
	server_setup_timeout         int
	server_stop_timeout          int
	server_setup_control_timeout int
	watch_gap_minimal            int
	manager_expiry               int
}

// BACKEND_FACTORY is to make a backend instance.
type backend_factory interface {
	configure()
	make_backend(string, string) backend
}

// BACKEND is a backend server with a server specific part.  A backend
// shall not start its long-running threads.  Or, it lets them enter a
// wait-group.
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

	// SETUP does a server specific initialization at its start.
	setup()

	// SHUTDOWN stops a server in its specific way.
	shutdown() error

	// HEARTBEAT pings a server and returns an http status.  It is an
	// error but status=200.
	heartbeat() int
}

// BACKEND_PROCESS is a generic part of a server.  It is embedded in a
// backend.
type backend_process struct {
	pool string

	port int
	ep   string

	owner_uid, owner_gid string
	directory            string

	// ROOT_USER and ROOT_PASSWORD are credential for accessing a server.
	root_user, root_password string

	verbose bool

	// environ is the same one in the_manager.
	environ []string

	// CH_QUIT is to inform stopping the server by closing.  Every
	// thread for this server shall quit.
	ch_quit chan vacuous_

	cmd      *exec.Cmd
	ch_stdio chan stdio_message

	heartbeat_misses int

	*backend_common
}

// BACKEND_COMMON is a static and common part of a server.  It is read
// from a configuration.  It is embedded and not directly used.
type backend_common struct {
	heartbeat_timeout int

	//mux_host int
	//mux_port int
	//mux_ep int
	//port_min int
	//port_max int
	//manager_pid int
}

type backend_command struct {
	argv []string
	envs []string
}

// (A single manager instance).
var the_manager = backend_manager{
	proc: make(map[int]backend),

	heartbeat_tolerance: 3,
}

func start_manager(m *backend_manager) {
	m.bin_sudo = "/usr/bin/sudo"
	m.environ = minimal_environ()
	m.be = the_backend_minio_factory
	m.be.configure()
	m.ch_sig = set_signal_handling()
	go reap_child_process(m)

	var svr = start_server(m)
	logger.info(fmt.Sprint("start_server()=", svr))
	var _ = svr.get_super_part()

	go ping_server(m, svr)

	{
		if false {
			cancel_process_for_test(m, svr)
		}

		if true {
			shutdown_process_for_test(m, svr)
		}

		fmt.Println("MORE 5 SEC")
		time.Sleep(5 * time.Second)
	}
}

func ping_server(m *backend_manager, svr backend) {
	var proc = svr.get_super_part()
	proc.heartbeat_misses = 0
	for {
		time.Sleep(1 * time.Second)
		fmt.Println("svr.heartbeat()", proc.heartbeat_misses)
		var status = svr.heartbeat()
		if status == 200 {
			proc.heartbeat_misses = 0
		} else {
			proc.heartbeat_misses += 1
		}
		if proc.heartbeat_misses > m.heartbeat_tolerance {
			logger.infof(("Mux(pool=%s)" +
				" Heartbeating server failed:" +
				" misses=%v"),
				proc.pool, proc.heartbeat_misses)
			raise(termination("MinIO heartbeat failure"))
		}
	}
}

func start_server(m *backend_manager) backend {
	fmt.Println("start_server()")
	//m.be = &backend_minio_template{}
	var svr = m.be.make_backend("", "")
	var proc = svr.get_super_part()

	var u, err4 = user.Current()
	assert_fatal(err4 == nil)
	proc.owner_uid = "#" + u.Uid
	proc.owner_gid = "#" + u.Gid
	proc.ep = "localhost:8080"
	proc.port = 8080
	proc.directory = u.HomeDir + "/pool-x"

	proc.root_user = generate_access_key()
	proc.root_password = generate_secret_key()

	proc.verbose = true
	proc.environ = m.environ

	var _ = try_start_server(m, svr)
	assert_fatal(proc.cmd.Process != nil)
	var pid = proc.cmd.Process.Pid
	m.proc[pid] = svr

	go barf_stdio_to_log(proc)

	svr.setup()
	fmt.Println("start_server() server=", svr)
	return svr
}

func stop_server(m *backend_manager, svr backend) {
	fmt.Println("stop_server()")
	var proc = svr.get_super_part()

	var _ = svr.shutdown()

	close(proc.ch_quit)
}

// TRY_START_SERVER starts a process and waits for a message or a
// timeout.  A message from the server is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_server(m *backend_manager, svr backend) start_result {
	var proc = svr.get_super_part()

	var user = proc.owner_uid
	var group = proc.owner_gid
	var address = proc.ep
	var directory = proc.directory
	var command = svr.make_command_line(address, directory)
	var sudo_argv = []string{
		m.bin_sudo,
		"-n",
		"-u", user,
		"-g", group}
	var argv = append(sudo_argv, command.argv...)
	var envs = append(m.environ, command.envs...)

	logger.debugf("Mux(pool=%s) Run a server: argv=%v.", proc.pool, argv)
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
		Pdeathsig:  unix.SIGTERM,
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
		fmt.Println("cmd.Start() err=", err3)
	}

	var r1 = wait_for_server_come_up(svr)
	fmt.Println("DONE DONE DONE DONE")
	fmt.Println("DONE state=", r1.start_state, r1.message)

	/*dump_threads()*/
	//} ()
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

// WAIT_FOR_SERVER_COME_UP waits until either a server (1) outputs an
// expected message, (2) outputs an error message, (3) outputs too
// many messages, (4) reaches a timeout, (5) closes both
// stdout+stderr.  It returns STARTED/TO_RETRY/FAILED.  It reads the
// stdio channel as much as available.
func wait_for_server_come_up(svr backend) start_result {
	var proc *backend_process = svr.get_super_part()
	// fmt.Printf("WAIT_FOR_SERVER_COME_UP() svr=%T proc=%T\n", svr, proc)

	var msg_out []string
	var msg_err []string

	defer func() {
		// It defers calling a closure to refer to finally collected
		// msg_out and msg_err.
		drain_start_messages_to_log(proc.pool, msg_out, msg_err)
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
				var st1 = svr.check_startup(on_out, msg_out)
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

func reap_child_process(m *backend_manager) {
	fmt.Println("reap_child_process() start")
	//proc map[int]backend_process
	//ch_sig chan sycall.Signal
	for sig := range m.ch_sig {
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

func cancel_process_for_test(m *backend_manager, svr backend) {
	fmt.Println("CANCEL IN 10 SEC")
	time.Sleep(10 * time.Second)
	var proc = svr.get_super_part()
	fmt.Println("cmd.Cancel()")
	var err5 = proc.cmd.Cancel()
	if err5 != nil {
		fmt.Println("cmd.Cancel()=", err5)
	}
}

func shutdown_process_for_test(m *backend_manager, svr backend) {
	fmt.Println("SHUTDOWN IN 10 SEC")
	time.Sleep(10 * time.Second)
	var proc = svr.get_super_part()
	stop_server(m, svr)
	var err5 = proc.cmd.Cancel()
	if err5 != nil {
		fmt.Println("cmd.Cancel()=", err5)
	}
}
