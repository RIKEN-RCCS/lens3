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

// MEMO: rc-port is http://127.0.0.1:5572/

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
// json in rclone-v1.66.0.  The regexp has matching parts (host and
// port) for extracting the port number from the url in the message.
var (
	date_time_pattern = `\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}`
	url_pattern       = `http://([^:]*|\[[^\]]*\]):([0-9]*)/`

	rclone_response_expected_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Local file system at [^:]*:` +
			` Starting s3 server on \[` + url_pattern + `\]$`)

	rclone_response_control_url_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Serving remote control on ` +
			url_pattern + `$`)

	rclone_response_s3_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to s3: .*$`)

	rclone_response_port_in_use_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to s3: failed to init server: listen tcp :[0-9]*:` +
			` bind: address already in use$`)

	rclone_response_rc_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to start remote control: .*$`)
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
func (d *backend_rclone) check_startup(stream int, mm []string) start_result {
	fmt.Println("rclone.check_startup1(%v)", mm)
	if stream == on_stdout {
		return start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
	fmt.Println("rclone.check_startup2(%v)", mm)

	var got_failure = rclone_response_s3_failure_re.MatchString
	var failure_found, m1 = find_one(mm, got_failure)
	if failure_found {
		var port_in_use = rclone_response_port_in_use_re.MatchString(m1)
		if port_in_use {
			return start_result{
				start_state: start_to_retry,
				message:     m1,
			}
		} else {
			return start_result{
				start_state: start_failed,
				message:     m1,
			}
		}
	}
	var got_expected = rclone_response_expected_re.MatchString
	var got_control = rclone_response_control_url_re.MatchString
	var expected_found, m2 = find_one(mm, got_expected)
	var control_found, m3 = find_one(mm, got_control)
	switch {
	case expected_found && control_found:
		var port, ok1 = parse_rclone_control_url_response(m3)
		if !ok1 {
			logger.errf("Mux(rclone) Got an expected message of rclone"+
				" but with a bad control url message: (%s)", m3)
			return start_result{
				start_state: start_failed,
				message:     ("bad control url message: " + m3),
			}
		}
		fmt.Println("*** EXPECTED=", port, m2)
		d.rc_port = port
		return start_result{
			start_state: start_started,
			message:     m2,
		}
	case expected_found && !control_found:
		logger.errf("Mux(rclone) Got an expected message of rclone" +
			" but without a control url message")
		return start_result{
			start_state: start_failed,
			message:     m1,
		}
	default:
		return start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
}

func parse_rclone_control_url_response(m string) (int, bool) {
	var w1 = rclone_response_control_url_re.FindStringSubmatch(m)
	if len(w1) != 3 {
		return 0, false
	}
	var port, err1 = strconv.Atoi(w1[2])
	if err1 != nil {
		return 0, false
	}
	return port, true
}

func (d *backend_rclone) establish() error {
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
	var rsp, err1 = c.Head(d.heartbeat_url)
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
	value map[string]any
	err   error
}

// SIMPLIFY_RCLONE_RC_MESSAGE returns a 2-tuple {value,nil} on
// success, or {nil,err} on failure or decoding error.  An empty
// output is a proper success.  A failure output looks like
// {"error":message,...}.
func simplify_rclone_rc_message(s []byte) *rclone_rc_result {
	var s2 = string(s)
	var r = strings.NewReader(s2)
	var dec = json.NewDecoder(r)
	var m map[string]any
	var err1 = dec.Decode(&m)
	if err1 != nil {
		logger.err("Mux(rclone) json decode failed")
		return &rclone_rc_result{nil, err1}
	}
	switch msg := m["error"].(type) {
	case nil:
		// OK.
	case string:
		var err2 = fmt.Errorf("(%s)", msg)
		return &rclone_rc_result{nil, err2}
	default:
		panic("never")
	}
	return &rclone_rc_result{m, nil}
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
