/* A conf file reader. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Conf files are in yaml, and they are read
// and checked against json schema.

// https://pkg.go.dev/gopkg.in/yaml.v3@v3.0.1
// == https://gopkg.in/yaml.v3
// https://pkg.go.dev/sigs.k8s.io/yaml

import (
	"encoding/json"
	"fmt"
	"gopkg.in/yaml.v3"
	"io/ioutil"
	//"reflect"
)

// Number representation in the configuration structure is integer.
type Number int

// Lens3_conf is a union of Mux_conf|Api_conf.
type Lens3_conf interface{ lens3_conf_union() }

func (Mux_conf) lens3_conf_union() {}
func (Api_conf) lens3_conf_union() {}

type Conf_header struct {
	Subject       string
	Version       string
	Aws_signature string
}

type Redis_conf struct {
	Host     string
	Port     Number
	Password string
}

// Mux_conf is a configuration of Mux.  mux_node_name and log_file are
// optional.
type Mux_conf struct {
	Conf_header
	//Subject       string
	//Version       string
	//Aws_signature string
	Gunicorn      Gunicorn_conf
	Multiplexer   Multiplexer_conf
	Minio_Manager Manager_conf
	Minio         Minio_conf
	Log_file      string
	Log_syslog    Syslog_conf
}

// Api_conf is a configuration of Api.  log_file is optional.
type Api_conf struct {
	Conf_header
	//Subject       string
	//Version       string
	//Aws_signature string
	Gunicorn   Gunicorn_conf
	Controller Controller_conf
	UI         UI_conf
	Minio      Minio_conf
	Log_file   string
	Log_syslog Syslog_conf
}

type Multiplexer_conf struct {
	Front_host             string
	Trusted_proxies        []string
	Mux_ep_update_interval Number
	Forwarding_timeout     Number
	Probe_access_timeout   Number
	Bad_response_delay     Number
	Busy_suspension_time   Number
	Mux_node_name          string
}

type Controller_conf struct {
	Front_host      string
	Trusted_proxies []string
	Base_path       string
	Claim_uid_map   string
	// {"id", "email-name", "map"}
	Probe_access_timeout Number
	Minio_mc_timeout     Number
	Max_pool_expiry      Number
	Csrf_secret_seed     string
}

type Manager_conf struct {
	Sudo                     string
	Port_min                 Number
	Port_max                 Number
	Minio_awake_duration     Number
	Minio_setup_at_start     bool
	Heartbeat_interval       Number
	Heartbeat_miss_tolerance Number
	Heartbeat_timeout        Number
	Minio_start_timeout      Number
	Minio_setup_timeout      Number
	Minio_stop_timeout       Number
	Minio_mc_timeout         Number
}

type Minio_conf struct {
	Minio string
	Mc    string
}

type UI_conf struct {
	S3_url        string
	Footer_banner string
}

type Syslog_conf struct {
	Facility string
	Priority string
}

type Gunicorn_conf struct {
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

// Read_yaml_conf reads a configuration file and checks a structure is
// properly filled.
func Read_yaml_conf(file_ string) interface{} {
	var b1, err1 = ioutil.ReadFile("conf.yaml")
	if err1 != nil {
		panic(err1)
	}
	var yaml2 = make(map[string]interface{})
	var err2 = yaml.Unmarshal(b1, &yaml2)
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
		check_mux_conf(muxconf)
		return muxconf
	case "api":
		var apiconf Api_conf
		var err6 = json.Unmarshal(json3, &apiconf)
		if err6 != nil {
			panic(fmt.Sprint("Bad .yaml conf file:", err6))
		}
		fmt.Println("API CONF is", apiconf)
		check_api_conf(apiconf)
		return apiconf
	default:
		panic(fmt.Sprint("Bad .yaml conf file: Bad subject field."))
	}
}

func check_mux_conf(conf Mux_conf) {
	check_gunicorn_entry(conf.Gunicorn)
	check_multiplexer_entry(conf.Multiplexer)
	check_manager_entry(conf.Minio_Manager)
	check_minio_entry(conf.Minio)
	check_syslog_entry(conf.Log_syslog)
}

func check_api_conf(conf Api_conf) {
	check_gunicorn_entry(conf.Gunicorn)
	check_controller_entry(conf.Controller)
	check_minio_entry(conf.Minio)
	check_ui_entry(conf.UI)
	check_syslog_entry(conf.Log_syslog)
}

func assert_slot(c bool) {
	if !c {
		panic(fmt.Errorf("Bad .yaml conf file."))
	}
}

func check_gunicorn_entry(e Gunicorn_conf) {
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

func check_controller_entry(e Controller_conf) {
	if len(e.Front_host) > 0 &&
		//e.Trusted_proxies : []string
		len(e.Base_path) > 0 &&
		len(e.Claim_uid_map) > 0 &&
		// {"id", "email-name", "map"}
		e.Probe_access_timeout > 0 &&
		e.Minio_mc_timeout > 0 &&
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
	assert_slot(e.Minio_awake_duration > 0)
	//assert_slot(Minio_setup_at_start : bool
	assert_slot(e.Heartbeat_interval > 0)
	assert_slot(e.Heartbeat_miss_tolerance > 0)
	assert_slot(e.Heartbeat_timeout > 0)
	assert_slot(e.Minio_start_timeout > 0)
	assert_slot(e.Minio_setup_timeout > 0)
	assert_slot(e.Minio_stop_timeout > 0)
	assert_slot(e.Minio_mc_timeout > 0)
}

func check_redis_entry(e Redis_conf) {
	if len(e.Host) > 0 &&
		e.Port > 0 &&
		len(e.Password) > 0 {
	} else {
		panic(fmt.Errorf("Bad .yaml conf file."))
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
