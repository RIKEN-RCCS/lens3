/* Small functions. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	// GOLANG VERSIONS: "slices" is from v1.22.  Note Golang is v1.21
	// in Linux Rocky8/9 as of 2023-04-01.

	//"context"
	"encoding/json"
	"errors"
	"fmt"
	//"github.com/go-redis/redis/v8"
	"io"
	"net"
	"os"
	//"log"
	//"log/syslog"
	"sort"
	//"time"
	//"slices"
	"math/rand/v2"
	"reflect"
	"regexp"
	"runtime"
	"strconv"
	"strings"
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

const (
	http_status_400_bad_request  int = 400
	http_status_401_unauthorized int = 401
	http_status_403_forbidden    int = 403
	http_status_404_not_found    int = 404

	http_status_500_internal_server_error int = 500
	http_status_503_service_unavailable   int = 503

	http_status_601_unanalyzable int = 601
)

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

// FATAL_ERROR is a panic argument to stop the service as recover()
// does not handle this.  Usage:panic(&fatal_error{"message string"}).
type fatal_error struct {
	m string
}

func (e *fatal_error) Error() string {
	return "fatal_error:" + e.m
}

type termination_exc struct {
	m string
}

type reg_error_exc struct {
	m string
}

type proxy_exc struct {
	code int
	m    string
}

func (e *termination_exc) Error() string {
	return "termination_exc:" + e.m
}

func (e *reg_error_exc) Error() string {
	return "reg_error_exc:" + e.m
}

func (e *proxy_exc) Error() string {
	return "proxy_exc:" + e.m
}

func proxy_error(code int, s string) error {
	return &proxy_exc{
		code: code,
		m:    s,
	}
}

func handle() any {
	return recover()
}

func raise(e error) {
	panic(e)
}

func termination(m string) *termination_exc {
	return &termination_exc{m}
}

func reg_error(code int, _ string) error {
	return &reg_error_exc{fmt.Sprintf("reg_error code=%d", code)}
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

	var mm []map[string]interface{}
	for dec.More() {
		var m map[string]interface{}
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

// MAKE_TYPICAL_IP_ADDRESS makes IP address strings comparable.  It
// drops the hex part.  (Returned strings do not conform RFC-5952).
func make_typical_ip_address(ip string) string {
	if strings.HasPrefix(ip, "::ffff:") {
		return ip[7:]
	} else {
		return ip
	}
}

// GET_IP_ADDRESSES returns a list of addresses for the host name,
// which are formatted for equality comparison.
func get_ip_addresses(hostname string) []string {
	var ips1, err1 = net.LookupHost(hostname)
	assert_fatal(err1 == nil)
	var ips2 []string
	for _, ip := range ips1 {
		ips2 = append(ips2, make_typical_ip_address(ip))
	}
	return string_sort(ips2)
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
func check_int_in_ranges(v int, pairs [][2]int) bool {
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
