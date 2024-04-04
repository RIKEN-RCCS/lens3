/* Small functions. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// GOLANG VERSION: Lens3 uses Golang-1.21 in Linux Rocky8, which lacks
// "slices", as of 2023-04-01

import (
	//"context"
	//"encoding/json"
	//"fmt"
	//"github.com/go-redis/redis/v8"
	//"log"
	"sort"
	//"time"
	//"slices" >=1.22
	"reflect"
)

// STRING_SORT sorts strings non-destructively.  It currently uses
// sort.Strings().  It will use slices.Sort in Go-1.22 and later.
func string_sort(s []string) []string {
	var x []string
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
