/* Small functions. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand/v2"
	"net"
	"os"
	"reflect"
	"regexp"
	"runtime"
	"runtime/debug"
	"slices"
	"sort"
	"strconv"
	"strings"
	"time"
	//"context"
	//"github.com/go-redis/redis/v8"
	//"log"
	//"log/syslog"
	//"slices"
)

type vacuous = struct{}

// ITE if-then-else.
func ITE[T any](c bool, e1 T, e2 T) T {
	if c {
		return e1
	} else {
		return e2
	}
}

type Fatal struct {
	Err error
}

func (e Fatal) Error() string {
	return fmt.Sprintf("Fatal (%v)", e.Err)
}

func panic_non_nil(w any) {
	if w != nil {
		panic(w)
	}
}

func assert_fatal(c bool) {
	if !c {
		panic("assert fail")
	}
}

// ASSERT_NEVER just panics.
func assert_never(m string) {
	panic(m)
}

func panic_never() {
	panic("(interal)")
}

// FATAL_EXC is a panic argument to stop the service as recover()
// does not handle this.  Usage:panic(&fatal_exc{"message string"}).
type fatal_exc struct {
	m string
}

func (e *fatal_exc) Error() string {
	return fmt.Sprintf("%#v", e)
}

type proxy_exc struct {
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
			slogger.Warn("net.LookupIP() fails", "host", h, "err", err1)
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

var garbage_in_input_stream_error = errors.New("garbage_in_stream")

// CHECK_STREAM_EOF checks is the input stream is empty.  It returns
// nil on EOF.  IT READS ONE BYTE.
func check_stream_eof(is io.Reader) error {
	var _, err2 = is.Read([]byte{9})
	if err2 == io.EOF {
		return nil
	} else {
		return ITE(err2 != nil, err2, garbage_in_input_stream_error)
	}
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
		slogger.Warn("net.LookupIP(%s) failed", "peer", host, "err", err2)
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
			dump_statistics()
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

func dump_statistics() {
	//runtime.MemProfile()
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	var g debug.GCStats
	debug.ReadGCStats(&g)
	slogger.Info("Stats", "MemStats", m)
	slogger.Info("Stats", "GCStats", g)
}
