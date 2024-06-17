/* S3-server delegate for rclone serve s3. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// This is a backend for rclone.  The target is rclone-v1.66.0.

// MEMO: Starting rclone-serve-s3.
//
// rclone serve s3 '/home/someone/somewhere' [-vvv]
// --addr :{s3port} --auth-key "{id},{key}"
// --rc --rc-addr :{rcport}
// --rc-user {rcuser} --rc-pass {rcpass}
// [--force-path-style true]
// [--vfs-cache-mode full]

// MEMO: Stopping rclone-serve-s3 via a rc-command.
//
// % rclone rc --url :{rcport}
// --user {rcuser} --pass {rcpass} core/quit
//
// Some rc-commands: "core/quit", "job/list"

// MEMO: rc-port default is http://127.0.0.1:5572/
//
// MEMO: Option "--config=notfound" lets not use the rclone.conf file.
// "notfound" is a keyword.
//
// MEMO: vfs caching creates a cache in "~/.cache/rclone", and the
// subdirectories are "vfs/local" and "vfsMeta/local".

import (
	"bytes"
	//"errors"
	"context"
	"encoding/json"
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
	"regexp"
	"runtime"
	"strconv"
	"strings"
	//"time"
	//"reflect"
)

// Messages Patterns.  These are messages from rclone at its start-up.
// Lens3 avoids using "--use-json-log", since some messages are not in
// json in rclone-v1.66.0.  Checking port-in-use matches against the
// substring extracted from the failure message.
var (
	date_time_pattern = `\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}`
	url_pattern       = `http://([^:]*|\[[^\]]*\]):([0-9]*)/`

	rclone_response_expected_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Local file system at [^:]*:` +
			` Starting s3 server on \[` + url_pattern + `\]$`)

	rclone_response_s3_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to s3: (.*)$`)

	rclone_response_rc_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to start remote control: (.*)$`)

	rclone_response_port_in_use_re = regexp.MustCompile(
		`^` + `failed to init server: listen tcp :[0-9]*:` +
			` bind: address already in use$`)

	rclone_response_control_url_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Serving remote control on ` +
			url_pattern + `$`)
)

// BACKEND_RCLONE is a manager for rclone.
type backend_rclone struct {
	backend_delegate

	rc_port int
	rc_user string
	rc_pass string

	heartbeat_client *http.Client
	heartbeat_url    string

	*rclone_conf
}

// BACKEND_FACTORY_RCLONE.  See "backend_minio.go".
type backend_factory_rclone struct {
	*rclone_conf
	backend_conf
}

var the_backend_rclone_factory = &backend_factory_rclone{}

func (fa *backend_factory_rclone) configure(conf *mux_conf) {
	fa.rclone_conf = &conf.Rclone
	fa.backend_conf.use_n_ports = 2
}

func (fa *backend_factory_rclone) make_delegate(pool string) backend {
	var d = &backend_rclone{}
	// Set the super part.
	d.backend_conf = &fa.backend_conf
	// Set the local part.
	d.rclone_conf = the_backend_rclone_factory.rclone_conf
	d.rc_user = random_string(10)
	d.rc_pass = random_string(20)
	runtime.SetFinalizer(d, finalize_backend_rclone)
	return d
}

func (fa *backend_factory_rclone) clean_at_exit() {
	clean_tmp()
}

func finalize_backend_rclone(d *backend_rclone) {
}

func (d *backend_rclone) get_super_part() *backend_delegate {
	return &(d.backend_delegate)
}

func (d *backend_rclone) make_command_line(port int, directory string) backend_command {
	d.rc_port = (port + 1)
	var ep1 = net.JoinHostPort("", strconv.Itoa(port))
	var ep2 = net.JoinHostPort("", strconv.Itoa(port+1))
	var keypair = fmt.Sprintf("%s,%s", d.be.Root_access, d.be.Root_secret)
	var argv = []string{
		d.Rclone, "serve", "s3",
		directory,
		"--config", "notfound",
		"--addr", ep1, "--auth-key", keypair,
		"--rc", "--rc-addr", ep2,
		"--rc-user", d.rc_user, "--rc-pass", d.rc_pass,
	}
	argv = append(argv, d.Command_options...)
	var envs = []string{}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  All rclone's messages at a
// start are on stderr.
func (d *backend_rclone) check_startup(stream stdio_stream, mm []string) start_result {
	if stream == on_stdout {
		return start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
	//fmt.Printf("rclone.check_startup(%v)\n", mm)

	// Check failure.  Failure messages can be both by S3 and RC.

	var got_s3_failure = rclone_response_s3_failure_re.MatchString
	var failure_s3_found, m1 = find_one(mm, got_s3_failure)
	if failure_s3_found {
		var r1 = check_rclone_port_in_use(m1, rclone_response_s3_failure_re)
		return r1
	}

	var got_rc_failure = rclone_response_rc_failure_re.MatchString
	var failure_rc_found, m2 = find_one(mm, got_rc_failure)
	if failure_rc_found {
		var r2 = check_rclone_port_in_use(m2, rclone_response_rc_failure_re)
		return r2
	}

	// Check an expected message.

	var got_expected = rclone_response_expected_re.MatchString
	var expected_found, m3 = find_one(mm, got_expected)
	if expected_found {
		var got_control = rclone_response_control_url_re.MatchString
		var control_found, _ = find_one(mm, got_control)
		if !control_found {
			slogger.Warn("Mux(rclone) Got an expected message " +
				" but no control messages")
		}
		if d.verbose {
			slogger.Debug("Mux(rclone) Got an expected message", "output", m3)
		}
		return start_result{
			start_state: start_started,
			message:     m3,
		}
	}

	return start_result{
		start_state: start_ongoing,
		message:     "--",
	}
}

func check_rclone_port_in_use(m string, re *regexp.Regexp) start_result {
	var w1 = re.FindStringSubmatch(m)
	assert_fatal(w1 != nil && len(w1) == 2)
	var port_in_use = rclone_response_port_in_use_re.MatchString(w1[1])
	if port_in_use {
		return start_result{
			start_state: start_to_retry,
			message:     m,
		}
	} else {
		return start_result{
			start_state: start_failed,
			message:     m,
		}
	}
}

func (d *backend_rclone) establish() error {
	return nil
}

// SHUTDOWN stops a server using RC core/quit.
func (d *backend_rclone) shutdown() error {
	var proc = d.get_super_part()
	slogger.Debug("Mux(rclone) Stopping rclone",
		"pool", proc.Pool, "pid", proc.cmd.Process.Pid)
	var v1 = rclone_rc_core_quit(d)
	return v1.err
}

// HEARTBEAT calls s3.Client.ListBuckets() and returns a status code.
func (d *backend_rclone) heartbeat(w *manager) int {
	var proc = d.get_super_part()
	var be = get_backend(w.table, proc.Pool)
	if be == nil {
		return http_404_not_found
	}
	var code = heartbeat_backend(w, be)
	return code
}

// HEARTBEAT http-heads on the "/" path and returns a status code.  It
// returns 500 on a connection failure.
func (d *backend_rclone) heartbeat__() int {
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
	var rsp, err1 = c.Head(d.heartbeat_url)
	if err1 != nil {
		slogger.Debug("Mux(rclone) Heartbeat failed (http.Client.Get())",
			"pool", proc.Pool, "err", err1)
		return http_500_internal_server_error
	}
	defer rsp.Body.Close()
	var _, err2 = io.ReadAll(rsp.Body)
	if err2 != nil {
		slogger.Info("Mux(rclone) Heartbeat failed (io.ReadAll())",
			"pool", proc.Pool, "err", err2)
		panic(err2)
	}
	return rsp.StatusCode
}

// RCLONE_RC_RESULT is a decoding of an output of an RC-command.  On an
// error, it returns {nil,error}.
type rclone_rc_result struct {
	value map[string]any
	err   error
}

// SIMPLIFY_RCLONE_RC_MESSAGE returns a 2-tuple {value,nil} on
// success, or {nil,err} on failure or decoding error.  An empty
// output "{}" is a proper success.  A failure output looks like
// {"error":message,...}.
func simplify_rclone_rc_message(s []byte) *rclone_rc_result {
	var s2 = string(s)
	var r = strings.NewReader(s2)
	var dec = json.NewDecoder(r)
	var m map[string]any
	var err1 = dec.Decode(&m)
	if err1 != nil {
		slogger.Error("Mux(rclone) Bad message from rclone-rc",
			"output", s2, "err", err1)
		return &rclone_rc_result{nil, err1}
	}
	switch msg := m["error"].(type) {
	case nil:
		// OK.
	case string:
		var err2 = fmt.Errorf("%s", msg)
		return &rclone_rc_result{nil, err2}
	default:
		panic("never")
	}
	return &rclone_rc_result{m, nil}
}

// EXECUTE_RCLONE_RC_CMD runs an RC-command and checks its output.
// Note that a timeout kills the process by SIGKILL.  MEMO: Timeout of
// context returns "context.deadlineExceededError".
func execute_rclone_rc_cmd(d *backend_rclone, name string, command []string) *rclone_rc_result {
	var port = net.JoinHostPort("", strconv.Itoa(d.rc_port))
	var argv = []string{
		d.Rclone, "rc",
		"--url", port,
		"--user", d.rc_user,
		"--pass", d.rc_pass,
	}
	argv = append(argv, command...)
	var timeout = (time.Duration(d.Backend_timeout_ms) * time.Millisecond)
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
	var stdouts = strings.TrimSpace(stdoutb.String())
	var stderrs = strings.TrimSpace(stderrb.String())
	switch err2 := err1.(type) {
	case nil:
		// OK.
		if d.verbose {
			slogger.Debug("Mux(rclone) RC-command done",
				"cmd", argv, "exit", wstatus,
				"stdout", stdouts, "stderr", stderrs)
		}
	case *exec.ExitError:
		// NOT SUCCESSFUL.
		if wstatus == -1 {
			slogger.Error("Mux(rclone) RC-command signaled/unfinished",
				"cmd", argv, "err", err2,
				"stdout", stdouts, "stderr", stderrs)
			return &rclone_rc_result{nil, err2}
		}
	default:
		// ERROR.
		slogger.Error("Mux(rclone) RC-command faile",
			"cmd", argv, "err", err1,
			"stdout", stdouts, "stderr", stderrs)
		return &rclone_rc_result{nil, err1}
	}
	var v1 = simplify_rclone_rc_message([]byte(stdouts))
	if v1.err == nil {
		if d.verbose {
			slogger.Debug("Mux(rclone) RC-command OK",
				"cmd", command)
		} else {
			slogger.Debug("Mux(rclone) RC-command OK",
				"cmd", name)
		}
	} else {
		slogger.Error("Mux(rclone) RC-command failed",
			"cmd", argv, "err", v1.err,
			"stdout", stdouts, "stderr", stderrs)
	}
	return v1
}

func rclone_rc_core_quit(d *backend_rclone) *rclone_rc_result {
	var v1 = execute_rclone_rc_cmd(d, "core/quit",
		[]string{"core/quit"})
	return v1
}
