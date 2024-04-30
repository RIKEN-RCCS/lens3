/* Small functions. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// GOLANG VERSIONS: "slices" is from v1.22.  Note Golang is v1.21 in
// Linux Rocky8/9 as of 2023-04-01.

import (
	//"context"
	//"encoding/json"
	//"fmt"
	//"github.com/go-redis/redis/v8"
	"log/slog"
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

var logger = slog.Default()

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
