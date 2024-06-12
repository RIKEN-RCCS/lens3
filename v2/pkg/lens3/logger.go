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
	"time"
)

// "slogger" is with a source file:line.  "logger" is without a source
// file:line, because its calls are nested and from this file.
var slogger = slog.Default()
var logger = &log_writer{slog.Default()}

func configure_logger(logging *logging_conf) {
	slog.SetLogLoggerLevel(slog.LevelDebug)
	slogger = make_logger(logging, true)
	logger = &log_writer{make_logger(logging, false)}
}

// It removes the "time" field for output to syslog.
func make_logger(logging *logging_conf, source bool) *slog.Logger {
	var w io.Writer
	var replacer func(groups []string, a slog.Attr) slog.Attr
	if logging.Syslog.Log_file != "" {
		fmt.Println("configure_logger(OPENFILE)")
		var w1, err1 = os.OpenFile(logging.Syslog.Log_file,
			os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
		if err1 != nil {
			logger.critf("Opening a log file failed: err=(%v)", err1)
			panic("")
		}
		w = w1
		replacer = nil
	} else {
		var fac = log_facility_map[logging.Syslog.Facility]
		var sev = log_severity_map[logging.Syslog.Level]
		var p syslog.Priority = sev | fac
		var w1, err2 = syslog.New(p, "lenticularis")
		if err2 != nil {
			logger.critf("Opening a log file failed: err=(%v)", err2)
			panic("")
		}
		w = w1
		replacer = func(groups []string, a slog.Attr) slog.Attr {
			if a.Key == slog.TimeKey {
				return slog.Attr{}
			}
			return a
		}
	}
	var level, ok = log_level_name[logging.Syslog.Level]
	if !ok {
		level = slog.LevelInfo
	}
	fmt.Println("configure_logger(OPENFILE) w=", w)
	return slog.New(slog.NewTextHandler(w, &slog.HandlerOptions{
		AddSource:   source,
		Level:       level,
		ReplaceAttr: replacer,
	}))
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
		panic("")
	}
	mux_access_log_file = s
}

func open_log_for_reg(f string) {
	var s, err1 = os.OpenFile(f, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0600)
	if err1 != nil {
		slogger.Error("Reg() Opening a log file failed: err=(%v)", err1)
		panic("")
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

func log_mux_access_by_response(rspn *http.Response) {
	var rqst = rspn.Request
	log_access(mux_access_log_file, rqst, rspn.StatusCode, rspn.ContentLength, "-")
}

func log_mux_access_by_request(rqst *http.Request, code int, length int64, uid string) {
	log_access(mux_access_log_file, rqst, code, length, "-")
}

func log_reg_access_by_request(rqst *http.Request, code int, length int64, uid string) {
	log_access(reg_access_log_file, rqst, code, length, "-")
}

func log_access(f *os.File, rqst *http.Request, code int, length int64, uid string) {
	var layout = "02/Jan/2006:15:04:05 -0700"

	// l: RFC 1413 client identity by identd
	// u: user
	// rf: Referer

	var h = rqst.RemoteAddr
	var l = "-"
	var u = uid
	var t = time.Now().Format(layout)
	var r = fmt.Sprintf("%s %s %s", rqst.Method, rqst.URL, rqst.Proto)
	var s = fmt.Sprintf("%d", code)
	var b = fmt.Sprintf("%d", length)
	var rf = "-"
	var ua = rqst.Header.Get("User-Agent")

	var msg = fmt.Sprintf((`%s %s %s [%s] %q` + ` %s %s %q %q` + "\n"),
		h, l, u, t, r,
		s, b, rf, ua)
	var _, err1 = f.WriteString(msg)
	if err1 != nil {
		var key string
		switch f {
		case mux_access_log_file:
			key = "Mux()"
		case reg_access_log_file:
			key = "Reg()"
		default:
			panic("")
		}
		slogger.Error((key + " Wrinting to a log failed"), "file", f, "err", err1)
	}
}
