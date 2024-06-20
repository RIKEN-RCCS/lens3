/* Logger Setup. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"log/syslog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// SLOGGER is a logger.  It uses a default one first, but it will soon
// be replaced by one created in configure_logger().
var slogger = slog.Default()

// CONFIGURE_LOGGER makes a logger which is either a file logger or a
// syslog logger.  It also makes an additional logger for alerting (by
// MQTT).  It removes the "time" field for syslog.  See "Example
// (Wrapping)" in the "slog" document.
func configure_logger(logging *logging_conf, qch <-chan vacuous) {
	slog.SetLogLoggerLevel(slog.LevelDebug)

	var w1 io.Writer
	var notime bool
	if logging.Syslog.Log_file != "" {
		var f = logging.Syslog.Log_file
		var w2, err1 = os.OpenFile(f, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
		if err1 != nil {
			slog.Error("Opening a log file failed", "file", f, "err", err1)
			panic(nil)
		}
		w1 = w2
		notime = false
	} else {
		var fac = log_facility_map[logging.Syslog.Facility]
		var sev = log_severity_map[logging.Syslog.Level]
		var p syslog.Priority = sev | fac
		var w2, err2 = syslog.New(p, "lenticularis")
		if err2 != nil {
			slog.Error("Opening syslog failed", "err", err2)
			panic(nil)
		}
		w1 = w2
		notime = true
	}

	var replacer = func(groups []string, a slog.Attr) slog.Attr {
		if notime && a.Key == slog.TimeKey {
			return slog.Attr{}
		}
		if a.Key == slog.SourceKey {
			var s, ok1 = a.Value.Any().(*slog.Source)
			if ok1 {
				s.File = filepath.Base(s.File)
			}
		}
		return a
	}

	// Make a usual (file or syslog) logger.

	var source bool = logging.Syslog.Source_line
	var level = map_level_name(logging.Syslog.Level)
	var h1 slog.Handler = slog.NewTextHandler(w1, &slog.HandlerOptions{
		AddSource:   source,
		Level:       level,
		ReplaceAttr: replacer,
	})

	// Set the usual logger temporarily.  It is used until the end of
	// this function.

	slogger = slog.New(h1)

	// Maker a logger for alerting.

	var h2 slog.Handler = nil
	var alert slog.Level = slog.LevelInfo
	var mqtt *mqtt_client = nil
	if strings.EqualFold(logging.Alert.Queue, "mqtt") {
		mqtt = configure_mqtt(&logging.Mqtt, qch)
		alert = map_level_name(logging.Alert.Level)
		h2 = slog.NewTextHandler(mqtt, &slog.HandlerOptions{
			AddSource:   false,
			Level:       alert,
			ReplaceAttr: replacer,
		})
	}

	var hx = &slog_fork_handler{
		h1:    h1,
		h2:    h2,
		level: level,
		alert: alert,
	}

	// Set the logger.

	slogger = slog.New(hx)
}

// FETCH_SLOGGER_LEVEL returns a log level of an slog_fork_handler.
// It returns slog.LevelDebug when it is not an slog_fork_handler.
func fetch_slogger_level(logger *slog.Logger) slog.Level {
	var h = logger.Handler()
	switch logger1 := h.(type) {
	default:
		//fmt.Println("slogger_level()= default")
		return slog.LevelDebug
	case *slog_fork_handler:
		//fmt.Println("slogger_level()=", logger1.level)
		return logger1.level
	}
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
// handlers.  h1 is for main logging (with level), and h2 is for
// alerting (with alert).
type slog_fork_handler struct {
	h1    slog.Handler
	h2    slog.Handler
	level slog.Level
	alert slog.Level
}

func (x *slog_fork_handler) Enabled(ctx context.Context, l slog.Level) bool {
	return x.h1.Enabled(ctx, l)
}

// SLOG_FORK_HANDLER.HANDLE outputs to both logging and alerting
// targets.  Note that errors in MQTT are not reported here.
func (x *slog_fork_handler) Handle(ctx context.Context, r slog.Record) error {
	//fmt.Println("SLOG_FORK_HANDLER.Handle")
	var err1 = x.h1.Handle(ctx, r)
	if x.h2 != nil && r.Level >= x.alert {
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

// LOG_WRITER IS NOT USED.
// logger_ = &log_writer{slog.Default()}

type log_writer struct {
	o *slog.Logger
}

func (w *log_writer) critf(f string, a ...any) error {
	var m = fmt.Sprintf(f, a...)
	var ctx = context.Background()
	w.o.Log(ctx, log_CRIT, m)
	return nil
}

func (w *log_writer) errf(f string, a ...any) error {
	var m = fmt.Sprintf(f, a...)
	w.o.Debug(m)
	return nil
}

func (w *log_writer) warnf(f string, a ...any) error {
	var m = fmt.Sprintf(f, a...)
	w.o.Warn(m)
	return nil
}

func (w *log_writer) noticef(f string, a ...any) error {
	var m = fmt.Sprintf(f, a...)
	var ctx = context.Background()
	w.o.Log(ctx, log_NOTICE, m)
	return nil
}

func (w *log_writer) infof(f string, a ...any) error {
	var m = fmt.Sprintf(f, a...)
	w.o.Info(m)
	return nil
}

func (w *log_writer) debugf(f string, a ...any) error {
	var m = fmt.Sprintf(f, a...)
	w.o.Debug(m)
	return nil
}

var mux_access_log_file *os.File
var reg_access_log_file *os.File

func open_log_for_mux(f string) {
	var s, err1 = os.OpenFile(f, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err1 != nil {
		slogger.Error("Mux() Opening a log file failed", "err", err1)
		panic(nil)
	}
	mux_access_log_file = s
}

func open_log_for_reg(f string) {
	var s, err1 = os.OpenFile(f, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err1 != nil {
		slogger.Error("Reg() Opening a log file failed: err=(%v)", err1)
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
//  192.168.2.2 - - [02/Jan/2006:15:04:05 -0700] "GET /... HTTP/1.1"
//  200 333 "-" "aws-cli/1.18.156 Python/3.6.8
//  Linux/4.18.0-513.18.1.el8_9.x86_64 botocore/1.18.15"

func log_mux_access_by_response(rspn *http.Response, auth string) {
	var rqst = rspn.Request
	log_access("mux", rqst, rspn.StatusCode, rspn.ContentLength, "-", auth)
}

func log_mux_access_by_request(rqst *http.Request, code int, length int64, uid string, auth string) {
	log_access("mux", rqst, code, length, "-", auth)
}

func log_reg_access_by_request(rqst *http.Request, code int, length int64, uid string, auth string) {
	log_access("reg", rqst, code, length, "-", auth)
}

const common_log_time_layout = "02/Jan/2006:15:04:05 -0700"

// LOG_ACCESS logs accesses for both Multiplexer and Registrar.  The
// AUTH is an access-key, and it is always "-" for Registrar.
func log_access(src string, rqst *http.Request, code int, length int64, uid string, auth string) {

	// l: RFC 1413 client identity by identd
	// u: user
	// rf: Referer

	var h = rqst.RemoteAddr
	var l = "-"
	var u = uid
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
			auth)
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
