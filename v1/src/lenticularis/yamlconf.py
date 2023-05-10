"""A conf file reader.  Conf files are in yaml, and they are read
and checked against json schema."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import json
import jsonschema
import yaml
from lenticularis.utility import rephrase_exception_message


def read_yaml_conf(file):
    """Reads a file and checks it against json schema."""
    assert file is not None
    try:
        with open(file, "r") as f:
            yamlconf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"Reading a conf file failed: {file}:"
                        f" exception=({e})")
    except Exception as e:
        m = rephrase_exception_message(e)
        raise Exception(f"Reading a conf file failed: {file}:"
                        f" exception=({m})")
    if "subject" not in yamlconf:
        raise Exception(f"Bad conf file: {file}:"
                        f" missing subject")
    sub = yamlconf["subject"]
    if sub == "api":
        schema = _api_conf_schema()
        conf = _fix_type(yamlconf, schema)
        jsonschema.validate(instance=conf, schema=schema)
        return conf
    elif sub[:3] == "mux":
        schema = _mux_conf_schema()
        conf = _fix_type(yamlconf, schema)
        jsonschema.validate(instance=conf, schema=schema)
        return conf
    else:
        raise Exception(f"Bad conf file: {file}:"
                        f" bad subject=({sub})")
    pass


redis_json_schema = {
    "type": "object",
    "properties": {
        "host": {"type": "string"},
        "port": {"type": "number"},
        "password": {"type": "string"},
    },
    "required": [
        "host",
        "port",
        "password",
    ],
    "additionalProperties": False,
}

_gunicorn_json_schema = {
    "type": "object",
    "properties": {
        "port": {"type": "string"},
        "workers": {"type": "number"},
        "threads": {"type": "number"},
        "timeout": {"type": "number"},
        "access_logfile": {"type": "string"},
        "reload": {"type": "string"},
        "log_file": {"type": "string"},
        "log_level": {"type": "string"},
        "log_syslog_facility": {"type": "string"},
    },
    "required": [
        "port",
    ],
    "additionalProperties": False,
}

_syslog_json_schema = {
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

_minio_json_schema = {
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

def _mux_conf_schema():
    """mux_node_name and log_file are optional."""
    multiplexer = {
        "type": "object",
        "properties": {
            "front_host": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "mux_ep_update_interval": {"type": "number"},
            "forwarding_timeout": {"type": "number"},
            "probe_access_timeout": {"type": "number"},
            "bad_response_delay": {"type": "number"},
            "mux_node_name": {"type": "string"},
        },
        "required": [
            "front_host",
            "trusted_proxies",
            "mux_ep_update_interval",
            "forwarding_timeout",
            "probe_access_timeout",
            "bad_response_delay",
        ],
        "additionalProperties": False,
    }
    minio_manager = {
        "type": "object",
        "properties": {
            "sudo": {"type": "string"},
            "port_min": {"type": "number"},
            "port_max": {"type": "number"},
            "minio_awake_duration": {"type": "number"},
            "minio_setup_at_restart": {"type": "boolean"},
            "heartbeat_interval": {"type": "number"},
            "heartbeat_miss_tolerance": {"type": "number"},
            "heartbeat_timeout": {"type": "number"},
            "minio_start_timeout": {"type": "number"},
            "minio_setup_timeout": {"type": "number"},
            "minio_stop_timeout": {"type": "number"},
            "minio_mc_timeout": {"type": "number"},
        },
        "required": [
            "sudo",
            "port_min",
            "port_max",
            "minio_awake_duration",
            "minio_setup_at_restart",
            "heartbeat_interval",
            "heartbeat_miss_tolerance",
            "heartbeat_timeout",
            "minio_start_timeout",
            "minio_setup_timeout",
            "minio_stop_timeout",
            "minio_mc_timeout",
        ],
        "additionalProperties": False,
    }
    _schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "version": {"type": "string"},
            "aws_signature": {"type": "string"},
            "gunicorn": _gunicorn_json_schema,
            "multiplexer": multiplexer,
            "minio_manager": minio_manager,
            "minio": _minio_json_schema,
            "log_file": {"type": "string"},
            "log_syslog": _syslog_json_schema,
        },
        "required": [
            "subject",
            "version",
            "aws_signature",
            "gunicorn",
            "multiplexer",
            "minio_manager",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return _schema


def _api_conf_schema():
    """log_file is optional."""
    controller = {
        "type": "object",
        "properties": {
            "front_host": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "base_path": {"type": "string"},
            "claim_uid_map": {"type": "string",
                              "enum": ["id", "email-name", "map"]},
            "probe_access_timeout": {"type": "number"},
            "minio_mc_timeout": {"type": "number"},
            "max_pool_expiry": {"type": "number"},
            "csrf_secret_key": {"type": "string"},
        },
        "required": [
            "front_host",
            "trusted_proxies",
            "base_path",
            "claim_uid_map",
            "probe_access_timeout",
            "minio_mc_timeout",
            "max_pool_expiry",
            "csrf_secret_key",
        ],
        "additionalProperties": False,
    }
    _schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "version": {"type": "string"},
            "aws_signature": {"type": "string"},
            "gunicorn": _gunicorn_json_schema,
            "controller": controller,
            "minio": _minio_json_schema,
            "log_file": {"type": "string"},
            "log_syslog": _syslog_json_schema,
        },
        "required": [
            "subject",
            "version",
            "aws_signature",
            "gunicorn",
            "controller",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return _schema


def _fix_type(data, schema):
    """Rereads tokens in yaml to match for json schema.  It admits
    missing/additional properties, which will be checked by json
    validation.
    """
    if schema["type"] == "object":
        newdata = data.copy()
        for (prop, subschema) in schema["properties"].items():
            subdata = data.get(prop)
            # assert prop not in schema["required"] or subdata is not None
            if subdata is not None:
                newdata[prop] = _fix_type(subdata, subschema)
                pass
            pass
        return newdata
    elif schema["type"] == "array":
        subschema = schema["items"]
        assert isinstance(data, list)
        return [_fix_type(subdata, subschema) for subdata in data]
    elif schema["type"] == "string":
        assert isinstance(data, str)
        return data
    elif schema["type"] == "number":
        assert isinstance(data, str)
        try:
            return int(data)
        except ValueError:
            return float(data)
    elif schema["type"] == "boolean":
        assert isinstance(data, str)
        return bool(data)
    else:
        raise Exception("_fix_type: Other types are not implemented")
    pass
