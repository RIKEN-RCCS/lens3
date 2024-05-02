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
	"os/signal"
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

// BACKEND specific part.  A backend never start its own threads.
type backend interface {
	// GET_SUPER_PART returns a generic part or a superclass.
	get_super_part() *backend_generic

	// CHECK_STARTUP checks a start of a server. It is called each
	// time a server outputs a line of a message.  It looks for a
	// specific message.  The first argument indicates stdout or
	// stderr by values on_out and on_err.  The passed strings are
	// accumulated all from the start.
	check_startup(int, []string) start_result

	// SHUTDOWN stops a server by its specific way.
	shutdown()

	// HEARTBEAT pings a server and returns an http status.
	heartbeat() int
}

type backend_generic struct {
	pool_id string

	// CH_QUIT is to inform stopping the server by closing.  Every
	// thread for this server shall quit.
	ch_quit chan struct{}

	cmd      *exec.Cmd
	ch_stdio chan stdio_message

	ep string

	heartbeat_misses int

	heartbeat_timeout int

	verbose bool

	/* **************** */

	//mux_host int
	//mux_port int
	//mux_ep int
	//port_min int
	//port_max int
	//manager_pid int
}

type backend_manager struct {
	// PROC maps a PID to a process record.  PID is int in "os".
	proc map[int]backend

	// CH_SIG is a channel to receive SIGCHLD.
	ch_sig chan os.Signal

	//ctl_param map[string]any

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

// (A single manager instance).
var manager = backend_manager{
	proc: make(map[int]backend),

	heartbeat_tolerance: 3,
}

func start_manager(m *backend_manager) {
	m.ch_sig = set_signal_handling()
	go reap_gone_child(m)

	{
		var svr = start_server(m)
		logger.Info(fmt.Sprint("start_server()=", svr))
		var proc = svr.get_super_part()

		go ping_server(m, svr)

		fmt.Println("CANCEL IN 10 SEC")
		time.Sleep(10 * time.Second)
		fmt.Println("cmd.Cancel()")
		var err5 = proc.cmd.Cancel()
		if err5 != nil {
			fmt.Println("cmd.Cancel()=", err5)
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
			logger.Info("Manager (pool={pool_id})" +
				" Heartbeating server failed:" +
				" misses={self._heartbeat_misses}")
			raise(termination("MinIO heartbeat failure"))
		}
	}
}

func start_server(m *backend_manager) backend {
	var svr, _ = try_start_server(8001)
	fmt.Println("try_start_server()=", svr)
	var proc = svr.get_super_part()
	var pid = proc.cmd.Process.Pid
	m.proc[pid] = svr

	go barf_stdio_to_log(proc)

	return svr
}

func stop_server(m *backend_manager, svr backend) {
	var proc = svr.get_super_part()
	close(proc.ch_quit)
}

func barf_stdio_to_log(proc *backend_generic) {
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

// TRY_START_SERVER starts a process and waits for a message or a
// timeout.  A message from the server is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_server(port int) (backend, start_result) {
	var u, err4 = user.Current()
	assert_fatal(err4 == nil)

	var ch1 = make(chan stdio_message)

	var bin_sudo = "/usr/bin/sudo"
	var bin_minio = "/usr/local/bin/minio"
	var address = "localhost:8080"
	var user = "#" + u.Uid
	var group = "#" + u.Gid
	var directory = u.HomeDir + "/pool-x"
	var argv = []string{
		"-n",
		"-u", user,
		"-g", group,
		bin_minio,
		"--json", "--anonymous", "server",
		"--address", address, directory}
	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, bin_sudo, argv...)
	if cmd == nil {
		panic("cmd=nil")
	}
	assert_fatal(cmd.SysProcAttr == nil)
	cmd.SysProcAttr = &unix.SysProcAttr{
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

	var proc = backend_generic{
		cmd:      cmd,
		ch_stdio: ch1,

		pool_id:           "",
		ep:                "localhost:8080",
		heartbeat_timeout: 60,
		verbose:           true,
	}
	var svr = backend_minio{
		backend_generic: proc,
	}

	drain_stdio(&proc)

	var err3 = cmd.Start()
	if err3 != nil {
		fmt.Println("cmd.Start() err=", err3)
	}

	var r1 = wait_for_server_come_up(&svr)
	fmt.Println("DONE DONE DONE DONE")
	fmt.Println("DONE state=", r1.start_state, r1.message)

	/*dump_threads()*/
	//} ()
	return &svr, r1
}

// DRAIN_STDIO spawns threads for draining stdout+stderr to a channel
// until closed.  It returns immediately.  It drains one line at a
// time.  It closes the channel when both are closed.
func drain_stdio(proc *backend_generic) {
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
// stdout+stderr.  It returns STARTED/TO_RETRY/FAILED.
func wait_for_server_come_up(svr backend) start_result {
	var cmd *backend_generic = svr.get_super_part()

	// fmt.Printf("WAIT_FOR_SERVER_COME_UP() svr=%T cmd=%T\n", svr, cmd)

	var msg_out []string
	var msg_err []string

	defer func() {
		// It defers calling a closure to refer to finally collected
		// msg_out and msg_err.
		drain_messages_to_log(msg_out, msg_err)
	}()

	var to = time.After(60 * time.Second)
	for {
		select {
		case msg, ok1 := <-cmd.ch_stdio:
			if !ok1 {
				return start_result{
					start_state: start_failed,
					message:     "pipe closed",
				}
			}
			//fmt.Println("MSG:", msg)
			switch msg.int {
			case on_out:
				msg_out = append(msg_out, msg.string)
				var st1 = svr.check_startup(on_out, msg_out)
				switch st1.start_state {
				case start_ongoing:
					if len(msg_out) > 500 {
						return start_result{
							start_state: start_failed,
							message:     "stdout flooding",
						}
					}
					continue
				case start_started:
					fmt.Println("*SERVER COME UP*")
					return st1
				case start_to_retry:
					return st1
				case start_failed:
					return st1
				}
			case on_err:
				msg_err = append(msg_err, msg.string)
				if len(msg_err) > 500 {
					return start_result{
						start_state: start_failed,
						message:     "stderr flooding",
					}
				}
				continue
			default:
				panic(&fatal_error{"never"})
			}
		case <-to:
			var f2 = start_result{
				start_state: start_failed,
				message:     "timeout",
			}
			return f2
		}
	}
}

func drain_messages_to_log(outs []string, errs []string) {
	fmt.Println("drain_messages_to_log")
	var s string
	for _, s = range outs {
		fmt.Println("LINE:", s)
		//log.Info(m)
	}
	for _, s = range errs {
		fmt.Println("LINE:", s)
		//log.Info(m)
	}
}

func set_signal_handling() chan os.Signal {
	fmt.Println("set_signal_handling()")
	var ch = make(chan os.Signal, 1)
	signal.Notify(ch, unix.SIGCHLD, unix.SIGHUP)
	return ch
}

func reap_gone_child(m *backend_manager) {
	fmt.Println("reap_gone_child() start")
	//proc map[int]backend_generic
	//ch_sig chan sycall.Signal
	for sig := range m.ch_sig {
		switch sig {
		case unix.SIGCHLD:
			fmt.Println("Got SIGCHLD")
			var wstatus unix.WaitStatus
			var options int = unix.WNOHANG
			var rusage unix.Rusage
			var wpid, err1 = unix.Wait4(-1, &wstatus, options, &rusage)
			fmt.Println("wait4 wpid=", wpid, "err1=", err1)
			if err1 != nil {
				var err, ok = err1.(unix.Errno)
				if !ok {
					fmt.Println("bad error from wait")
				} else {
					if err == unix.ECHILD {
						fmt.Println("wait but no children")
					} else {
						fmt.Println("errno=", err)
					}
				}
			} else {
				fmt.Println("wait pid=", wpid, "status=", wstatus, "rusage=", rusage)
			}
		case unix.SIGHUP:
			fmt.Println("SIGHUP")
		default:
			// unix.SignalName(sig)
			fmt.Println("unhandled signal SIG=", sig)
		}
	}
	fmt.Println("reap_gone_child() channel closed")
}
