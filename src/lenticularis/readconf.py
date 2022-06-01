"""A config file reader."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import jsonschema
import os
import yaml

##default_mux_conf = "/etc/lenticularis/mux-config.yaml"
mux_conf_envname = "LENTICULARIS_MUX_CONFIG"

##default_adm_conf = "/etc/lenticularis/adm-config.yaml"
adm_conf_envname = "LENTICULARIS_ADM_CONFIG"

node_envname = "LENTICULARIS_MUX_NODE"


def read_mux_conf(configfile=None):
    return readconf(configfile, fix_mux_conf, validate_mux_conf,
                    mux_conf_envname)


def read_adm_conf(configfile=None):
    return readconf(configfile, fix_adm_conf, validate_adm_conf,
                    adm_conf_envname)


def readconf(configfile, fixfn, valfn, envname):
    if configfile is None:
        configfile = os.environ.get(envname)
    assert configfile is not None

    try:
        with open(configfile, "r") as f:
            conf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"cannot read {configfile} {e}")
    except Exception as e:
        raise Exception(f"cannot read {configfile} {e}")

    conf = fixfn(conf)
    valfn(conf)

    return (conf, configfile)


def gunicorn_schema(number_type):
    return {
        "type": "object",
        "properties": {
            "port": {"type": "string"},
            "workers": number_type,
            "threads": number_type,
            "timeout": number_type,
            "access_logfile": {"type": "string"},
            "log_file": {"type": "string"},
            "log_level": {"type": "string"},
            "log_syslog_facility": {"type": "string"},
            "reload": {"type": "string"},
        },
        "required": [
            "port",
        ],
        "additionalProperties": False,
    }


def redis_schema(number_type):
    return {
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "port": number_type,
            "password": {"type": "string"},
        },
        "required": [
            "host",
            "port",
            "password",
        ],
        "additionalProperties": False,
    }


def syslog_schema():
    return {
        "type": "object",
        "properties": {
            "facility": {"type": "string"},
            "priority": {"type": "string"},
        },
        "required": [
            "facility",
            "priority",
        ],
        "additionalProperties": False,
    }


def mux_schema(number_type):

    multiplexer = {
        "type": "object",
        "properties": {
            #"port": number_type,
            #"facade_hostnames": {"type": "array", "items": {"type": "string"}},
            "facade_hostname": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "timer_interval": number_type,
            "request_timeout": number_type,
            "probe_access_timeout": number_type,
        },
        "required": [
            "facade_hostname",
            "trusted_proxies",
            "timer_interval",
            "request_timeout",
            "probe_access_timeout",
        ],
        "additionalProperties": False,
    }

    controller = {
        "type": "object",
        "properties": {
            "port_min": number_type,
            "port_max": number_type,
            "watch_interval": number_type,
            "keepalive_limit": number_type,
            "heartbeat_miss_tolerance": number_type,
            "minio_startup_timeout": number_type,
            "max_lock_duration": number_type,
            "mc_info_timelimit": number_type,
            "mc_stop_timelimit": number_type,
            "kill_supervisor_wait": number_type,
            "minio_user_install_timelimit": number_type,
            "refresh_margin": number_type,
            "sudo": {"type": "string"},
        },
        "required": [
            "port_min",
            "port_max",
            "watch_interval",
            "keepalive_limit",
            "heartbeat_miss_tolerance",
            "minio_startup_timeout",
            "max_lock_duration",
            "mc_info_timelimit",
            "mc_stop_timelimit",
            "kill_supervisor_wait",
            "minio_user_install_timelimit",
            "refresh_margin",
            "sudo",
        ],
        "additionalProperties": False,
    }

    minio = {
        "type": "object",
        "properties": {
            "minio": {"type": "string"},
            "mc": {"type": "string"},
        },
        "required": [
            "minio",
            "mc",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "redis": redis_schema(number_type),
            "gunicorn": gunicorn_schema(number_type),
            "aws_signature": {"type": "string"},
            "multiplexer": multiplexer,
            "controller": controller,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": syslog_schema(),
        },
        "required": [
            "redis",
            "gunicorn",
            "multiplexer",
            "controller",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }


def adm_schema(number_type):

    multiplexer = {
        "type": "object",
        "properties": {
            #"facade_hostnames": {"type": "array", "items": {"type": "string"}},
            "facade_hostname": {"type": "string"},
        },
        "required": [
            "facade_hostname",
        ],
        "additionalProperties": False,
    }

    controller = {
        "type": "object",
        "properties": {
            "max_lock_duration": number_type,
        },
        "required": [
            "max_lock_duration",
        ],
        "additionalProperties": False,
    }

    system_settings = {
        "type": "object",
        "properties": {
            "max_zone_per_user": number_type,
            "max_direct_hostnames_per_user": number_type,
            "default_zone_lifetime": number_type,
            "allowed_maximum_zone_exp_date": number_type,
            "endpoint_url": {"type": "string"},
            "direct_hostname_validator": {"type": "string"},  # choice = ["flat"]
            "direct_hostname_domains": {"type": "array", "items": {"type": "string"}},
            "reserved_hostnames": {"type": "array", "items": {"type": "string"}},
            "probe_access_timeout": number_type,
        },
        "required": [
            "max_zone_per_user",
            "max_direct_hostnames_per_user",
            "default_zone_lifetime",
            "allowed_maximum_zone_exp_date",
            "endpoint_url",
            "direct_hostname_validator",
            "direct_hostname_domains",
            "reserved_hostnames",
            "probe_access_timeout",
        ],
        "additionalProperties": False,
    }

    webui = {
        "type": "object",
        "properties": {
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "CSRF_secret_key": {"type": "string"},
        },
        "required": [
            "trusted_proxies",
            "CSRF_secret_key",
        ],
        "additionalProperties": False,
    }

    minio = {
        "type": "object",
        "properties": {
            "minio": {"type": "string"},
            "mc": {"type": "string"},
        },
        "required": [
            "minio",
            "mc",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "gunicorn": gunicorn_schema(number_type),
            "redis": redis_schema(number_type),
            "aws_signature": {"type": "string"},
            "multiplexer": multiplexer,
            "controller": controller,
            "system_settings": system_settings,
            "webui": webui,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": syslog_schema(),
        },
        "required": [
            "gunicorn",
            "redis",
            "multiplexer",
            "controller",
            "system_settings",
            "webui",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }


def validate_mux_conf(conf):
    jsonschema.validate(instance=conf, schema=mux_schema({"type": "string"}))
    check_type_number(conf, mux_schema({"type": "number"}))


def validate_adm_conf(conf):
    jsonschema.validate(instance=conf, schema=adm_schema({"type": "string"}))
    check_type_number(conf, adm_schema({"type": "number"}))


def check_type_number(conf, schema):
    if schema["type"] == "object":
        for (property, sub_schema) in schema["properties"].items():
            val = conf.get(property)
            if val:
                check_type_number(val, sub_schema)
            elif property in schema["required"]:
                raise Exception(f"missing required {property}")
    elif schema["type"] == "array":
        sub_schema = schema["items"]
        if not isinstance(conf, list):
            raise Exception(f"not an array: {conf}")
        for e in conf:
            check_type_number(e, sub_schema)
    elif schema["type"] == "string":
        if not isinstance(conf, str):
            raise Exception(f"not a string: {conf}")
    elif schema["type"] == "number":
        if not isinstance(conf, str) or not conf.isdigit():
            raise Exception(f"not a number: {conf}")
    else:
        raise Exception("INTERNAL ERROR: NOT IMPLEMENTED")


def fix_adm_conf(conf):
    multiplexer_param = conf["multiplexer"]
    #merge_single_key_into_list_key(multiplexer_param, "facade_hostname",
    #                               "facade_hostnames")
    system_settings_param = conf["system_settings"]
    merge_single_key_into_list_key(system_settings_param, "direct_hostname_domain",
                                 "direct_hostname_domains")
    return conf


def fix_mux_conf(conf):
    multiplexer_param = conf["multiplexer"]
    #merge_single_key_into_list_key(multiplexer_param, "facade_hostname",
    #                               "facade_hostnames")
    return conf


def merge_single_key_into_list_key(dic, single_key, list_key):
    single_val = dic.get(single_key)
    list_val = dic.get(list_key)
    if single_val is not None:
        if list_val is None:
            list_val = [single_val]
        else:
            list_val.push(single_val)   # XXX XXX XXX append?
        dic.pop(single_key)
    if list_val is not None:
        dic[list_key] = list_val
