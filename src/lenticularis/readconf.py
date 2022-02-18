# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from jsonschema import validate
import os
import yaml

default_mux_conf = "/etc/lenticularis/mux-config.yaml"
mux_conf_envname = "LENTICULARIS_MUX_CONFIG"


default_adm_conf = "/etc/lenticularis/adm-config.yaml"
adm_conf_envname = "LENTICULARIS_ADM_CONFIG"


node_envname = "LENTICULARIS_MUX_NODE"


def read_mux_conf(configfile=None):
    return readconf(configfile, fix_mux_conf, validate_mux_conf,
                    mux_conf_envname, default_mux_conf)


def read_adm_conf(configfile=None):
    return readconf(configfile, fix_adm_conf, validate_adm_conf,
                    adm_conf_envname, default_adm_conf)


def readconf(configfile, fix, vali, envname, default_conf):
    if configfile is None:
        configfile = os.environ.get(envname)
    if configfile is None:
        configfile = default_conf

    try:
        with open(configfile, "r") as f:
            conf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"cannot read {configfile} {e}")
    except Exception as e:
        raise Exception(f"cannot read {configfile} {e}")

    conf = fix(conf)
    vali(conf)

    return (conf, configfile)


def gunicorn_schema(type_number):
    return {
        "type": "object",
        "properties": {
            "bind": {"type": "string"},
            "workers": type_number,
            "threads": type_number,
            "timeout": type_number,
            "log_file": {"type": "string"},
            "log_level": {"type": "string"},
            "log_syslog_facility": {"type": "string"},
            "reload": {"type": "string"},
        },
        "required": [
            "bind",
            # OPTIONAL "workers",
            # OPTIONAL "threads",
            # OPTIONAL "timeout",
            # OPTIONAL "log_file",
            # OPTIONAL "log_level",
            # OPTIONAL "log_syslog_facility",
            # OPTIONAL "reload",
        ],
        "additionalProperties": False,
    }


def redis_schema(type_number):
    return {
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "port": type_number,
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


def mux_schema(type_number):

    multiplexer = {
        "type": "object",
        "properties": {
            "port": type_number,
            "delegate_hostnames": {"type": "array", "items": {"type": "string"}},
            "trusted_hosts": {"type": "array", "items": {"type": "string"}},
            "timer_interval": type_number,
            "request_timeout": type_number,
        },
        "required": [
            "port",
            "delegate_hostnames",
            "trusted_hosts",
            "timer_interval",
            "request_timeout",
        ],
        "additionalProperties": False,
    }

    controller = {
        "type": "object",
        "properties": {
            "port_min": type_number,
            "port_max": type_number,
            "watch_interval": type_number,
            "keepalive_limit": type_number,
            "allowed_down_count": type_number,
            "max_lock_duration": type_number,
            "mc_info_timelimit": type_number,
            "mc_stop_timelimit": type_number,
            "kill_supervisor_wait": type_number,
            "minio_user_install_timelimit": type_number,
            "refresh_margin": type_number,
            "sudo": {"type": "string"},
        },
        "required": [
            "port_min",
            "port_max",
            "watch_interval",
            "keepalive_limit",
            "allowed_down_count",
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
            "minio_http_trace": {"type": "string"},
            "mc": {"type": "string"},
        },
        "required": [
            "minio",
            # OPTIONAL "minio_http_trace",
            "mc",
        ],
        "additionalProperties": False,
    }

    lenticularis = {
        "type": "object",
        "properties": {
            "multiplexer": multiplexer,
            "controller": controller,
            "minio": minio,
            "syslog": syslog_schema(),
        },
        "required": [
            "multiplexer",
            "controller",
            "minio",
            "syslog",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "gunicorn": gunicorn_schema(type_number),
            "redis": redis_schema(type_number),
            "lenticularis": lenticularis,
        },
        "required": [
            "gunicorn",
            "redis",
            "lenticularis",
        ],
        "additionalProperties": False,
    }


def adm_schema(type_number):

    multiplexer = {
        "type": "object",
        "properties": {
            "delegate_hostnames": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "delegate_hostnames",
        ],
        "additionalProperties": False,
    }

    controller = {
        "type": "object",
        "properties": {
            "max_lock_duration": type_number,
        },
        "required": [
            "max_lock_duration",
        ],
        "additionalProperties": False,
    }

    system_settings = {
        "type": "object",
        "properties": {
            "max_zone_per_user": type_number,
            "max_direct_hostnames_per_user": type_number,
            "default_zone_lifetime": type_number,
            "allowed_maximum_zone_exp_date": type_number,
            "endpoint_url": {"type": "string"},
            "direct_hostname_validator": {"type": "string"},  # choice = ["flat"]
            "direct_hostname_domains": {"type": "array", "items": {"type": "string"}},
            "reserved_hostnames": {"type": "array", "items": {"type": "string"}},
            "decoy_connection_timeout": type_number,
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
            "decoy_connection_timeout",
        ],
        "additionalProperties": False,
    }

    lenticularis = {
        "type": "object",
        "properties": {
            "multiplexer": multiplexer,
            "controller": controller,
            "system_settings": system_settings,
            "syslog": syslog_schema(),
        },
        "required": [
            "multiplexer",
            "controller",
            "system_settings",
            "syslog",
        ],
        "additionalProperties": False,
    }

    webui = {
        "type": "object",
        "properties": {
            "trusted_hosts": {"type": "array", "items": {"type": "string"}},
            "CSRF_secret_key": {"type": "string"},
        },
        "required": [
            "trusted_hosts",
            "CSRF_secret_key",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "gunicorn": gunicorn_schema(type_number),
            "redis": redis_schema(type_number),
            "lenticularis": lenticularis,
            "webui": webui,
        },
        "required": [
            "gunicorn",
            "redis",
            "lenticularis",
            "webui",
        ],
        "additionalProperties": False,
    }


def validate_mux_conf(conf):
    validate(instance=conf, schema=mux_schema({"type": "string"}))
    check_type_number(conf, mux_schema({"type": "number"}))


def validate_adm_conf(conf):
    validate(instance=conf, schema=adm_schema({"type": "string"}))
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
    multiplexer_param = conf["lenticularis"]["multiplexer"]
    merge_single_key_into_list_key(multiplexer_param, "delegate_hostname",
                                 "delegate_hostnames")
    system_settings_param = conf["lenticularis"]["system_settings"]
    merge_single_key_into_list_key(system_settings_param, "direct_hostname_domain",
                                 "direct_hostname_domains")
    return conf


def fix_mux_conf(conf):
    multiplexer_param = conf["lenticularis"]["multiplexer"]
    merge_single_key_into_list_key(multiplexer_param, "delegate_hostname",
                                 "delegate_hostnames")
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
