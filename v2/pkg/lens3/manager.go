/* A sentinel for an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// A manager watches the backend server state and records
// its outputs in the logs.  The first few lines from a server is used
// to check its start.  A server usually does not output anything
// later except on errors.
//
// MEMO: A manager tries to kill a server by sudo's signal forwarding,
// when a shutdown fails.  Signal forwarding works because sudo runs
// with the same RUID.  PDEATHSIG in exec/Command nor
// prctl(PR_SET_PDEATHSIG) does not work because of sudo.  Also, a
// default in exec/Command.Cancel kills with SIGKILL, and it does not
// work with sudo.  See "src/os/exec/exec.go".  A cancel function is
// replaced by one with SIGTERM.

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
	//"os"
	"os/exec"
	"os/user"
	"sync"
	//"os/signal"
	//"bytes"
	//"syscall"
	"golang.org/x/sys/unix"
	//"runtime"
	//"reflect"
	//"strconv"
	//"time"
	//"testing"
)

type backend interface {
	get_generic_part() *backend_process
	check_startup(int, []string) start_result
	shutdown()
}

type backend_process struct {
	*exec.Cmd
	ch_stdio chan stdio_message

	//stdout_buffer bytes.Buffer
	//stderr_buffer bytes.Buffer

	// wait_to_come_up checks a server start by messages it outputs.
	// It looks for a specific message.  Also, it detects a closure of
	// stdout (a process exit) or a timeout.
	//     func wait_to_come_up(cmd exec.Cmd) (bool, bool)
}

type backend_minio struct {
	backend_process
}

func (svr *backend_minio) get_generic_part() *backend_process {
	return &(svr.backend_process)
}

// TRY_START_SERVER starts a process and waits for a message or a
// timeout.  A message from the server is one that indicates a
// success/failure.  Note that it changes a cancel function from
// SIGKILL to SIGTERM to make it work with sudo.
func try_start_server(port int) {
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
	cmd.Stdin = nil
	var o1, err1 = cmd.StdoutPipe()
	if err1 != nil {
		log.Fatal(err1)
	}
	var e2, err2 = cmd.StderrPipe()
	if err2 != nil {
		log.Fatal(err2)
	}
	var err3 = cmd.Start()
	if err3 != nil {
		fmt.Println("cmd.Start() err=", err3)
	}

	cmd.Cancel = func() error {
		return cmd.Process.Signal(unix.SIGTERM)
	}

	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		var sc1 = bufio.NewScanner(o1)
		for sc1.Scan() {
			var s2 = sc1.Text()
			ch1 <- struct {
				int
				string
			}{1, s2}
		}
		fmt.Println("close(out)")
		//close(ch1)
	}()
	go func() {
		defer wg.Done()
		var sc2 = bufio.NewScanner(e2)
		for sc2.Scan() {
			var s3 = sc2.Text()
			ch1 <- struct {
				int
				string
			}{2, s3}
		}
		fmt.Println("close(err)")
		//close(ch1)
	}()
	go func() {
		wg.Wait()
		close(ch1)
	}()

	go func() {
		time.Sleep(10 * time.Second)
		fmt.Println("cmd.Cancel()")
		var err5 = cmd.Cancel()
		if err5 != nil {
			fmt.Println("cmd.Cancel()=", err5)
		}
	}()

	var svr = backend_minio{
		backend_process{
			cmd,
			ch1,
		},
	}

	var r1 = wait_for_server_come_up(&svr)
	fmt.Println("DONE state=", r1.start_state, r1.message)

	//go func() {
	for {
		var x1, ok1 = <-ch1
		if !ok1 {
			fmt.Println("CLOSED")
			break
		}
		fmt.Println("LINE: ", x1.int, x1.string)
	}
	fmt.Println("DONE")
	//} ()
}

func kill_server__(pid int) {
	var err1 = unix.Kill(pid, unix.SIGTERM)
	fmt.Println("unix.Kill()", err1)
}

func (*backend_minio) wait_to_come_up(cmd *exec.Cmd) (bool, bool) {
	return true, true
}

const (
	on_out int = iota + 1
	on_err
)

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
	var cmd *backend_process = svr.get_generic_part()

	fmt.Printf("WAIT_FOR_SERVER_COME_UP() svr=%T cmd=%T\n", svr, cmd)

	var msg_out []string
	var msg_err []string

	defer drain_messages_to_log(msg_out, msg_err)

	var to = time.After(60 * time.Second)
	for {
		select {
		case msg, ok1 := <-cmd.ch_stdio:
			if !ok1 {
				var r1 = start_result{
					start_state: start_failed,
					message:     "pipe closed",
				}
				return r1
			}
			switch msg.int {
			case on_out:
				msg_out = append(msg_out, msg.string)
				var st1 = svr.check_startup(on_out, msg_out)
				switch st1.start_state {
				case start_ongoing:
					continue
				case start_started:
					return st1
				case start_to_retry:
					return st1
				case start_failed:
					return st1
				}
			case on_err:
				msg_err = append(msg_err, msg.string)
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
	for _, _ = range outs {
		//log.Info(m)
	}
	for _, _ = range errs {
		//log.Info(m)
	}
}
