/* Check Mux. */

package lens3

import (
	//"bufio"
	//"bytes"
	//"context"
	//"encoding/json"
	"fmt"
	//"log"
	//"net/http"
	"time"
	//"reflect"
	//"io"
	//"os"
	//"os/exec"
	//"os/signal"
	//"os/user"
	//"strings"
	//"syscall"
	//"testing"
)

func run_service() {
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

	//run_dummy_reg_client_for_mux_client()
	go run_dummy_mux_client(m)

	start_multiplexer(m)
}

func run_dummy_mux_client(m *multiplexer) {
	time.Sleep(1 * time.Second)

	//var g = start_backend_for_test(w)
	//var proc = g.get_super_part()
	//var pool = proc.Pool

	//var desc = &proc.backend_record
	fmt.Println("proc.backend_record=")
	//print_in_json(desc)
	//set_backend(w.table, proc.Pool, desc)
	//var proc = g.get_super_part()
	//m.pool[proc.pool] = g
	//time.Sleep(30 * time.Second)
	//start_dummy_proxy(m)

	fmt.Println("MUX CLIENT RUN...")

	var pool = "b26089c45be8635d"
	var prop = get_pool(m.table, pool)
	var secret = get_secret(m.table, prop.Probe_key)
	var err1 = probe_access_mux(m, m.mux_ep, secret)
	fmt.Println("err=", err1)

	time.Sleep(15 * time.Second)
}
