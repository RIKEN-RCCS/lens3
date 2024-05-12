/* A conf file reader. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Conf files are read and checked against structures.  It accepts
// extra fields.

import (
	"bytes"
	"encoding/json"
	"fmt"
	//"io"
	"log"
	"os"
	"reflect"
	"slices"
	"time"
)

// DB_CONF is a pair of an endpoint and password to access a
// keyval-DB, and it is usually stored in a file in "etc".
type Db_conf struct {
	Ep       string
	Password string
}

// LENS3_CONF is a union of Mux_conf|Api_conf.
type lens3_conf interface{ lens3_conf_union() }

func (Mux_conf) lens3_conf_union() {}
func (Api_conf) lens3_conf_union() {}

// Mux_conf is a configuration of Mux.  mux_node_name and log_file are
// optional.
type Mux_conf struct {
	Conf_header
	//Gunicorn      Gunicorn_conf
	Multiplexer Multiplexer_conf `json:"multiplexer"`
	Manager     Manager_conf     `json:"manager"`
	Minio       Minio_conf       `json:"minio"`
	Log_file    string           `json:"log_file"`
	Log_syslog  Syslog_conf      `json:"log_syslog"`
}

// Api_conf is a configuration of Api.  log_file is optional.
type Api_conf struct {
	Conf_header
	//Gunicorn   Gunicorn_conf
	Registrar  Registrar_conf `json:"registrar"`
	UI         UI_conf        `json:"ui"`
	Minio      Minio_conf     `json:"minio"`
	Log_file   string         `json:"log_file"`
	Log_syslog Syslog_conf    `json:"log_syslog"`
}

type Conf_header struct {
	Subject       string `json:"subject"`
	Version       string `json:"version"`
	Aws_signature string `json:"aws_signature"`
}

type Multiplexer_conf struct {
	Port                    int           `json:"port"`
	Front_host              string        `json:"front_host"`
	Trusted_proxies         []string      `json:"trusted_proxies"`
	Mux_ep_update_interval  time.Duration `json:"mux_ep_update_interval"`
	Forwarding_timeout      time.Duration `json:"forwarding_timeout"`
	Probe_access_timeout    time.Duration `json:"probe_access_timeout"`
	Bad_response_delay      time.Duration `json:"bad_response_delay"`
	Busy_suspension_time    time.Duration `json:"busy_suspension_time"`
	Mux_node_name           string        `json:"mux_node_name"`
	Backend                 string        `json:"backend"`
	Backend_command_timeout time.Duration `json:"backend_command_timeout"`
	Mux_access_log_file     string        `json:"mux_access_log_file"`
}

// claim_uid_map is one of {"id", "email-name", "map"}.
type Registrar_conf struct {
	Port                    int           `json:"port"`
	Front_host              string        `json:"front_host"`
	Trusted_proxies         []string      `json:"trusted_proxies"`
	Base_path               string        `json:"base_path"`
	Claim_uid_map           string        `json:"claim_uid_map"`
	Probe_access_timeout    time.Duration `json:"probe_access_timeout"`
	Max_pool_expiry         time.Duration `json:"max_pool_expiry"`
	Csrf_secret_seed        string        `json:"csrf_secret_seed"`
	Backend                 string        `json:"backend"`
	Backend_command_timeout time.Duration `json:"backend_command_timeout"`
	Api_access_log_file     string        `json:"api_access_log_file"`
}

type Manager_conf struct {
	Sudo                     string        `json:"sudo"`
	Port_min                 int           `json:"port_min"`
	Port_max                 int           `json:"port_max"`
	Backend_awake_duration   time.Duration `json:"backend_awake_duration"`
	Backend_setup_at_start   bool          `json:"backend_setup_at_start"`
	Backend_start_timeout    time.Duration `json:"backend_start_timeout"`
	Backend_setup_timeout    time.Duration `json:"backend_setup_timeout"`
	Backend_stop_timeout     time.Duration `json:"backend_stop_timeout"`
	Backend_command_timeout  time.Duration `json:"backend_command_timeout"`
	Heartbeat_interval       time.Duration `json:"heartbeat_interval"`
	Heartbeat_miss_tolerance int           `json:"heartbeat_miss_tolerance"`
	Heartbeat_timeout        time.Duration `json:"heartbeat_timeout"`
}

type Minio_conf struct {
	Minio string `json:"minio"`
	Mc    string `json:"mc"`
}

type UI_conf struct {
	S3_url        string `json:"s3_url"`
	Footer_banner string `json:"footer_banner"`
}

type Syslog_conf struct {
	Facility string `json:"facility"`
	Priority string `json:"priority"`
}

var claim_conversions = []string{"id", "email-name", "map"}
var backend_list = []string{"minio", "rclone"}

const bad_message = "Bad json conf file."

// READ_DB_CONF reads a conf-file for the keyval table.
func read_db_conf(file string) Db_conf {
	file = "conf.json"
	var b1, err1 = os.ReadFile(file)
	if err1 != nil {
		log.Panicf("Reading a conf-file failed: file=%s, error=%v", file, err1)
	}
	var b2 = bytes.NewReader(b1)
	var d = json.NewDecoder(b2)
	d.DisallowUnknownFields()
	var conf Db_conf
	var err2 = d.Decode(&conf)
	if err2 != nil {
		log.Panic(err2)
	}
	if conf.Ep == "" || conf.Password == "" {
		log.Panic("conf.redis.ep or conf.redis.password missing")
	}
	check_db_entry(conf)
	return conf
}

// Read_conf reads a configuration file and checks a structure is
// properly filled.
func read_conf(filename string) lens3_conf {
	var json1, err1 = os.ReadFile(filename)
	if err1 != nil {
		panic(err1)
	}
	var conf1 = make(map[string]interface{})
	var err2 = json.Unmarshal(json1, &conf1)
	if err2 != nil {
		panic(err2)
	}

	var sub = conf1["subject"].(string)[:3]
	switch sub {
	case "mux":
		var muxconf Mux_conf
		var err3 = json.Unmarshal(json1, &muxconf)
		if err3 != nil {
			panic(fmt.Sprint("Bad json conf file:", err3))
		}
		//fmt.Println("MUX CONF is", muxconf)
		check_mux_conf(muxconf)
		return &muxconf
	case "api":
		var apiconf Api_conf
		var err4 = json.Unmarshal(json1, &apiconf)
		if err4 != nil {
			panic(fmt.Sprint("Bad json conf file:", err4))
		}
		//fmt.Println("API CONF is", apiconf)
		check_api_conf(apiconf)
		return &apiconf
	default:
		log.Panicf("Bad json conf file: Bad subject field (%s).", sub)
		return nil
	}
}

func check_mux_conf(conf Mux_conf) {
	check_multiplexer_entry(conf.Multiplexer)
	check_manager_entry(conf.Manager)
	switch conf.Multiplexer.Backend {
	case "minio":
		check_minio_entry(conf.Minio)
	}
	check_syslog_entry(conf.Log_syslog)
}

func check_api_conf(conf Api_conf) {
	check_registrar_entry(conf.Registrar)
	switch conf.Registrar.Backend {
	case "minio":
		check_minio_entry(conf.Minio)
	}
	check_ui_entry(conf.UI)
	check_syslog_entry(conf.Log_syslog)
}

func assert_slot(c bool) {
	if !c {
		panic(fmt.Errorf("Bad conf file."))
	}
}

func check_db_entry(e Db_conf) {
	if len(e.Ep) > 0 && len(e.Password) > 0 {
	} else {
		log.Panic(fmt.Errorf(bad_message))
	}
}

func check_field_required_and_positive(t any, slot string) {
	var t1 = reflect.ValueOf(t)
	var s = t1.FieldByName(slot)
	//fmt.Printf("s=%T %v\n", s, s)
	assert_fatal(s.IsValid())
	switch s.Kind() {
	case reflect.Int:
		fallthrough
	case reflect.Int8:
		fallthrough
	case reflect.Int16:
		fallthrough
	case reflect.Int32:
		fallthrough
	case reflect.Int64:
		var x1 = s.Int()
		if !(!s.IsZero() && x1 > 0) {
			log.Panicf("field (%s) is required in %T.", slot, t)
		}
	case reflect.String:
		if s.IsZero() {
			log.Panicf("field (%s) is required in %T.", slot, t)
		}
	}
}

func check_multiplexer_entry(e Multiplexer_conf) {
	for _, slot := range []string{
		"Port",
		"Front_host",
		//"Trusted_proxies",
		"Mux_ep_update_interval",
		"Forwarding_timeout",
		"Probe_access_timeout",
		"Bad_response_delay",
		"Busy_suspension_time",
		//"Mux_node_name",
		"Backend",
		"Backend_command_timeout",
		"Mux_access_log_file",
	} {
		check_field_required_and_positive(e, slot)
	}
	if !slices.Contains(backend_list, e.Backend) {
		panic(fmt.Errorf(bad_message))
	}
}

func check_registrar_entry(e Registrar_conf) {
	for _, slot := range []string{
		"Port",
		"Front_host",
		// "Trusted_proxies",
		// "Base_path",
		"Claim_uid_map",
		"Probe_access_timeout",
		"Max_pool_expiry",
		"Csrf_secret_seed",
		"Backend",
		"Backend_command_timeout",
		"Api_access_log_file",
	} {
		check_field_required_and_positive(e, slot)
	}
	if !slices.Contains(claim_conversions, e.Claim_uid_map) {
		panic(fmt.Errorf(bad_message))
	}
	if !slices.Contains(backend_list, e.Backend) {
		panic(fmt.Errorf(bad_message))
	}
}

func check_manager_entry(e Manager_conf) {
	for _, slot := range []string{
		"Sudo",
		"Port_min",
		"Port_max",
		"Backend_awake_duration",
		"Backend_setup_at_start",
		"Backend_start_timeout",
		"Backend_setup_timeout",
		"Backend_stop_timeout",
		"Backend_command_timeout",
		"Heartbeat_interval",
		"Heartbeat_miss_tolerance",
		"Heartbeat_timeout",
	} {
		check_field_required_and_positive(e, slot)
	}
}

func check_minio_entry(e Minio_conf) {
	if len(e.Minio) > 0 &&
		len(e.Mc) > 0 {
	} else {
		panic(fmt.Errorf(bad_message))
	}
}

func check_ui_entry(e UI_conf) {
	if len(e.S3_url) > 0 &&
		len(e.Footer_banner) > 0 {
	} else {
		panic(fmt.Errorf(bad_message))
	}
}

func check_syslog_entry(e Syslog_conf) {
	if len(e.Facility) > 0 &&
		len(e.Priority) > 0 {
	} else {
		panic(fmt.Errorf(bad_message))
	}
}

// func check_registrar_entry_2(e Registrar_conf) {
// 	if e.Port > 0 &&
// 		e.Front_host != "" &&
// 		// e.Trusted_proxies
// 		// e.Base_path != "" &&
// 		slices.Contains(claim_conversions, e.Claim_uid_map) &&
// 		e.Probe_access_timeout > 0 &&
// 		e.Backend_command_timeout > 0 &&
// 		e.Max_pool_expiry > 0 &&
// 		e.Csrf_secret_seed != "" &&
// 		e.Backend != "" &&
// 		e.Backend_command_timeout > 0 &&
// 		e.Api_access_log_file != "" {
// 	} else {
// 		panic(fmt.Errorf(bad_message))
// 	}
// }

// func check_multiplexer_entry_2(e Multiplexer_conf) {
// 	if e.Port > 0 &&
// 		e.Front_host != "" &&
// 		// e.Trusted_proxies
// 		e.Mux_ep_update_interval > 0 &&
// 		e.Forwarding_timeout > 0 &&
// 		e.Probe_access_timeout > 0 &&
// 		e.Bad_response_delay > 0 &&
// 		e.Busy_suspension_time > 0 &&
// 		//e.Mux_node_name
// 		e.Backend != "" &&
// 		e.Backend_command_timeout > 0 &&
// 		e.Mux_access_log_file != "" {
// 	} else {
// 		panic(fmt.Errorf(bad_message))
// 	}
// }

// func check_manager_entry_2(e Manager_conf) {
// 	assert_slot(len(e.Sudo) > 0)
// 	assert_slot(e.Port_min > 0)
// 	assert_slot(e.Port_max > 0)
// 	assert_slot(e.Backend_awake_duration > 0)
// 	//assert_slot(Backend_setup_at_start : bool
// 	assert_slot(e.Backend_start_timeout > 0)
// 	assert_slot(e.Backend_setup_timeout > 0)
// 	assert_slot(e.Backend_stop_timeout > 0)
// 	assert_slot(e.Backend_command_timeout > 0)
// 	assert_slot(e.Heartbeat_interval > 0)
// 	assert_slot(e.Heartbeat_miss_tolerance > 0)
// 	assert_slot(e.Heartbeat_timeout > 0)
// }
