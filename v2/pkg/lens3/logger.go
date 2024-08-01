/* Logger Setup. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"context"
	"fmt"
	"log/slog"
	"log/syslog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// SLOGGER is a logger.  It uses a default one first, but it will be
// replaced by one created in configure_logger().
var slogger = slog.Default()

// TRACING is a flag for low-level tracing.  Trace outputs go
// debug-level logging.  They are usually not interesting.
var tracing trace_flag = 0

type trace_flag uint32

const (
	trace_proxy trace_flag = 1 << iota
	trace_task
	trace_dos
	trace_proc
	trace_4_
	trace_5_
	trace_db_set
	trace_db_get
)

// CONFIGURE_LOGGER makes a logger which is a pair of a file logger
// and an alert logger.  An alert logger is optional and either syslog
// or MQTT.  It removes the "time" field for syslog.  See "Example
// (Wrapping)" in the "slog" document.
func configure_logger(logconf *logging_conf, qch <-chan vacuous) {
	slog.SetLogLoggerLevel(slog.LevelDebug)

	// Make a file logger (mandatory).

	var file1 = logconf.Logger.Log_file
	var level1 slog.Level = map_level_name(logconf.Logger.Level)
	var source1 bool = logconf.Logger.Source_line
	var h1 slog.Handler = make_file_logger(file1, level1, source1)

	// Set the file logger temporarily.  It is used until the end of
	// this function.

	slogger = slog.New(h1)

	// Make an alert logger (syslog or MQTT).

	var h2 slog.Handler = nil
	var level2 slog.Level = slog.LevelWarn
	var queue string = ""
	if logconf.Alert != nil {
		queue = logconf.Alert.Queue
		level2 = map_level_name(logconf.Alert.Level)
	}
	if strings.EqualFold(queue, "syslog") {
		if logconf.Syslog == nil {
			slog.Error("No syslog configuration")
			panic(nil)
		}
		var sev = log_severity_map[logconf.Alert.Level]
		var fac = log_facility_map[logconf.Syslog.Facility]
		var p syslog.Priority = (sev | fac)
		var w2, err2 = syslog.New(p, "lenticularis")
		if err2 != nil {
			slog.Error("Opening syslog failed", "err", err2)
			panic(nil)
		}
		var replacer2 = func(groups []string, a slog.Attr) slog.Attr {
			if a.Key == slog.TimeKey {
				return slog.Attr{}
			}
			return a
		}
		h2 = slog.NewTextHandler(w2, &slog.HandlerOptions{
			AddSource:   false,
			Level:       level2,
			ReplaceAttr: replacer2,
		})
	} else if strings.EqualFold(queue, "mqtt") {
		if logconf.Mqtt == nil {
			slog.Error("No mqtt configuration")
			panic(nil)
		}
		var mqtt *mqtt_client = configure_mqtt(logconf.Mqtt, qch)
		h2 = slog.NewTextHandler(mqtt, &slog.HandlerOptions{
			AddSource:   false,
			Level:       level2,
			ReplaceAttr: nil,
		})
	} else if logconf.Alert != nil {
		slog.Error("Bad alert logging configuration", "queue", queue)
		panic(nil)
	}

	var hx = &slog_fork_handler{
		h1:     h1,
		h2:     h2,
		level1: level1,
		level2: level2,
	}

	// Set the logger.

	slogger = slog.New(hx)
}

func make_file_logger(file string, level slog.Level, source bool) slog.Handler {
	var w1, err1 = os.OpenFile(file, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err1 != nil {
		slog.Error("Opening a log file failed", "file", file, "err", err1)
		panic(nil)
	}
	var replacer = func(groups []string, a slog.Attr) slog.Attr {
		if a.Key == slog.SourceKey {
			var s, ok1 = a.Value.Any().(*slog.Source)
			if ok1 {
				s.File = filepath.Base(s.File)
			}
		}
		return a
	}
	var h = slog.NewTextHandler(w1, &slog.HandlerOptions{
		AddSource:   source,
		Level:       level,
		ReplaceAttr: replacer,
	})
	return h
}

const (
	log_CRIT   = slog.Level(9)
	log_NOTICE = slog.Level(2)
)

var log_level_name = map[string]slog.Level{
	//"EMERG"
	//"ALERT"
	"CRIT":    log_CRIT,
	"ERR":     slog.LevelError,
	"WARNING": slog.LevelWarn,
	"NOTICE":  log_NOTICE,
	"INFO":    slog.LevelInfo,
	"DEBUG":   slog.LevelDebug,
}

var log_severity_map = map[string]syslog.Priority{
	//LOG_EMERG
	//LOG_ALERT
	"CRIT":    syslog.LOG_CRIT,
	"ERR":     syslog.LOG_ERR,
	"WARNING": syslog.LOG_WARNING,
	"NOTICE":  syslog.LOG_NOTICE,
	"INFO":    syslog.LOG_INFO,
	"DEBUG":   syslog.LOG_DEBUG,
}

var log_facility_map = map[string]syslog.Priority{
	"LOCAL0": syslog.LOG_LOCAL0,
	"LOCAL1": syslog.LOG_LOCAL1,
	"LOCAL2": syslog.LOG_LOCAL2,
	"LOCAL3": syslog.LOG_LOCAL3,
	"LOCAL4": syslog.LOG_LOCAL4,
	"LOCAL5": syslog.LOG_LOCAL5,
	"LOCAL6": syslog.LOG_LOCAL6,
	"LOCAL7": syslog.LOG_LOCAL7,
}

func map_level_name(n string) slog.Level {
	var l, ok = log_level_name[n]
	if ok {
		return l
	} else {
		return slog.LevelInfo
	}
}

// SLOG_FORK_HANDLER is a handler which copies messages to two
// handlers.  h1 (with level1) is for a file logger, and h2 (with
// level2) is for an alert logger.
type slog_fork_handler struct {
	h1     slog.Handler
	h2     slog.Handler
	level1 slog.Level
	level2 slog.Level
}

func (x *slog_fork_handler) Enabled(ctx context.Context, l slog.Level) bool {
	return x.h1.Enabled(ctx, l)
}

// SLOG_FORK_HANDLER.HANDLE outputs to both file and alert logger
// targets.  Note that errors in MQTT publishing (that are marked by
// the "alert" key) are not reported, because they would recurse.
func (x *slog_fork_handler) Handle(ctx context.Context, r slog.Record) error {
	//fmt.Println("SLOG_FORK_HANDLER.Handle")
	var err1 = x.h1.Handle(ctx, r)
	if x.h2 != nil && r.Level >= x.level2 {
		var skip bool = false
		r.Attrs(func(a slog.Attr) bool {
			if a.Key == "alert" {
				skip = true
				return false
			}
			return true
		})
		if !skip {
			var _ = x.h2.Handle(ctx, r)
		}
	}
	return err1
}

func (x *slog_fork_handler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return x.h1.WithAttrs(attrs)
}

func (x *slog_fork_handler) WithGroup(name string) slog.Handler {
	return x.h1.WithGroup(name)
}

var mux_access_log_file *os.File
var reg_access_log_file *os.File

func open_log_for_mux(f string) {
	var s, err1 = os.OpenFile(f, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err1 != nil {
		slogger.Error("Opening a log file failed", "err", err1)
		panic(nil)
	}
	mux_access_log_file = s
}

func open_log_for_reg(f string) {
	var s, err1 = os.OpenFile(f, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err1 != nil {
		slogger.Error("Opening a log file failed", "err", err1)
		panic(nil)
	}
	reg_access_log_file = s
}

// MEMO: Apache httpd access log format:
//
// LogFormat %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i" combined
//
// https://en.wikipedia.org/wiki/Common_Log_Format
//
// EXAMPLE:
//   192.168.2.2 - - [02/Jan/2006:15:04:05 -0700] "GET /... HTTP/1.1"
//   200 333 "-" "aws-cli/1.18.156 Python/3.6.8
//   Linux/4.18.0-513.18.1.el8_9.x86_64 botocore/1.18.15"

func log_mux_access_by_response(rspn *http.Response, auth string) {
	var rqst = rspn.Request
	log_access("mux", rqst, rspn.StatusCode, rspn.ContentLength, "", auth)
}

func log_mux_access_by_request(rqst *http.Request, code int, length int64, uid string, auth string) {
	log_access("mux", rqst, code, length, uid, auth)
}

func log_reg_access_by_request(rqst *http.Request, code int, length int64, uid string, auth string) {
	log_access("reg", rqst, code, length, uid, auth)
}

const common_log_time_layout = "02/Jan/2006:15:04:05 -0700"

// LOG_ACCESS logs accesses for both Multiplexer and Registrar.  The
// AUTH is an access-key, and it is always "-" for Registrar.
func log_access(src string, rqst *http.Request, code int, length int64, uid string, auth string) {
	var uid1 = ITE(uid != "", uid, "-")
	var auth1 = ITE(auth != "", auth, "-")

	// l: RFC 1413 client identity by identd
	// u: user
	// rf: Referer

	var h = rqst.RemoteAddr
	var l = "-"
	var u = uid1
	var t = time.Now().Format(common_log_time_layout)
	var r = fmt.Sprintf("%s %s %s", rqst.Method, rqst.URL, rqst.Proto)
	var s = fmt.Sprintf("%d", code)
	var b = fmt.Sprintf("%d", length)
	var rf = "-"
	var ua = rqst.Header.Get("User-Agent")

	switch src {
	case "mux":
		var f *os.File = mux_access_log_file
		var msg1 = fmt.Sprintf(
			("%s %s %s [%s] %q" + " %s %s %q %q" + " auth=%q" + "\n"),
			h, l, u, t, r,
			s, b, rf, ua,
			auth1)
		var _, err1 = f.WriteString(msg1)
		if err1 != nil {
			slogger.Error("Mux() Wrinting access log failed",
				"err", err1)
		}
	case "reg":
		var f *os.File = reg_access_log_file
		var msg2 = fmt.Sprintf(
			("%s %s %s [%s] %q" + " %s %s %q %q" + "\n"),
			h, l, u, t, r,
			s, b, rf, ua)
		var _, err2 = f.WriteString(msg2)
		if err2 != nil {
			slogger.Error("Reg() Wrinting access log failed",
				"err", err2)
		}
	default:
		panic(nil)
	}
}
