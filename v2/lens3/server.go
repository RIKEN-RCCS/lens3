// Copyright 2022-2026 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

// Service Runner.

// MEMO: The main in Golang will exit with status=2 on an unrecovered
// panic.
//
// Exit code to systemd services:
// status=1: generic or unspecified error (current practice)
// status=2: invalid or excess argument(s)
// status=3: unimplemented feature (for example, "reload")
// status=4: user had insufficient privilege
// status=5: program is not installed
// status=6: program is not configured
// status=7: program is not running
//
// https://refspecs.linuxbase.org/LSB_3.0.0/LSB-PDA/LSB-PDA/iniscrptact.html

package lens3

import (
	"flag"
	"fmt"
	"golang.org/x/sys/unix"
	"log/slog"
	"net"
	"net/http"
	_ "net/http/pprof"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"
)

const lens3_version string = "v2.2.1"
const registrar_api_version = "v1.2"
const configuration_file_version string = "v2.2"

var ch_quit_service chan<- vacuous = nil

func Run_lenticularis_mux() {
	//var logger_0 = slog.Default()
	slog.SetLogLoggerLevel(slog.LevelDebug)

	var flag_version = flag.Bool("v", false, "Print Lens3 version.")
	var flag_help = flag.Bool("h", false, "Print help.")
	var flag_conf = flag.String("c", "",
		"A file containing keyval-db connection information (REQUIRED).")
	var flag_pprof = flag.Int("pprof", 0,
		"A pprof port. It starts a pprof server.")
	flag.Parse()
	var args = flag.Args()

	if *flag_conf == "" {
		print_usage_and_exit()
	}
	if *flag_help {
		print_usage_and_exit()
	}
	if *flag_version {
		fmt.Fprintf(os.Stdout, "Lens3 %s %s\n",
			lens3_version, runtime.Version())
		os.Exit(0)
	}

	// Start pprof server.  Failure to start the server is fatal.

	if *flag_pprof != 0 {
		var port int = *flag_pprof
		go service_profiler(port, logger_0)
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
	tracing = 0xff

	var dbconf = read_db_conf(confpath, logger_0)
	if dbconf == nil {
		fmt.Fprintf(os.Stderr, "Reading db conf filed: %q\n", confpath)
		os.Exit(1)
	}

	// Note table's logger is temporarily set to the "early"-logger.

	var t = make_keyval_table(dbconf, false, logger_0)

	var chquit = make(chan vacuous)
	ch_quit_service = chquit

	var count int = 0
	var muxconf *mux_conf = nil
	var regconf *reg_conf = nil
	var muxlogger *slog.Logger = nil
	var reglogger *slog.Logger = nil

	// Value of "tracing" is prefered one from Reg than Mux.

	if services[0] != "" {
		var svc1 = services[0]
		count++
		muxconf = get_mux_conf(t, svc1)
		if muxconf == nil {
			fmt.Fprintf(os.Stderr, "No conf for %s found\n", svc1)
			os.Exit(1)
		}
		muxlogger = configure_logger(&muxconf.Logging, chquit)
		tracing = muxconf.Logging.Logger.Tracing
	}
	if services[1] != "" {
		var svc2 = services[1]
		count++
		regconf = get_reg_conf(t, svc2)
		if regconf == nil {
			fmt.Fprintf(os.Stderr, "No conf for %s found\n", svc2)
			os.Exit(1)
		}
		reglogger = configure_logger(&regconf.Logging, chquit)
		tracing = regconf.Logging.Logger.Tracing
	}

	// General logs are preferably to the registrar than the multiplexer.

	var mainlogger *slog.Logger
	if reglogger != nil {
		mainlogger = reglogger
	} else if muxlogger != nil {
		mainlogger = muxlogger
	} else {
		fmt.Fprintf(os.Stderr, "BAD-IMPL: No logger\n")
		os.Exit(1)
	}

	t.logger = mainlogger

	/*configure_logger(muxlogconf, chquit)*/
	handle_unix_signals(t, mainlogger)

	if reglogger != nil {
		reglogger.Info("Lenticularis-S3", "version", lens3_version,
			"golang.version", runtime.Version())
	}
	if muxlogger != nil {
		muxlogger.Info("Lenticularis-S3", "version", lens3_version,
			"golang.version", runtime.Version())
	}

	var wg sync.WaitGroup
	wg.Add(count)

	// Start Multiplexer.

	if services[0] != "" {
		assert_fatal(muxlogger != nil)
		var m = the_multiplexer
		m.logger = muxlogger
		var w = the_manager
		w.logger = muxlogger
		configure_multiplexer(m, w, t, chquit, muxconf)
		configure_manager(w, m, t, chquit, muxconf)
		defer w.backend_factory.clean_at_exit(m.logger)
		go start_multiplexer(m, &wg)
	}

	// Start Registrar.

	if services[1] != "" {
		assert_fatal(reglogger != nil)
		var z = the_registrar
		z.logger = reglogger
		configure_registrar(z, t, chquit, regconf)
		go start_registrar(z, &wg)
	}

	// Start memory stat dumper.

	var muxstats = muxconf.Logging.Stats
	var regstats = regconf.Logging.Stats

	var period time.Duration = 0
	if muxstats != nil && muxstats.Sample_period > 0 {
		period = muxstats.Sample_period.time_duration()
	} else if regstats != nil && regstats.Sample_period > 0 {
		period = regstats.Sample_period.time_duration()
	}
	if period != 0 {
		go dump_statistics_periodically(period, mainlogger)
	}

	wg.Wait()

	if reglogger != nil {
		reglogger.Info("Lenticularis-S3 service stops")
	}
	if muxlogger != nil {
		muxlogger.Info("Lenticularis-S3 service stops")
	}
}

func print_usage_and_exit() {
	var usage = `lenticularis-mux -c conf [mux/reg/mux+reg] [options]
  No arguments mean mux+reg. The mux part can be suffixed as mux:xxx
  to specify a different configuration.`

	fmt.Fprintf(os.Stderr, "Usage: %s\n", usage)
	flag.PrintDefaults()
	os.Exit(1)
}

func handle_unix_signals(t *keyval_table, logger *slog.Logger) {
	//logger.Debug("Set signal receivers", "pid", pid, "pgid", pgid)

	var ch_signal = make(chan os.Signal, 1)
	signal.Notify(ch_signal, unix.SIGINT, unix.SIGTERM, unix.SIGHUP)

	go func() {
	watchloop:
		for signal := range ch_signal {
			switch signal {
			case unix.SIGHUP, unix.SIGINT, unix.SIGTERM:
				logger.Error("Got signal; Stopping service", "signal", signal)
				break watchloop
			}
		}
		force_quit_service(logger)
	}()
}

// FORCE_QUIT_SERVICE tells services to quit via the ch_quit_service
// channel.  It lets the main thread exit, and thus, the remaining
// part of this function may not run to completion.
func force_quit_service(logger *slog.Logger) {
	var once sync.Once
	once.Do(func() {
		if ch_quit_service == nil {
			return
		}

		// Gracefully shutdown.

		close(ch_quit_service)
		ch_quit_service = nil

		// Backends had to be stopped, but force to kill them all.

		var pid = os.Getpid()
		var pgid, err1 = unix.Getpgid(0)
		if err1 != nil {
			// Ignore.
			pgid = pid
		}
		time.Sleep(100 * time.Millisecond)
		logger.Debug("Killing by killpg", "pgid", pgid)
		unix.Kill(-pgid, unix.SIGTERM)

		// When the main thread fails to exit, force to call os.Exit().

		time.Sleep(5000 * time.Millisecond)
		logger.Error("Force exit as the main thread not exits")
		os.Exit(1)
	})

	// Wait forever.
	//<-make(chan vacuous)
}

// SERVICE_PROFILER starts the http server for "go tool pprof".  Note
// importing "net/http/pprof" initializes profiler in DefaultServeMux.
// The logger is the "early"-logger which logs to stdout.
func service_profiler(port int, logger *slog.Logger) {
	var ep = net.JoinHostPort("", strconv.Itoa(port))
	var router = http.DefaultServeMux
	logger.Info("Enabling PPROF", "port", port)
	var err1 = http.ListenAndServe(ep, router)
	logger.Error("http.ListenAndServe for PPROF failed", "error", err1)
	print_usage_and_exit()
}
