/* Small functions. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// GOLANG VERSIONS: "slices" is from v1.22.  Note Golang is v1.21 in
// Linux Rocky8/9 as of 2023-04-01.

import (
	//"context"
	"encoding/json"
	"fmt"
	//"github.com/go-redis/redis/v8"
	"io"
	//"log"
	//"log/syslog"
	"sort"
	"time"
	//"slices"
	"math/rand"
	"reflect"
	"runtime"
)

// FATAL_ERROR is a panic argument to stop the service as recover()
// does not handle this.  Usage:panic(&fatal_error{"message string"}).
type fatal_error struct {
	msg string
}

func raise(m any) {
	panic(m)
}

type termination_exc struct {
	s string
}

func termination(s string) *termination_exc {
	return &termination_exc{s}
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

func assert_fatal(c bool) {
	if !c {
		panic("assert fail")
	}
}

// var logger = slog.Default()
// var logger = syslog.New()
var logger = logger_default()

const access_key_length = 20
const secret_key_length = 48

const ascii_letters_lc = "abcdefghijklmnopqrstuvwxyz"
const ascii_letters_uc = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
const ascii_digits = "0123456789"

func random_str(n int) string {
	const astr = (ascii_letters_lc + ascii_letters_uc)
	const bstr = (ascii_digits + ascii_letters_lc + ascii_letters_uc)
	const alen = len(astr)
	const blen = len(bstr)
	var s = make([]byte, 0, n)
	s[0] = astr[rand.Intn(alen)]
	for i := 1; i < n; i++ {
		s[i] = bstr[rand.Intn(blen)]
	}
	return string(s)
}

func generate_access_key() string {
	return random_str(access_key_length)
}

func generate_secret_key() string {
	return random_str(secret_key_length)
}

func init() {
	rand.Seed(time.Now().UnixNano())
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
// returns as many as possible.  Decoder error just stops decoding.
func decode_json(ss []string) []map[string]interface{} {
	var r = &strings_reader{ss, 0, 0}
	var dec = json.NewDecoder(r)

	var mm []map[string]interface{}
	for dec.More() {
		var m map[string]interface{}
		var err1 = dec.Decode(&m)
		if err1 != nil {
			break
		}
		// fmt.Printf("json.Decode()=%v\n", m)
		mm = append(mm, m)
	}
	return mm
}
