/* Service Runner. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"flag"
	"fmt"
	"golang.org/x/sys/unix"
	"net"
	"net/http"
	"net/http/pprof"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"
	//"context"
	//"io"
	//"log"
	//"maps"
	//"net/url"
	//"os"
	//"runtime"
	//"strings"
	//"syscall"
)

const lens3_version string = "v2.1.1"

func Run_lenticularis_mux() {
	var flag_version = flag.Bool("v", false, "Lens3 version.")
	var flag_help = flag.Bool("h", false, "Print help.")
	var flag_conf = flag.String("c", "",
		"A file containing keyval-db connection information (REQUIRED).")
	var flag_pprof = flag.Int("pprof", 0, "A pprof port.")
	flag.Parse()
	var args = flag.Args()

	if *flag_conf == "" {
		print_usage_and_exit()
	}
	if *flag_help {
		print_usage_and_exit()
	}
	if *flag_version {
		fmt.Println("Lens3", lens3_version)
		os.Exit(0)
	}
	if *flag_pprof != 0 {
		var port int = *flag_pprof
		go start_pprof_service(port)
	}

	var services = [2]string{"", ""}
	switch len(args) {
	default:
		print_usage_and_exit()
	case 0:
		// No arguments mean "reg+mux".
		services[0] = "mux"
		services[1] = "reg"
	case 1:
		// Check "mux", "reg", and "mux+reg" cases.
		var mux_or_reg = strings.Split(args[0], "+")
		switch len(mux_or_reg) {
		default:
			print_usage_and_exit()
		case 1, 2:
			for _, muxreg := range mux_or_reg {
				var opt = strings.Split(muxreg, ":")
				if (len(opt) == 1 || len(opt) == 2) && opt[0] == "mux" {
					services[0] = muxreg
				} else if (len(opt) == 1) && opt[0] == "reg" {
					services[1] = muxreg
				} else {
					print_usage_and_exit()
				}
			}
		}
	}
	if services[0] == "" && services[1] == "" {
		print_usage_and_exit()
	}

	//fmt.Println("services=", services)
	start_lenticularis_service(*flag_conf, services)
}

func start_lenticularis_service(confpath string, services [2]string) {
	var dbconf = read_db_conf(confpath)
	if dbconf == nil {
		fmt.Fprintf(os.Stderr, "Reading db conf filed: %q\n", confpath)
		os.Exit(1)
	}
	var t = make_keyval_table(dbconf)

	var count int = 0
	var muxconf *mux_conf = nil
	var regconf *reg_conf = nil
	var logconf *logging_conf = nil
	if services[0] != "" {
		var svc1 = services[0]
		count++
		muxconf = get_mux_conf(t, svc1)
		if muxconf == nil {
			fmt.Fprintf(os.Stderr, "No conf for %s found\n", svc1)
			os.Exit(1)
		}
		logconf = muxconf.Logging
	}
	if services[1] != "" {
		var svc2 = services[1]
		count++
		regconf = get_reg_conf(t, svc2)
		if regconf == nil {
			fmt.Fprintf(os.Stderr, "No conf for %s found\n", svc2)
			os.Exit(1)
		}
		if logconf == nil {
			logconf = regconf.Logging
		}
	}

	var ch_quit_service = make(chan vacuous)
	configure_logger(logconf, ch_quit_service)
	handle_unix_signals(t, ch_quit_service)

	slogger.Info("Lenticularis-S3", "version", lens3_version,
		"golang.version", runtime.Version())

	var wg sync.WaitGroup
	wg.Add(count)

	// Start Multiplexer.

	if services[0] != "" {
		var m = the_multiplexer
		var w = the_manager
		configure_multiplexer(m, w, t, ch_quit_service, muxconf)
		configure_manager(w, m, t, ch_quit_service, muxconf)
		defer w.factory.clean_at_exit()
		go start_multiplexer(m, &wg)
	}

	// Start Registrar.

	if services[1] != "" {
		var z = the_registrar
		configure_registrar(z, t, ch_quit_service, regconf)
		go start_registrar(z, &wg)
	}

	if logconf.Stats.Period > 0 {
		var period = (time.Duration(logconf.Stats.Period) * time.Second)
		go dump_statistics_periodically(period)
	}

	wg.Wait()
}

func print_usage_and_exit() {
	var usage = `Usage: lenticularis-mux -c conf [mux/reg/mux+reg]
  where the mux part can be mux:xxx to specify a different
  configuration.  No arguments mean mux+reg.`

	fmt.Fprintf(os.Stderr, usage)
	flag.PrintDefaults()
	os.Exit(1)
}

func handle_unix_signals(t *keyval_table, ch_quit_service chan vacuous) {
	var pid = os.Getpid()
	var pgid, err1 = unix.Getpgid(0)
	if err1 != nil {
		// Ignore.
		pgid = pid
	}
	//slogger.Debug("Set signal receivers", "pid", pid, "pgid", pgid)

	var ch_signal = make(chan os.Signal, 1)
	signal.Notify(ch_signal, unix.SIGINT, unix.SIGTERM, unix.SIGHUP)

	go func() {
	watchloop:
		for signal := range ch_signal {
			switch signal {
			case unix.SIGHUP, unix.SIGINT, unix.SIGTERM:
				slogger.Error("Got signal; Stopping service", "signal", signal)
				break watchloop
			}
		}
		// Graceful killing first.
		close(ch_quit_service)
		time.Sleep(100 * time.Millisecond)
		slogger.Debug("Killing by killpg", "pgid", pgid)
		unix.Kill(-pgid, unix.SIGTERM)
		time.Sleep(100 * time.Millisecond)
		os.Exit(1)
	}()
}

func start_pprof_service(port int) {
	var ep = net.JoinHostPort("", strconv.Itoa(port))
	var pprofrouter = http.NewServeMux()
	pprofrouter.HandleFunc("/debug/pprof/", pprof.Index)
	pprofrouter.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
	pprofrouter.HandleFunc("/debug/pprof/profile", pprof.Profile)
	pprofrouter.HandleFunc("/debug/pprof/symbol", pprof.Symbol)
	pprofrouter.HandleFunc("/debug/pprof/trace", pprof.Trace)
	var err1 = http.ListenAndServe(ep, pprofrouter)
	fmt.Fprintf(os.Stderr, "Starting pprof failed: err=%v\n", err1)
	print_usage_and_exit()
}
