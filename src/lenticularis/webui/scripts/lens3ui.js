// Copyright (c) 2022 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

///// Editor /////

var csrf_token;

var editor_data = {
  pool_name_visible: false,
  edit_pool_visible: false,
  zoneID: "",
  user: "",
  group: "",
  bucketsDir: "",
  buckets: ["", "", "", ""],
  accessKeys: [],
  accessKeyIDrw: "",
  accessKeyIDro: "",
  accessKeyIDwo: "",
  secretAccessKeyrw: "",
  secretAccessKeyro: "",
  secretAccessKeywo: "",
  key: "",
  policy: "",
  directHostnames: "",
  expDate: "",
  status: "",
  mode: "",
  atime: "",
  groups: "",
  directHostnameDomains: "",
  facadeHostname: "",
  endpointURLs: "",
  submit_button_name: "",
  submit_button_disabled: false,
  submit_button_visible: false,
  deleteButtonDisabled: false,
  buckets_directory_disabled: false,
};

var make_pool_app = new Vue({
  el: '#create_pool',
  data: editor_data,
  methods: {
    submitZoneToCreate: submit_zone_to_create,
    submitChangeAccessKeyRW: change_access_key_rw,
    submitChangeAccessKeyRO: change_access_key_ro,
    submitChangeAccessKeyWO: change_access_key_wo,
    submit_make_access_key_rw: change_access_key_rw,
    submit_make_access_key_ro: change_access_key_ro,
    submit_make_access_key_wo: change_access_key_wo,
  },
});

var edit_buckets_app = new Vue({
  el: '#edit_buckets',
  data: editor_data,
  methods: {
    submitZoneToCreate: submit_zone_to_create,
    submit_create_bucket: create_bucket,
    submitChangeAccessKeyRW: change_access_key_rw,
    submitChangeAccessKeyRO: change_access_key_ro,
    submitChangeAccessKeyWO: change_access_key_wo,
    submit_make_access_key_rw: change_access_key_rw,
    submit_make_access_key_ro: change_access_key_ro,
    submit_make_access_key_wo: change_access_key_wo,
  },
});

var edit_keys_app = new Vue({
  el: '#edit_keys',
  data: editor_data,
  methods: {
    submitZoneToCreate: submit_zone_to_create,
    submitChangeAccessKeyRW: change_access_key_rw,
    submitChangeAccessKeyRO: change_access_key_ro,
    submitChangeAccessKeyWO: change_access_key_wo,
    submit_make_access_key_rw: change_access_key_rw,
    submit_make_access_key_ro: change_access_key_ro,
    submit_make_access_key_wo: change_access_key_wo,
  },
});

///// Show Storage Zone (button) /////
var show_data = {
  message: "---",
  status: "---",
  reason: "---",
  time: "---",
};

var status_app = new Vue({
  el: "#show_status",
  data: show_data,
  methods: {
    show_pool_list: get_zone_list,
    debug: debug,
  },
});

var show_app = new Vue({
  el: "#show_pool_list_button",
  data: show_data,
  methods: {
    show_pool_list: get_zone_list,
    debug: debug,
  },
});

var add_app = new Vue({
  el: "#add_new_pool_button",
  methods: {
    add_zone: get_template,
  },
});

///// Zone /////

// dynamically allocated
var zone_data = { zone_data_visible: false }; // sentinel
var list_pools_app;

///// FUNCTIONS /////

function submit_zone_to_create() {
  var create = editor_data["submit_button_name"] == "Create";
  console.log("CREATE = " + create);
  if (create) {
    return submit_zone(0, null)
  }
  else {
    return submit_zone(1, null)
  }
}

function create_bucket() {
  console.log("create_bucket: name=" + editor_data.key
              + ", policy=" + editor_data.policy);
  return submit_zone(2, () => {
    var key = editor_data.key;
    var policy = editor_data.policy;
    method = "PUT";
    url_path = ("/pool/" + editor_data.zoneID + "/bucket/" + key);
    var c = {"bucket": {"key": key, "policy": policy}};
    body = stringify_dict(c, csrf_token);
    return {method, url_path, body};
  });
}

function change_access_key_rw() {
  console.log("change_access_key RW");
  return submit_zone(3, null)
}

function change_access_key_ro() {
  console.log("change_access_key RO");
  return submit_zone(4, null)
}

function change_access_key_wo() {
  console.log("change_access_key WO");
  return submit_zone(5, null)
}

function submit_zone(op, triple) {
  editor_data.submit_button_disabled = true;
  show_message(editor_data["submit_button_name"] + " zone...");
  clear_status_field();

  var method;
  var url_path;
  var body;

  if (op == 0) {          // create
    method = "POST";
    url_path = "/zone";
    body = compose_create_dict(csrf_token);
  }
  else if (op == 1) {     // updte zone
    method = "PUT";
    url_path = "/zone/" + editor_data.zoneID;
    body = compose_update_dict(csrf_token);
  }
  else if (op == 2) {     // create bucket
    //var key = editor_data.key;
    //var policy = editor_data.policy;
    //method = "PUT";
    //url_path = "/zone/" + editor_data.zoneID + "/buckets";
    //body = compose_create_bucket_dict(csrf_token, key, policy);
    const tt = triple();
    method = tt.method;
    url_path = tt.url_path;
    body = tt.body;
  }
  else if (op == 3 || op == 4 || op == 5) {
    var accessKeyID;
    if (op == 3) {
      accessKeyID = editor_data.accessKeyIDrw;
    }
    else if (op == 4) {
      accessKeyID = editor_data.accessKeyIDro;
    }
    else if (op == 5) {
      accessKeyID = editor_data.accessKeyIDwo;
    }

    method = "PUT";
    url_path = "/zone/" + editor_data.zoneID + "/accessKeys";
    body = compose_access_key_update_dict(csrf_token, accessKeyID);
  }

  console.log("method: " + method);
  console.log("url_path: " + url_path);
  console.log("body: " + body);
  var request_options = {
    method: method,
    body: body,
  };

  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
            function(data) {
              console.log("responsedata0: " + data);
              show_message(editor_data.submit_button_name + " zone... error: " + JSON.stringify(data));
              render_jsondata(data)
              if (data["zonelist"] != null) {
                editor_data.mode = data["zonelist"][0]["minio_state"];
              }
              editor_data.submit_button_disabled = false;
              editor_data.submit_button_visible = true;
              throw new Error(JSON.stringify(data));
            })
      } else {
        return response.json().then(function(data) {
          show_message(editor_data.submit_button_name + " zone... done: " + JSON.stringify(data));
          render_jsondata(data)
          editor_data.mode = data["zonelist"][0]["minio_state"]
          // update succeeded. do not re-enable button now.
        })
      }
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

const policies = ["none", "public", "upload", "download"];

const policyNames = ["readwrite", "readonly", "writeonly"];

function stringify_dict(dict, csrf_token) {
  dict["CSRF-Token"] = csrf_token;
  return JSON.stringify(dict);
}

function pullup_zone() {
  var zone = {};
  var buckets = new Array();
  var directHostnames = new Array();
  for (var i = 0; i < policies.length; i++) {
    buckets = push_buckets(buckets, editor_data.buckets[i], policies[i]);
  }
  directHostnames = push_direct_hostnames(directHostnames,
                                          editor_data.directHostnameDomains,
                                          editor_data.directHostnames);
  zone["owner_gid"] = editor_data.group;
  zone["buckets_directory"] = editor_data.bucketsDir;
  zone["buckets"] = buckets;
  zone["access_keys"] = [{"policy_name": "readwrite"}, {"policy_name": "readonly"}, {"policy_name": "writeonly"}]; // dummy entry
  zone["direct_hostnames"] = directHostnames;
  zone["expiration_date"] = parse_rfc3339(editor_data.expDate);
  zone["online_status"] = editor_data.status;
  // ignore "minio_state", nor "atime"
  return zone;
}

function compose_create_dict(csrf_token) {
  var zone = pullup_zone();
  var dict = {"zone": zone};
  return stringify_dict(dict, csrf_token);
}

function compose_update_dict(csrf_token) {
  var zone = pullup_zone();
  zone["access_keys"] = editor_data.accessKeys; // overwrite a dummy entry
  var dict = {"zone": zone};
  return stringify_dict(dict, csrf_token);
}

function compose_create_bucket_dict(csrf_token, key, policy) {
  if (policy != "none" && policy != "upload" && policy != "download") {
    throw new Error("error: invalid policy: " + policy);
  }
  var zone = {"buckets": [{"key": key, "policy": policy}]};
  var dict = {"zone": zone};
  return stringify_dict(dict, csrf_token);
}

function compose_access_key_update_dict(csrf_token, accessKeyID) {
  var zone = {"access_keys": [{"access_key": accessKeyID}]};
  var dict = {"zone": zone};
  return stringify_dict(dict, csrf_token);
}

function compose_delete_dict(csrf_token) {
  var dict = {};
  return stringify_dict(dict, csrf_token);
}

function push_buckets(buckets, bucketList, policy) {
  var xs = bucketList.split(' ');
  for (var i = 0; i < xs.length; i++) {
    var bucket = xs[i];
    if (bucket != "") {
      var v = {"key": bucket, "policy": policy};
      buckets.push(v);
    }
  }
  return buckets;
}

function push_direct_hostnames(directHostnames, directHostnameDomains, hosts) {
  var xs = hosts.split(' ');
  for (var i = 0; i < xs.length; i++) {
    var directHostname = xs[i];
    if (directHostname != "") {
      if (!directHostname.endsWith("." + directHostnameDomains[0])) {
        directHostname += "." + directHostnameDomains[0];
      }
      directHostnames.push(directHostname);
    }
  }
  return directHostnames;
}

function debug() {
  var post_data = compose_create_dict(csrf_token);
  var put_data = compose_update_dict(csrf_token);
  var bkt_data = compose_create_bucket_dict(csrf_token);
  var key_data = compose_access_key_update_dict(csrf_token);
  var delete_data = compose_delete_dict(csrf_token);
  console.log("post_data: " + post_data);
  console.log("put_data: " + put_data);
  console.log("bkt_data: " + bkt_data);
  console.log("key_data: " + key_data);
  console.log("delete_data: " + delete_data);
  //parsed = Date.parse("2012-07-04T18:10:00.000+09:00")
  //console.log("parsed: " + parsed);
  //var e = "1638401795";
  //var date = new Date(e * 1000);
  //var formatted = date.toISOString();
  //console.log("toISOString: " + e + " => " + formatted);
  //var t = "2012-07-04T18:10:00.000+09:00";
  //var parsed = Date.parse(s)
  //var date2 = new Date(s)
  //var d2 = date2.getTime() / 1000;
  //console.log("new Date: " + s + " => " + d2);
  var s = "2022-03-31T00:00:00.000Z";
  var t = parse_rfc3339(s);
  var u = format_rfc3339(t);
  console.log("parse: " + s + " => " + t);
  console.log("unparse: " + t + " => " + u);
}

function get_zone_list() {
  show_message("get zone list...");
  clear_status_field();
  const method = "GET";
  const url_path = "/zone";
  const request_options = {
    method: method,
    headers: {},
  };
  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
          function(data) {
            show_message("get zone list... error: " + JSON.stringify(data));
            render_jsondata(data)
            throw new Error(JSON.stringify(data));
          })
      }
      response.json().then(function(data) {
        csrf_token = data["CSRF-Token"];
        get_zone_list_body(data["zonelist"]);
        show_message("get zone list... done");
      })
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

function get_template() {
  editor_data.submit_button_disabled = true;
  show_message("get new zone...");
  clear_status_field();
  const method = "GET";
  const url_path = "/template";
  const request_options = {
    method: method,
    headers: {},
  };
  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
          function(data) {
            show_message("get new zone... error: " + JSON.stringify(data));
            render_jsondata(data)
            // fatal error. do not re-enable the button. enable_update_button();
            throw new Error(JSON.stringify(data));
          })
      }
      response.json().then(function(data) {
        csrf_token = data["CSRF-Token"];
        get_template_body(data["zonelist"]);
        show_message("get new zone... done");
        editor_data.submit_button_disabled = false;
        editor_data.submit_button_visible = true;
      })
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

function get_template_body(zone_list) {
  zone = zone_list[0];
  set_zone_to_editor_body(zone);
  editor_data.submit_button_name = "Create";
  editor_data.submit_button_disabled = false;
  editor_data.submit_button_visible = true;
  editor_data.pool_name_visible = true;
  editor_data.buckets_directory_disabled = false;
  editor_data.edit_pool_visible = false;
  zone_data.zone_data_visible = false;
}

function disable_create_button() {
  editor_data.submit_button_disabled = true;
}

function enable_create_button() {
  editor_data.submit_button_disabled = false;
}

function set_create_button_visibility(v) {
  editor_data.submit_button_visible = v;
}

function disable_delete_button() {
  editor_data.deleteButtonDisabled = true;
}

function enable_delete_button() {
  editor_data.deleteButtonDisabled = false;
}

function delete_zone_body(zone) {
  disable_delete_button();
  show_message("delete zone...");
  clear_status_field();
  var zoneID = zone["zoneID"];
  console.log(`zoneID = ${zoneID}`);
  const request_options = {
    method: "DELETE",
    body: compose_delete_dict(csrf_token),
  };
  var url_path = "/zone/" + zoneID;
  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
          function(data) {
            show_message("delete zone... error: " + JSON.stringify(data));
            render_jsondata(data)
            enable_delete_button();
            throw new Error(JSON.stringify(data));
          })
      }
      response.json().then(function(data) {
        show_message("delete zone... done");
        enable_delete_button();
        get_zone_list();
      })
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

function get_zone_list_body(zone_list) {
  var div = "";
  var res = new Array();
  var items_list = new Array();
  editor_data.pool_name_visible = false;
  editor_data.edit_pool_visible = false;
  for (var k = 0; k < zone_list.length; k++) {
    var zone = zone_list[k];
    var i = "<input v-on:click='editZone(" + k + ")' type='button' class='button' value='Edit' />" +
        "<input v-on:click='deleteZone(" + k + ")' type='button' class='button' value='Delete' :disabled='editor_data.deleteButtonDisabled' />" +
        "<ul style='list-style: none;'>" +
        "<li v-for='item in items_list[" + k + "]'>" +
        "<span class='label'> {{ item.text.label }}: </span>" +
        " {{ item.text.value }} " +
        "</li>" +
        "</ul>" +
        "<hr>";
    res.push(i);
    items_list.push(zone_to_ul_data(zone));
  }
  var div = "<div id='pool_list_viewer' v-if='zone_data_visible'>" +
      res.join("") +
      "</div>";
  var el = document.getElementById("pool_list")
  el.innerHTML = "";
  el.insertAdjacentHTML("beforeend", div);

  zone_data = {
    zone_data_visible: false,
    items_list: items_list,
    zone_list: zone_list,
  };

  function edit_zone(i) {
    set_zone_to_editor_body(zone_data.zone_list[i]);
    editor_data.pool_name_visible = true;
    editor_data.buckets_directory_disabled = true;
    editor_data.edit_pool_visible = true;
    zone_data.zone_data_visible = false;
    editor_data.submit_button_name = "Update";
    editor_data.submit_button_disabled = false;
    editor_data.submit_button_visible = true;
  }
  function delete_zone(i) {
    delete_zone_body(zone_data.zone_list[i])
  }

  list_pools_app = new Vue({
    el: "#pool_list_viewer",
    data: zone_data,
    methods: {
      editZone: edit_zone,
      deleteZone: delete_zone,
    }
  });
  list_pools_app.$mount();
  zone_data.zone_list = zone_list;
  zone_data.zone_data_visible = true;
}

function zone_to_ul_data(zone) {
  var buckets = zone["buckets"];
  var accessKeys = zone["access_keys"];
  var rwkey = chooseAccessKey(accessKeys, "readwrite");
  var rokey = chooseAccessKey(accessKeys, "readonly");
  var wokey = chooseAccessKey(accessKeys, "writeonly");

  return [
    {text: {label: "Buckets directory", value: zone["buckets_directory"]}},
    {text: {label: "Unix user", value: zone["owner_uid"]}},
    {text: {label: "Unix group", value: zone["owner_gid"]}},
    {text: {label: "Private buckets", value: scan_buckets(buckets, "none")}},
    {text: {label: "Public buckets", value: scan_buckets(buckets, "public")}},
    {text: {label: "Public download buckets", value: scan_buckets(buckets, "download")}},
    {text: {label: "Public upload buckets", value: scan_buckets(buckets, "upload")}},
    {text: {label: "Access key ID (RW)", value: rwkey["access_key"]}},
    {text: {label: "Secret access key", value: rwkey["secret_key"]}},
    {text: {label: "Access key ID (RO)", value: rokey["access_key"]}},
    {text: {label: "Secret access key", value: rokey["secret_key"]}},
    {text: {label: "Access key ID (WO)", value: wokey["access_key"]}},
    {text: {label: "Secret access key", value: wokey["secret_key"]}},
    {text: {label: "Endpoint-URL", value: zone["endpoint_url"]}},
    {text: {label: "Pool-ID", value: zone["zoneID"]}},
    {text: {label: "Direct hostname", value: zone["direct_hostnames"].join(' ')}},
    {text: {label: "Expiration date", value: format_rfc3339_if_not_zero(zone["expiration_date"])}},
    {text: {label: "MinIO state", value: zone["minio_state"]}},
    {text: {label: "Enabled", value: zone["online_status"]}},
    {text: {label: "Permitted", value: zone["admission_status"]}},
    {text: {label: "Last access time", value: format_rfc3339_if_not_zero(zone["atime"])}},
  ];
}

function set_zone_to_editor_body(zone) {
  var accessKeys = zone["access_keys"];
  var rwkey = chooseAccessKey(accessKeys, "readwrite");
  var rokey = chooseAccessKey(accessKeys, "readonly");
  var wokey = chooseAccessKey(accessKeys, "writeonly");

  editor_data.zoneID = zone["zoneID"];
  editor_data.user = zone["owner_uid"];
  editor_data.group = zone["owner_gid"];
  editor_data.bucketsDir = zone["buckets_directory"];
  var buckets = zone["buckets"];
  for (var i = 0; i < policies.length; i++) {
    editor_data.buckets[i] = scan_buckets(buckets, policies[i]);
  }

  // for chenge secret
  editor_data.accessKeys = accessKeys;
  editor_data.accessKeyIDrw = rwkey["access_key"];
  editor_data.accessKeyIDro = rokey["access_key"];
  editor_data.accessKeyIDwo = wokey["access_key"];
  editor_data.secretAccessKeyrw = rwkey["secret_key"];
  editor_data.secretAccessKeyro = rokey["secret_key"];
  editor_data.secretAccessKeywo = wokey["secret_key"];

  editor_data.key = "";           // for bucket creation
  editor_data.policy = "";        // ditto.

  editor_data.directHostnames = zone["direct_hostnames"].join(' ');
  editor_data.expDate = format_rfc3339_if_not_zero(zone["expiration_date"]);
  editor_data.status = zone["online_status"];
  editor_data.mode = zone["minio_state"];
  editor_data.atime = format_rfc3339_if_not_zero(zone["atime"]);
  editor_data.groups = zone["groups"];
  editor_data.directHostnameDomains = zone["directHostnameDomains"];
  editor_data.facadeHostname = zone["facadeHostname"];
  editor_data.endpointURLs = zone["endpoint_url"];
  show_message("editing");
}

function show_message(s) {
  show_data.message = "Message: " + s;
}

function clear_status_field() {
  render_jsondata({"status": "", "reason": "", "time": "0"})
}

function render_jsondata(data) {
  show_status(data["status"])
  show_reason(data["reason"])
  show_time(data["time"])
}

function show_status(s) {
  show_data.status = "Status: " + s;
}

function show_reason(s) {
  show_data.reason = "Reason: " + s;
}

function show_time(s) {
  if (s != null) {
    show_data.time = "Finished at: " + format_rfc3339_if_not_zero(s);
  } else {
    show_data.time = "";
  }
}

function parse_rfc3339(s) {
  return "" + new Date(s).getTime() / 1000;
}

function format_rfc3339(d) {
  return new Date(d * 1000).toISOString();
}

function format_rfc3339_if_not_zero(d) {
  //console.log("format_rfc3339_if_not_zero: " + d);
  if (d == "0") {
    return "0";
  }
  return format_rfc3339(d);
}

function chooseAccessKey(accessKeys, policyName) {
  for (var i = 0; i < accessKeys.length; i++) {
    var accessKey = accessKeys[i];
    if (accessKey["policy_name"] == policyName) {
      return accessKey;
    }
  }
  return undefined;
}

function scan_buckets(buckets, policy) {
  var res = new Array();
  for (var i = 0; i < buckets.length; i++) {
    var bucket = buckets[i];
    if (bucket["policy"] == policy) {
      res.push(bucket["key"]);
    }
  }
  return res.join(' ');
}