/* A sentinel for an S3-server process. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A manager is responsible for watching the process state and the
// output from an S3-server, although an S3-server usually does not
// output anything but start and end messages.

import (
	"context"
	//"encoding/json"
	"fmt"
	//"log"
	//"time"
	//"reflect"
	//"os"
	"os/exec"
	//"os/signal"
	//"syscall"
	"bytes"
	"time"
	//"testing"
)

type backend_s3 struct {
	exec.Cmd
	stdout_buffer bytes.Buffer
	stderr_buffer bytes.Buffer

	// wait_to_come_up checks a server start by messages it outputs.
	// It looks for a specific message.  Also, it detects a closure of
	// stdout (a process exit) or a timeout.
	//     func wait_to_come_up(cmd exec.Cmd) (bool, bool)
}

func try_start_server(port int, user int, group int, directory string) {
	//pool_id = self._pool_id
	//tables = self._tables
	//address = f":{port}"

	var server_start_timeout = 1000 * time.Millisecond

	//var bin_sudo = "/usr/bin/sudo"
	//var bin_minio = "/home/users/m-matsuda/bin/doit.sh"
	//var argv = []string{
	//	bin_sudo,
	//	"-n",
	//	"-u", user,
	//	"-g", group,
	//	bin_minio,
	//	"--json", "--anonymous", "server",
	//	"--address", address, directory}

	{
		fmt.Println("Manager (pool={pool_id}) starting MinIO: {cmd}")

		//	var attr = syscall.ProcAttr{
		//        Dir:   "/tmp",
		//        Env:   []string{},
		//        Files: []uintptr{fstdin.Fd(), fstdout.Fd(), fstderr.Fd()},
		//        Sys: &syscall.SysProcAttr{
		//			Foreground: false,
		//		},
		//	}

		//self._set_alarm(self._minio_start_timeout, "start-minio")
		var ctx, cancel = context.WithTimeout(context.Background(),
			server_start_timeout)
		defer cancel()
		var cmd = exec.CommandContext(ctx, "sleep", "5")
		var err = cmd.Run()
		if err != nil {
			fmt.Println("cmd.Run() errs")
		}
		var _, _ = wait_for_server_to_come_up(cmd)

		//self._set_alarm(0, None)
		select {
		case <-ctx.Done():
			fmt.Println("ctx.Done()")
			fmt.Println(ctx.Err())
		}

		//	if ok {
		//		fmt.Println("Manager (pool={pool_id}) MinIO started.")
		//		//self._minio_ep = host_port(self._mux_host, port)
		//		//return (p, True)
		//	} else {
		//		//self._minio_ep = None
		//		//return (None, continuable)
		//	}
	}

	//defer func() {
	//	// (e is SubprocessError, OSError, ValueError, usually).
	//	m = rephrase_exception_message(e)
	//	logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
	//		f" command=({cmd}); exception=({m})",
	//		exc_info=True)
	//	reason = Pool_Reason.EXEC_FAILED + f"{m}"
	//	set_pool_state(tables, pool_id, Pool_State.INOPERABLE, reason)
	//	self._minio_ep = None
	//	return (None, False)
	//}
	//defer func() {
	//	self._set_alarm(0, None)
	//	pass
	//}()
	//assert p is None
	//self._minio_ep = None
	//return (None, True)
}

type backend_minio struct{}

func (*backend_minio) wait_to_come_up(cmd *exec.Cmd) (bool, bool) {
	return true, true
}

func wait_for_server_to_come_up(cmd *exec.Cmd) (bool, bool) {
	var server = new(backend_minio)
	var ok, continuable = server.wait_to_come_up(cmd)
	return ok, continuable
}
