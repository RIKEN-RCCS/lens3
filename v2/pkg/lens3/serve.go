/* Service Runner. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"fmt"
	//"flag"
	//"context"
	//"io"
	//"log"
	//"os"
	//"net"
	//"maps"
	//"net/http"
	//"net/http/httputil"
	//"net/url"
	//"os"
	//"strconv"
	//"strings"
	"time"
	//"runtime"
)

const lens3_version string = "v2.1"

func start_service_for_test() {
	var dbconf = read_db_conf("conf.json")
	var t = make_table(dbconf)
	var muxconf = get_mux_conf(t, "mux")
	var regconf = get_reg_conf(t, "reg")

	var m = &the_multiplexer
	var w = &the_manager
	configure_multiplexer(m, w, t, muxconf)
	configure_manager(w, m, t, muxconf)
	go start_manager(w)

	var z = &the_registrar
	configure_registrar(z, t, regconf)
	go start_registrar(z)

	time.Sleep(5 * time.Second)

	if false {
		var g = start_backend_for_test(w)
		var proc = g.get_super_part()
		//var pool = proc.Pool

		var desc = &proc.backend_record
		fmt.Println("set_backend_process(2) ep=", proc.Backend_ep)
		fmt.Println("proc.backend_record=")
		print_in_json(desc)
		set_backend_process(w.table, proc.Pool, desc)
		//var proc = g.get_super_part()
		//m.pool[proc.pool] = g
		//time.Sleep(30 * time.Second)
		//start_dummy_proxy(m)
	}

	start_multiplexer(m)
}
