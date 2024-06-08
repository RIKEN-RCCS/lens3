/* Service Runner. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"flag"
	"fmt"
	//"context"
	//"io"
	//"log"
	"os"
	"os/signal"
	//"net"
	//"maps"
	//"net/http"
	//"net/http/httputil"
	//"net/url"
	//"os"
	//"strconv"
	//"strings"
	"golang.org/x/sys/unix"
	//"syscall"
	"strings"
	"time"
	//"runtime"
)

const lens3_version string = "v2.1"

func Run_lenticularis_mux() {
	var flag_version = flag.Bool("v", false, "Lens3 version.")
	var flag_help = flag.Bool("h", false, "Print help.")
	var flag_conf = flag.String("c", "",
		"A file containing keyval-db connection information (REQUIRED).")
	flag.Parse()
	var args = flag.Args()

	if *flag_conf == "" {
		print_lenticularis_mux_usage()
		os.Exit(0)
	}

	var services []string
	switch len(args) {
	default:
		print_lenticularis_mux_usage()
		os.Exit(0)
	case 0:
		// No argument mean "reg+mux".
		services = []string{"reg", "mux"}
	case 1:
		// Check "reg", "mux", and "reg+mux" cases.
		var regmux = strings.Split(args[0], "+")
		switch len(regmux) {
		default:
			print_lenticularis_mux_usage()
			os.Exit(0)
		case 1, 2:
			var regpart = regmux[0]
			var muxpart = regmux[(len(regmux) - 1)]
			if regpart == "reg" {
				services = append(services, regpart)
			}
			if strings.HasPrefix(muxpart, "mux") {
				var muxopt = strings.Split(muxpart, ":")
				switch len(muxopt) {
				case 1, 2:
					if muxopt[0] == "mux" {
						services = append(services, muxpart)
					}
				}
			}
			if len(services) != len(regmux) {
				print_lenticularis_mux_usage()
				os.Exit(0)
			}
		}
	}
	if *flag_help {
		print_lenticularis_mux_usage()
		os.Exit(0)
	}
	if *flag_version {
		fmt.Println("Lens3", lens3_version)
		os.Exit(0)
	}

	//fmt.Println("services=", services)
	start_lenticularis_service(*flag_conf, services)
}

func start_lenticularis_service(confpath string, services []string) {
	var dbconf = read_db_conf(confpath)
	var t = make_table(dbconf)

	var ch_quit_service = make(chan vacuous)
	handle_unix_signals(t, ch_quit_service)

	for i, service := range services {
		var run_on_main_thread = (i == len(services)-1)
		if service == "reg" {
			var regconf = get_reg_conf(t, service)
			var z = &the_registrar
			configure_registrar(z, t, ch_quit_service, regconf)
			if run_on_main_thread {
				start_registrar(z)
			} else {
				go start_registrar(z)
			}
		}
		if strings.HasPrefix(service, "mux") {
			var muxconf = get_mux_conf(t, service)
			var m = &the_multiplexer
			var w = &the_manager
			configure_multiplexer(m, w, t, ch_quit_service, muxconf)
			configure_manager(w, m, t, ch_quit_service, muxconf)
			defer w.factory.clean_at_exit()
			if run_on_main_thread {
				start_multiplexer(m)
			} else {
				go start_multiplexer(m)
			}
		}
	}
}

func print_lenticularis_mux_usage() {
	fmt.Fprintf(os.Stderr,
		"Usage: lenticularis-mux -c conf [reg/mux/reg+mux]\n"+
			"  where the mux part can be mux:xxx"+
			" to specify a different configuration.\n"+
			"  No reg nor mux means reg+mux\n")
	flag.PrintDefaults()
}

func handle_unix_signals(t *keyval_table, ch_quit_service chan vacuous) {
	var ch_sig = make(chan os.Signal, 1)

	var pid = os.Getpid()
	var pgid, err1 = unix.Getpgid(0)
	if err1 != nil {
		// Ignore.
	}
	fmt.Printf("Set signal receivers; pid=%d pgid=%d\n", pid, pgid)

	signal.Notify(ch_sig, unix.SIGINT, unix.SIGTERM, unix.SIGHUP)

	go func() {
	watchloop:
		for signal := range ch_sig {
			switch signal {
			case unix.SIGINT:
				fmt.Println("SIGINT")
				break watchloop
			case unix.SIGTERM:
				fmt.Println("SIGTERM")
				break watchloop
			case unix.SIGHUP:
				fmt.Println("SIGHUP")
				break watchloop
			}
		}
		// (Graceful killing here).
		close(ch_quit_service)
		time.Sleep(100 * time.Millisecond)
		fmt.Printf("killing by pgid=%d\n", pgid)
		unix.Kill(-pgid, unix.SIGTERM)
		time.Sleep(100 * time.Millisecond)
		os.Exit(0)
	}()
}
