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
	//"reflect"
)

// DB_CONF is a pair of an endpoint and password to access a
// keyval-DB, and it is usually stored in a file in "etc".
type Db_conf struct {
	Ep       string
	Password string
}

// Number representation in the configuration structure is integer.
type Number int

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
	Port                    Number   `json:"port"`
	Front_host              string   `json:"front_host"`
	Trusted_proxies         []string `json:"trusted_proxies"`
	Mux_ep_update_interval  Number   `json:"mux_ep_update_interval"`
	Forwarding_timeout      Number   `json:"forwarding_timeout"`
	Probe_access_timeout    Number   `json:"probe_access_timeout"`
	Bad_response_delay      Number   `json:"bad_response_delay"`
	Busy_suspension_time    Number   `json:"busy_suspension_time"`
	Mux_node_name           string   `json:"mux_node_name"`
	Backend                 string   `json:"backend"`
	Backend_command_timeout Number   `json:"backend_command_timeout"`
	Mux_access_log_file     string   `json:"mux_access_log_file"`
}

type Registrar_conf struct {
	Port            Number   `json:"port"`
	Front_host      string   `json:"front_host"`
	Trusted_proxies []string `json:"trusted_proxies"`
	Base_path       string   `json:"base_path"`
	Claim_uid_map   string   `json:"claim_uid_map"`
	// {"id", "email-name", "map"}
	Probe_access_timeout    Number `json:"probe_access_timeout"`
	Max_pool_expiry         Number `json:"max_pool_expiry"`
	Csrf_secret_seed        string `json:"csrf_secret_seed"`
	Backend                 string `json:"backend"`
	Backend_command_timeout Number `json:"backend_command_timeout"`
	Api_access_log_file     string `json:"api_access_log_file"`
}

type Manager_conf struct {
	Sudo                     string `json:"sudo"`
	Port_min                 Number `json:"port_min"`
	Port_max                 Number `json:"port_max"`
	Backend_awake_duration   Number `json:"backend_awake_duration"`  // Minio_awake_duration
	Backend_setup_at_start   bool   `json:"backend_setup_at_start"`  // Minio_setup_at_start
	Backend_start_timeout    Number `json:"backend_start_timeout"`   // Minio_start_timeout
	Backend_setup_timeout    Number `json:"backend_setup_timeout"`   // Minio_setup_timeout
	Backend_stop_timeout     Number `json:"backend_stop_timeout"`    // Minio_stop_timeout
	Backend_command_timeout  Number `json:"backend_command_timeout"` // Minio_mc_timeout
	Heartbeat_interval       Number `json:"heartbeat_interval"`
	Heartbeat_miss_tolerance Number `json:"heartbeat_miss_tolerance"`
	Heartbeat_timeout        Number `json:"heartbeat_timeout"`
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

type Gunicorn_conf__ struct {
	Port                Number
	Workers             Number
	Threads             Number
	Timeout             Number
	Access_logfile      string
	Reload              string //bool
	Log_file            string
	Log_level           string
	Log_syslog_facility string
}

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
	check_redis_entry(conf)
	return conf
}

// Read_conf reads a configuration file and checks a structure is
// properly filled.
func Read_conf(file_ string) interface{} {
	var _, err1 = os.ReadFile("conf.yaml")
	if err1 != nil {
		panic(err1)
	}
	var yaml2 = make(map[string]interface{})
	//var err2 = yaml.Unmarshal(b1, &yaml2)
	var err2 error = nil
	if err2 != nil {
		panic(err2)
	}
	var json3, err4 = json.Marshal(yaml2)
	if err4 != nil {
		panic(err4)
	}

	//fmt.Println(yaml2)
	//fmt.Println(string(json3))

	/*
		var c2 = yaml2["controller"].(map[string]interface{})
		fmt.Println(c2)
		var t2 = c2["minio_mc_timeout"]
		fmt.Println(reflect.TypeOf(t2))
		fmt.Println(t2)
	*/
	/*
		var b3, err3 = json.Marshal(&yaml2)
		if err3 != nil {
			panic(err3)
		}
		fmt.Print(b3)
	*/
	/*
		fmt.Println(yaml2)
	*/

	var sub = yaml2["subject"].(string)[:3]
	switch sub {
	case "mux":
		var muxconf Mux_conf
		var err5 = json.Unmarshal(json3, &muxconf)
		if err5 != nil {
			panic(fmt.Sprint("Bad .yaml conf file:", err5))
		}
		fmt.Println("MUX CONF is", muxconf)
		//check_mux_conf(muxconf)
		return muxconf
	case "api":
		var apiconf Api_conf
		var err6 = json.Unmarshal(json3, &apiconf)
		if err6 != nil {
			panic(fmt.Sprint("Bad .yaml conf file:", err6))
		}
		fmt.Println("API CONF is", apiconf)
		//check_api_conf(apiconf)
		return apiconf
	default:
		panic(fmt.Sprint("Bad .yaml conf file: Bad subject field."))
	}
}

func check_mux_conf(conf Mux_conf) {
	//check_gunicorn_entry(conf.Gunicorn)
	check_multiplexer_entry(conf.Multiplexer)
	check_manager_entry(conf.Manager)
	check_minio_entry(conf.Minio)
	check_syslog_entry(conf.Log_syslog)
}

func check_api_conf(conf Api_conf) {
	//check_gunicorn_entry(conf.Gunicorn)
	check_registrar_entry(conf.Registrar)
	check_minio_entry(conf.Minio)
	check_ui_entry(conf.UI)
	check_syslog_entry(conf.Log_syslog)
}

func assert_slot(c bool) {
	if !c {
		panic(fmt.Errorf("Bad conf file."))
	}
}

func check_gunicorn_entry(e Gunicorn_conf__) {
	assert_slot(e.Port > 0)
	assert_slot(e.Workers > 0)
	//assert_slot(e.Threads >= 0)
	assert_slot(e.Timeout > 0)
	assert_slot(len(e.Access_logfile) > 0)
	// assert_slot(e.Reload is bool and always OK.)
	assert_slot(len(e.Log_file) > 0)
	assert_slot(len(e.Log_level) > 0)
	assert_slot(len(e.Log_syslog_facility) >= 0)
}

func check_registrar_entry(e Registrar_conf) {
	if len(e.Front_host) > 0 &&
		//e.Trusted_proxies : []string
		len(e.Base_path) > 0 &&
		len(e.Claim_uid_map) > 0 &&
		// {"id", "email-name", "map"}
		e.Probe_access_timeout > 0 &&
		e.Backend_command_timeout > 0 &&
		e.Max_pool_expiry > 0 &&
		len(e.Csrf_secret_seed) > 0 {
	} else {
		panic(fmt.Errorf("Bad .yaml conf file."))
	}
}

func check_multiplexer_entry(e Multiplexer_conf) {
	if len(e.Front_host) > 0 &&
		//e.Trusted_proxies : []string
		e.Mux_ep_update_interval > 0 &&
		e.Forwarding_timeout > 0 &&
		e.Probe_access_timeout > 0 &&
		e.Bad_response_delay > 0 &&
		e.Busy_suspension_time > 0 &&
		len(e.Mux_node_name) >= 0 {
	} else {
		panic(fmt.Errorf("Bad .yaml conf file."))
	}
}

func check_manager_entry(e Manager_conf) {
	assert_slot(len(e.Sudo) > 0)
	assert_slot(e.Port_min > 0)
	assert_slot(e.Port_max > 0)
	assert_slot(e.Backend_awake_duration > 0)
	//assert_slot(Backend_setup_at_start : bool
	assert_slot(e.Backend_start_timeout > 0)
	assert_slot(e.Backend_setup_timeout > 0)
	assert_slot(e.Backend_stop_timeout > 0)
	assert_slot(e.Backend_command_timeout > 0)
	assert_slot(e.Heartbeat_interval > 0)
	assert_slot(e.Heartbeat_miss_tolerance > 0)
	assert_slot(e.Heartbeat_timeout > 0)
}

func check_redis_entry(e Db_conf) {
	if len(e.Ep) > 0 && len(e.Password) > 0 {
	} else {
		log.Panic(fmt.Errorf("Bad conf.json conf-file."))
	}
}

func check_minio_entry(e Minio_conf) {
	if len(e.Minio) > 0 &&
		len(e.Mc) > 0 {
	} else {
		panic(fmt.Errorf("Bad .yaml conf file."))
	}
}

func check_ui_entry(e UI_conf) {
	if len(e.S3_url) > 0 &&
		len(e.Footer_banner) > 0 {
	} else {
		panic(fmt.Errorf("Bad .yaml conf file."))
	}
}

func check_syslog_entry(e Syslog_conf) {
	if len(e.Facility) > 0 &&
		len(e.Priority) > 0 {
	} else {
		panic(fmt.Errorf("Bad .yaml conf file."))
	}
}
