/* Small functions. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand/v2"
	"net"
	"os"
	"os/exec"
	"reflect"
	"regexp"
	"runtime"
	"runtime/debug"
	"slices"
	"sort"
	"strconv"
	"strings"
	"time"
)

type vacuous = struct{}

// ITE is if-then-else.
func ITE[T any](c bool, e1 T, e2 T) T {
	if c {
		return e1
	} else {
		return e2
	}
}

func assert_fatal(c bool) {
	if !c {
		panic(nil)
	}
}

// PROXY_EXC is a panic argument to escape the service to toplevel
// where recover() does handle this.  Usage: raise(&proxy_exc{auth,
// code, and "message"}), where auth is an access-key or "-".
type proxy_exc struct {
	auth    string
	code    int
	message [][2]string
}

func (e *proxy_exc) Error() string {
	return fmt.Sprintf("%#v", e)
}

func handle() any {
	return recover()
}

func raise(e error) {
	panic(e)
}

// STRING_SORT sorts strings non-destructively.  It currently uses
// sort.Strings().  It will use slices.Sort in Go-1.22 and later.
func string_sort(s []string) []string {
	var x = make([]string, len(s))
	copy(x, s)
	sort.Strings(x)
	return x
}

// STRING_SET_EQUAL compares two arrays as sets, where the 2nd array
// should be sorted in advance.
func string_set_equal(s1 []string, s2 []string) bool {
	return reflect.DeepEqual(string_sort(s1), s2)
}

// STRING_SEARCH finds a string in sorted strings.
func string_search(s string, v []string) bool {
	var i = sort.SearchStrings(v, s)
	return i < len(v) && v[i] == s
}

const access_key_length = 20
const secret_key_length = 48

const ascii_letters_lc = "abcdefghijklmnopqrstuvwxyz"
const ascii_letters_uc = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
const ascii_digits = "0123456789"

func random_string(n int) string {
	const astr = (ascii_letters_lc + ascii_letters_uc)
	const bstr = (ascii_digits + ascii_letters_lc + ascii_letters_uc)
	const alen = len(astr)
	const blen = len(bstr)
	var s = make([]byte, n, n)
	s[0] = astr[rand.IntN(alen)]
	for i := 1; i < n; i++ {
		s[i] = bstr[rand.IntN(blen)]
	}
	return string(s)
}

func generate_access_key() string {
	return random_string(access_key_length)
}

func generate_secret_key() string {
	return random_string(secret_key_length)
}

func generate_random_key() string {
	var v1 = strconv.FormatUint(rand.Uint64(), 16)
	var v2 = "0000000000000000" + v1
	return v2[len(v2)-16:]
}

var access_key_naming_good_re = regexp.MustCompile(`^[a-zA-Z][a-zA-Z0-9]*$`)

func check_access_key_naming(s string) bool {
	return (len(s) == access_key_length &&
		access_key_naming_good_re.MatchString(s))
}

var claim_name_good_re = regexp.MustCompile(`^[-_a-zA-Z0-9.:@%]{0,256}$`)

func check_claim_name(s string) bool {
	return claim_name_good_re.MatchString(s)
}

func init() {
}

// get_function_name returns a printable name of a function.
//
//	var n = get_function_name(cmd.Cancel)
//	fmt.Println("cmd.Cancel=", n)
//	"cmd.Cancel= os/exec.CommandContext.func1"
func get_function_name(f any) string {
	return runtime.FuncForPC(reflect.ValueOf(f).Pointer()).Name()
}

func dump_threads() {
	var buf = make([]byte, (64 * 1024))
	var len = runtime.Stack(buf, true)
	fmt.Println("runtime.Stack()")
	fmt.Printf("%s", buf[:len])
}

// STRINGS_READER is strings.Reader but for multiple strings.  It
// skips empty strings.  It implements an io.Reader interface.
type strings_reader struct {
	ss       []string
	pos, ind int
}

func (r *strings_reader) Read(b []byte) (n int, err error) {
	for r.pos < len(r.ss) && len(r.ss[r.pos]) == 0 {
		r.pos++
	}
	if r.pos == len(r.ss) {
		return 0, io.EOF
	}
	n = copy(b, r.ss[r.pos][r.ind:])
	r.ind += n
	if r.ind == len(r.ss[r.pos]) {
		r.ind = 0
		r.pos++
	}
	return n, nil
}

// DECODE_JSON reads records from a concatenation of strings, and
// returns as many as possible.  A decoder error just stops decoding.
// It returns false in the secondon a decoder error.
func decode_json(ss []string) ([]map[string]any, bool) {
	var r = &strings_reader{ss, 0, 0}
	var dec = json.NewDecoder(r)

	var mm []map[string]any
	for dec.More() {
		var m map[string]any
		var err1 = dec.Decode(&m)
		if err1 != nil {
			return mm, false
		}
		// fmt.Printf("json.Decode()=%v\n", m)
		mm = append(mm, m)
	}
	return mm, true
}

// GET_STRING returns a string field at the key in the map.  It
// returns "", if a field is missing or non-string.
func get_string(m map[string]any, keys ...string) string {
	var v any
	v = m
	for _, key := range keys {
		switch x1 := v.(type) {
		case map[string]any:
			var x2, ok1 = x1[key]
			if !ok1 {
				return ""
			}
			v = x2
		default:
			return ""
		}
	}
	switch x3 := v.(type) {
	case string:
		return x3
	default:
		return ""
	}
}

func get_string1(m map[string]any, key string) string {
	var m1, ok1 = m[key]
	if !ok1 {
		return ""
	}
	var m2, ok2 = m1.(string)
	if !ok2 {
		return ""
	}
	return m2
}

// MINIMAL_ENVIRON returns a copy of environment variables that is
// minimal to run services.
func minimal_environ() []string {
	var envs = []string(os.Environ())
	var keys = string_sort([]string{
		"HOME",
		"LANG",
		"LC_CTYPE",
		"LOGNAME",
		"PATH",
		"SHELL",
		"USER",
		//"USERNAME",
		"LENS3_CONF",
		"LENS3_MUX_NAME",
	})
	var filtered []string
	for _, e := range envs {
		var i = strings.IndexByte(e, '=')
		if i != -1 {
			var k = e[:i]
			if string_search(k, keys) {
				filtered = append(filtered, e)
			}
		}
	}
	return filtered
}

func convert_hosts_to_addrs(hosts []string) []net.IP {
	var addrs []net.IP
	for _, h := range hosts {
		var ips, err1 = net.LookupIP(h)
		if err1 != nil {
			slogger.Warn("net/LookupIP() fails", "host", h, "err", err1)
			continue
		}
		addrs = append(addrs, ips...)
	}
	return addrs
}

// MAKE_TYPICAL_IP_ADDRESS makes IP address strings comparable.  It
// drops the hex part.  (Returned strings do not conform RFC-5952).
func make_typical_ip_address__(ip string) string {
	if strings.HasPrefix(ip, "::ffff:") {
		return ip[7:]
	} else {
		return ip
	}
}

var bucket_naming_good_re = regexp.MustCompile(`^[a-z0-9-]{3,63}$`)
var bucket_naming_forbidden_re = regexp.MustCompile(
	`^[0-9.]*$` +
		`|^.*-$` +
		`|^xn--.*$` +
		`|^.*-s3alias$` +
		`|^.*--ol-s3$` +
		`|^aws$` +
		`|^amazon$` +
		`|^goog.*$` +
		`|^g00g.*$` +
		`|^minio$`)

// CHECK_BUCKET_NAMING checks bucket naming restrictions.  Names are
// 3-63 characters in all lowercase, but exclude all digits.  Lens3
// forbits any DOTS, "aws", "amazon", "goog*", "g00g*", and "minio".
//
// * Bucket naming rules:
//   - https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
//
// * Bucket naming guidelines
//   - https://cloud.google.com/storage/docs/naming-buckets
func check_bucket_naming(name string) bool {
	return (len(name) >= 3 && len(name) <= 63 &&
		bucket_naming_good_re.MatchString(name) &&
		!bucket_naming_forbidden_re.MatchString(name))
}

var pool_naming_good_re = regexp.MustCompile(`^[a-h0-9]{16}$`)

func check_pool_naming(name string) bool {
	return pool_naming_good_re.MatchString(name)
}

var user_naming_good_re = regexp.MustCompile(`^[a-z_][-a-z0-9_.]{0,31}$`)

func check_user_naming(name string) bool {
	return user_naming_good_re.MatchString(name)
}

var claim_string_good_re = regexp.MustCompile(`^[-_a-zA-Z0-9.:@%]{0,256}$`)

func check_claim_string(claim string) bool {
	return claim_string_good_re.MatchString(claim)
}

// EXECUTE_COMMAND runs a controlling command of the backend.  It
// returns a message from stdout+stderr and an error.  Note that a
// timeout kills the process by SIGKILL.  MEMO: Timeout of context
// returns "context.deadlineExceededError".
func execute_command(synopsis string, argv []string, environ []string, timeout time.Duration, prefix string, verbose bool) (string, string, error) {
	//var timeout = (time.Duration(timeout_ms) * time.Millisecond)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	var stdoutb, stderrb bytes.Buffer
	cmd.Stdin = nil
	cmd.Stdout = &stdoutb
	cmd.Stderr = &stderrb
	cmd.Env = environ
	var err1 = cmd.Run()
	//fmt.Println("cmd.Run()=", err1)
	var wstatus = cmd.ProcessState.ExitCode()
	var stdouts = strings.TrimSpace(stdoutb.String())
	var stderrs = strings.TrimSpace(stderrb.String())
	switch err2 := err1.(type) {
	case nil:
		// OK.
		if verbose {
			slogger.Debug(prefix+": Command done",
				"cmd", argv, "exit", wstatus,
				"stdout", stdouts, "stderr", stderrs)
		}
	case *exec.ExitError:
		// Not successful.
		if wstatus == -1 {
			slogger.Error(prefix+": Command signaled/unfinished",
				"cmd", argv, "err", err2,
				"stdout", stdouts, "stderr", stderrs)
			return "", "", err2
		} else {
			slogger.Error(prefix+": Command failed",
				"cmd", argv, "err", err2,
				"stdout", stdouts, "stderr", stderrs)
			return "", "", err2
		}
	default:
		// Error.
		slogger.Error(prefix+": Command failed to run",
			"cmd", argv, "err", err1,
			"stdout", stdouts, "stderr", stderrs)
		return "", "", err1
	}
	return stdouts, stderrs, nil
}

// CHECK_FIELDS_FILLED checks if all fields of a structure is
// non-zero, recursively.  It assumes no pointers.
func check_fields_filled(data any) bool {
	var v = reflect.ValueOf(data)
	return check_fields_filled_loop(v)
}

func check_fields_filled_loop(v reflect.Value) bool {
	if v.IsZero() {
		return false
	}
	switch v.Kind() {
	case reflect.Pointer:
		return true
	case reflect.Array:
		fallthrough
	case reflect.Map:
		fallthrough
	case reflect.Slice:
		for i := 0; i < v.Len(); i++ {
			var f = v.Index(i)
			if !check_fields_filled(f) {
				return false
			}
		}
		return true
	case reflect.Struct:
		for i := 0; i < v.NumField(); i++ {
			var f = v.Field(i)
			if !check_fields_filled(f) {
				return false
			}
		}
		return true
	default:
		return true
	}
}

// CHECK_INT_IN_RANGES checks int v is in any of ranges, lb≤v≤ub for
// [lb,ub] (lower/upper-bounds inclusive).
func check_int_in_ranges(pairs [][2]int, v int) bool {
	for _, lbub := range pairs {
		if lbub[0] <= v && v < lbub[1] {
			return true
		}
	}
	return false
}

// CHECK_STREAM_EOF checks is the input stream is empty.  It actually
// reads the stream.  It returns an error if garbage is in the stream.
// Note that checking by reading zero bytes ([]byte{}) is not
// accurate.  ACCEPT_JSON_EMPTY=true allows UI's bug in sending "{}"
// as an empty body.
func check_stream_eof(is io.Reader, accept_json_empty bool) error {
	var size = 512
	var b = make([]byte, size)
	var n, err1 = is.Read(b)
	if n == 0 && err1 == io.EOF {
		return nil
	}
	if err1 != nil && err1 != io.EOF {
		return err1
	}
	var s = strings.TrimSpace(string(b[:n]))
	if accept_json_empty && n < size && (s == "" || s == "{}") {
		return nil
	}
	var err2 = fmt.Errorf("Garbage in request: %q", s)
	return err2
}

func check_frontend_proxy_trusted(trusted []net.IP, peer string) bool {
	if peer == "" {
		slogger.Warn("Bad frontend proxy", "peer", peer)
		return false
	}
	var host, _, err1 = net.SplitHostPort(peer)
	if err1 != nil {
		slogger.Warn("Bad frontend proxy", "peer", peer, "err", err1)
		return false
	}
	var ips, err2 = net.LookupIP(host)
	if err2 != nil {
		slogger.Warn("net/LookupIP() failed", "peer", host, "err", err2)
		return false
	}
	for _, ip := range ips {
		if slices.IndexFunc(trusted, ip.Equal) != -1 {
			return true
		}
	}
	return false
}

// FIND_ONE searches in the list for one that satisfies f.  It returns
// a boolean and the first satisfying one if it exists.
func find_one[T any](mm []T, f func(T) bool) (bool, T) {
	for _, m := range mm {
		if f(m) {
			return true, m
		}
	}
	return false, *new(T)
}

func delay_sleep(ms time_in_sec) {
	time.Sleep(time.Duration(ms) * time.Millisecond)
}

func dump_statistics_periodically(period time.Duration) {
	var ch = make(chan time.Time)
	go tick_periodically(ch, period)
	for {
		select {
		case <-ch:
			dump_statistics(false)
		}
	}
}

// TICK_PERIODICALLY ticks on clock to the channel.  A period can be
// time.Hour or 24*time.Hour.  It adds a ±0.5% jitter.
func tick_periodically(ch chan<- time.Time, period time.Duration) {
	var period1 = int64(period)
	for {
		var now = time.Now()
		var jitter = time.Duration(rand.Int64N(period1/100) - (period1 / 200))
		var next = now.Add(period + (period / 2)).Round(period).Add(jitter)
		time.Sleep(next.Sub(now))
		ch <- time.Now()
	}
}

func dump_statistics(verbose bool) {
	//runtime.MemProfile()
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	var ms = struct {
		HeapAlloc   uint64
		HeapSys     uint64
		HeapObjects uint64
		HeapInuse   uint64
		StackInuse  uint64
		OtherSys    uint64
		NumGC       uint32
		NumForcedGC uint32
	}{
		HeapAlloc:   m.HeapAlloc,
		HeapInuse:   m.HeapInuse,
		HeapSys:     m.HeapSys,
		StackInuse:  m.StackInuse,
		OtherSys:    m.OtherSys,
		HeapObjects: m.HeapObjects,
		NumGC:       m.NumGC,
		NumForcedGC: m.NumForcedGC,
	}
	slogger.Info("MemStats", "Summary", ms)
	if verbose {
		slogger.Info("MemStats", "MemStats", m)
	}
	if verbose {
		var g debug.GCStats
		debug.ReadGCStats(&g)
		slogger.Info("GCStats", "GCStats", g)
	}
}
