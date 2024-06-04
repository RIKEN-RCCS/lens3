/* S3-server delegate for rclone serve s3. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// MEMO: Starting rclone-serve-s3.
//
// rclone serve s3 '/home/someone/somewhere' [-vvv]
// --addr :{port} --auth-key "{id},{key}"
// --rc [--rc-addr :{port}]
// --rc-user {rcuser} --rc-pass {rcpass}
// [--force-path-style true]
// [--vfs-cache-mode full]

// MEMO: Stopping rclone-serve-s3 via a rc-command.
//
// % rclone rc --url :{port} core/quit
// --user {rcuser} --pass {rcpass}
//
// Some rc-commands: "core/quit", "job/list"

// MEMO: Option "--config=notfound" lets not use the rclone.conf file.
// "notfound" is a keyword.
//
// MEMO: vfs caching creates a cache in "~/.cache/rclone", and the
// subdirectories are "vfs/local" and "vfsMeta/local".

import (
	"bytes"
	"errors"
	//"encoding/json"
	"context"
	"fmt"
	"io"
	//"maps"
	"net"
	"time"
	//"syscall"
	//"os"
	"os/exec"
	//"path/filepath"
	//"log"
	"net/http"
	"runtime"
	"strconv"
	//"strings"
	"regexp"
	//"time"
	//"reflect"
)

// Messages from rclone at its start-up.  The regexp has a matching
// part for extracting the port number for RC commands from
// rclone_response_control.
var (
	date_time_pattern = `\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}`
	url_pattern       = `http://[^:]*:([0-9]*)`

	rclone_response_expected_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Local file system at [^:]*:` +
			` Starting s3 server on \[` + url_pattern + `\]$`)
	rclone_response_control_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Serving remote control on ` +
			url_pattern + `/$`)
	rclone_response_port_in_use_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to s3: failed to init server: listen tcp :[0-9]*:` +
			` bind: address already in use$`)
)

// BACKEND_RCLONE is a manager for rclone.
type backend_rclone struct {
	backend_process

	rc_port int
	rc_user string
	rc_pass string

	heartbeat_client *http.Client
	heartbeat_url    string

	*backend_rclone_conf
}

// BACKEND_RCLONE_CONF.  See "backend_minio.go".
type backend_rclone_conf struct {
	*rclone_conf
}

var the_backend_rclone_factory = &backend_rclone_conf{}

func (fa *backend_rclone_conf) make_delegate(pool string) backend {
	var d = &backend_rclone{}
	// Set the super part.
	d.Pool = pool
	// Set the local part.
	d.backend_rclone_conf = the_backend_rclone_factory
	d.rc_user = random_string(10)
	d.rc_pass = random_string(20)
	runtime.SetFinalizer(d, finalize_backend_rclone)
	return d
}

func (fa *backend_rclone_conf) configure(conf *mux_conf) {
	fa.rclone_conf = &conf.Rclone
}

func (fa *backend_rclone_conf) clean_at_exit() {
	clean_tmp()
}

func finalize_backend_rclone(d *backend_rclone) {
}

func (d *backend_rclone) get_super_part() *backend_process {
	return &(d.backend_process)
}

func (d *backend_rclone) make_command_line(address string, directory string) backend_command {
	var keypair = fmt.Sprintf("%s,%s", d.be.Root_access, d.be.Root_secret)
	var argv = []string{
		d.Rclone, "serve", "s3",
		directory,
		"--addr", address, "--auth-key", keypair,
		"--config", "notfound",
		"--rc", "--rc-user", d.rc_user, "--rc-pass", d.rc_pass,
		// [--rc-addr :8090]
	}
	argv = append(argv, d.Command_options...)
	var envs = []string{}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  See "backend_minio.go".
func (d *backend_rclone) check_startup(outerr int, ss []string) start_result {
	fmt.Println("rclone.check_startup()")
	var mm, _ = decode_json(ss)
	//fmt.Printf("mm=%T\n", mm)
	if len(mm) == 0 {
		return start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
	// var m1, fatal1 = check_fatal_exists(mm)
	var m1, error1 = find_one(mm, has_level_fatal)
	if error1 {
		assert_fatal(m1 != nil)
		var msg = get_string(m1, "message")
		switch {
		case rclone_response_port_in_use_re.MatchString(msg):
			//case strings.HasPrefix(msg, rclone_response_port_in_use):
			return start_result{
				start_state: start_to_retry,
				message:     msg,
			}
		default:
			return start_result{
				start_state: start_failed,
				message:     msg,
			}
		}
	}
	// var m2, expected1 = check_expected_exists(mm)
	var m2, expected1 = find_one(mm, has_expected_response)
	if expected1 {
		assert_fatal(m2 != nil)
		var msg = get_string(m2, "message")
		fmt.Println("*** EXPECTED=", msg)
		return start_result{
			start_state: start_started,
			message:     msg,
		}
	}
	return start_result{
		start_state: start_ongoing,
		message:     "--",
	}
}

func (d *backend_rclone) establish() error {
	fmt.Println("rclone.establish()")
	return nil
}

// SHUTDOWN stops a server using RC core/quit.
func (d *backend_rclone) shutdown() error {
	var proc = d.get_super_part()
	logger.debugf("Mux(rclone) Stopping rclone: pool=(%s) pid=%d",
		proc.Pool, proc.cmd.Process.Pid)
	var v1 = rclone_rc_core_quit(d)
	return v1.err
}

// HEARTBEAT http-heads on the "/" path and returns a status code.  It
// returns 500 on a connection failure.
func (d *backend_rclone) heartbeat() int {
	//fmt.Println("rclone.heartbeat()")
	var proc = d.get_super_part()

	if d.heartbeat_client == nil {
		var timeout = (time.Duration(proc.Heartbeat_timeout) * time.Second)
		d.heartbeat_client = &http.Client{
			Timeout: timeout,
		}
		var ep = proc.be.Backend_ep
		d.heartbeat_url = fmt.Sprintf("http://%s/", ep)
	}

	var c = d.heartbeat_client
	var rsp, err1 = c.Get(d.heartbeat_url)
	if err1 != nil {
		logger.debugf("Mux(rclone) Heartbeat failed (http.Client.Get()):"+
			" pool=(%s) err=(%v)", proc.Pool, err1)
		return http_500_internal_server_error
	}
	defer rsp.Body.Close()
	var _, err2 = io.ReadAll(rsp.Body)
	if err2 != nil {
		logger.infof("Mux(rclone) Heartbeat failed (io.ReadAll()):"+
			" pool=(%s) err=(%v)", proc.Pool, err2)
		panic(err2)
	}
	return rsp.StatusCode
}

// RCLONE_RC_RESULT is a decoding of an output of an RC-command.  On an
// error, it returns {nil,error}.
type rclone_rc_result struct {
	values []map[string]any
	err    error
}

// SIMPLIFY_RCLONE_RC_MESSAGE returns a 2-tuple {[value,...], ""} on success,
// or {nil, error-cause} on failure.  It extracts a message part from
// an error message.  RC-command may return zero or more values as
// separate json records.  An empty output is a proper success.  Each
// record is {"status": "success", ...}, containing a value.  An error
// record looks like: {"status": "error", "error": {"message":, ...,
// "cause": {"error": {"Code": ..., ...}}}}.  The
// "error/cause/error/Code" slot will be a keyword of useful
// information if it exists.  A returned 2-tuple may have a whole
// message instead of a cause-code if the slot is missing.
func simplify_rclone_rc_message(s []byte) *rclone_rc_result {
	var mm, ok = decode_json([]string{string(s)})
	if !ok {
		logger.err("Mux(rclone) json decode failed")
		var err1 = fmt.Errorf("RC-command returned a bad json: (%s)", s)
		return &rclone_rc_result{nil, err1}
	}

	for _, m := range mm {
		switch get_string(m, "status") {
		case "success":
			// Skip.
		case "error":
			if len(mm) != 1 {
				logger.warnf("Mux(rclone) RC-command with multiple errors: (%v)", mm)
			}
			var m1 = get_string(m, "error", "cause", "error", "Code")
			if m1 != "" {
				return &rclone_rc_result{nil, errors.New(m1)}
			}
			var m2 = get_string(m, "error", "message")
			if m2 != "" {
				return &rclone_rc_result{nil, errors.New(m2)}
			}
			return &rclone_rc_result{nil, fmt.Errorf("%s", m)}
		default:
			// Unknown status.
			return &rclone_rc_result{nil, fmt.Errorf("%s", m)}
		}
	}
	return &rclone_rc_result{mm, nil}
}

// EXECUTE_RCLONE_RC_CMD runs an RC-command command and checks its output.
// Note that a timeout kills the process by SIGKILL.  MEMO: Timeout of
// context returns "context.deadlineExceededError".
func execute_rclone_rc_cmd(d *backend_rclone, name string, command []string) *rclone_rc_result {
	var port = net.JoinHostPort("", strconv.Itoa(d.rc_port))
	var argv = []string{
		d.Rclone, "rc",
		"--url", port,
	}
	argv = append(argv, command...)
	var timeout = (time.Duration(d.Backend_command_timeout) * time.Second)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	var stdoutb, stderrb bytes.Buffer
	cmd.Stdin = nil
	cmd.Stdout = &stdoutb
	cmd.Stderr = &stderrb
	cmd.Env = *d.environ
	var err1 = cmd.Run()
	//fmt.Println("cmd.Run()=", err1)
	var wstatus = cmd.ProcessState.ExitCode()
	switch err2 := err1.(type) {
	case nil:
		// OK.
		if d.verbose {
			logger.debugf("Mux(rclone) RC-command done:"+
				" cmd=(%v) exit=%d stdout=(%s) stderr=(%s)",
				argv, wstatus, stdoutb.String(), stderrb.String())
		}
	case *exec.ExitError:
		// NOT SUCCESSFUL.
		if wstatus == -1 {
			logger.errf("Mux(rclone) RC-command signaled/unfinished:"+
				" cmd=(%v) err=(%v) stdout=(%s) stderr=(%s)",
				argv, err2, stdoutb.String(), stderrb.String())
			return &rclone_rc_result{nil, err2}
		}
	default:
		// ERROR.
		logger.errf("Mux(rclone) RC-command failed:"+
			" cmd=(%v) err=(%v) stdout=(%s) stderr=(%s)",
			argv, err1, stdoutb.String(), stderrb.String())
		return &rclone_rc_result{nil, err1}
	}
	var v1 = simplify_rclone_rc_message(stdoutb.Bytes())
	if v1.err == nil {
		if d.verbose {
			logger.debugf("Mux(rclone) RC-command OK: cmd=(%v)", command)
		} else {
			logger.debugf("Mux(rclone) RC-command OK: cmd=(%s)", name)
		}
	} else {
		logger.errf("Mux(rclone) RC-command failed:"+
			" cmd=(%v) err=(%v) stdout=(%s) stderr=(%s)",
			argv, v1.err, stdoutb.String(), stderrb.String())
	}
	return v1
}

func rclone_rc_core_quit(d *backend_rclone) *rclone_rc_result {
	var v1 = execute_rclone_rc_cmd(d, "core/quit",
		[]string{"core/quit"})
	return v1
}
