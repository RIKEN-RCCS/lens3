/* A sentinel for an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Golang prefers "x/sys/unix" over "syscall".  "SysProcAttr" is the
// same in x.sys.unix and syscall.

import (
	"bufio"
	"context"
	//"encoding/json"
	"fmt"
	"log"
	//"time"
	//"reflect"
	//"os"
	"os/exec"
	"os/user"
	"sync"
	//"os/signal"
	"bytes"
	//"syscall"
	"golang.org/x/sys/unix"
	//"strconv"
	//"time"
	//"testing"
)

// A manager watches the backend server state and records
// its outputs in the logs.  The first few lines from a server is used
// to check its start.  A server usually does not output anything
// later except on errors.
//
// MEMO: When a shutdown fails, a manager tries to kill a server by
// sudo's signal forwarding.  It works because sudo runs with the same
// RUID.  PDEATHSIG to exec.Command nor prctl(PR_SET_PDEATHSIG) does
// not work because of sudo.

type backend_s3i interface {
	check_startup()
	shutdown()
}

type backend_s3 struct {
	exec.Cmd
	stdout_buffer bytes.Buffer
	stderr_buffer bytes.Buffer

	// wait_to_come_up checks a server start by messages it outputs.
	// It looks for a specific message.  Also, it detects a closure of
	// stdout (a process exit) or a timeout.
	//     func wait_to_come_up(cmd exec.Cmd) (bool, bool)

}

type backend_minio struct{}

func (*backend_minio) wait_to_come_up(cmd *exec.Cmd) (bool, bool) {
	return true, true
}

func wait_for_server_to_come_up(cmd *exec.Cmd) (bool, bool) {
	var srv = new(backend_minio)
	var ok, continuable = srv.wait_to_come_up(cmd)
	return ok, continuable
}

// TRY_START_SERVER starts a process and waits for a message or a
// timeout.  A message from the server is one that indicates a
// success/failure.
func try_start_server(port int) {
	var u, err4 = user.Current()
	assert_fatal(err4 == nil)

	var ch1 = make(chan struct {
		int
		string
	})

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
